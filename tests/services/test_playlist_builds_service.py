import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch
from zipfile import ZipFile
from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.models.build_job import BuildJob
from zou.app.models.playlist import Playlist
from zou.app.stores import file_store
from zou.app.services import playlists_service, playlist_builds_service
from zou.app.utils import fields, fs, remote_job
from zou.utils import movie
from zou.utils.movie import EncodingParameters


class PlaylistsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project_standard()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.episode_2 = self.generate_fixture_episode("E02")
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()

    def generate_fixture_preview_files(self):
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.task = self.generate_fixture_shot_task()
        self.preview_file_1 = self.generate_fixture_preview_file(revision=1)
        # The latest revision, and the one self.preview_file points at.
        self.preview_file_2 = self.generate_fixture_preview_file(revision=2)

    def generate_fixture_playlists(self):
        Playlist.create(
            name="Playlist 1",
            shots={},
            project_id=self.project.id,
            episode_id=self.episode.id,
        )
        Playlist.create(
            name="Playlist 2", shots={}, project_id=self.project_standard.id
        )
        Playlist.create(
            name="Playlist 3",
            shots={},
            project_id=self.project.id,
            episode_id=self.episode_2.id,
        )
        self.playlist = Playlist.create(
            name="Playlist 4",
            shots={},
            project_id=self.project.id,
            episode_id=self.episode_2.id,
        )
        return self.playlist.serialize()

    def test_start_and_end_build_job(self):
        """
        The two ends of a playlist build: the row the clients poll while the
        movie is being encoded, then its final status.
        """
        playlist = self.generate_fixture_playlists()

        job = playlist_builds_service.start_build_job(playlist)
        self.assertEqual(job["status"], "running")
        self.assertEqual(job["playlist_id"], playlist["id"])
        self.assertIsNone(job["ended_at"])

        job = playlist_builds_service.end_build_job(playlist, job, False)
        self.assertEqual(job["status"], "failed")
        self.assertIsNotNone(job["ended_at"])

    def test_end_build_job_message(self):
        """
        The optional message explains a degraded build to whoever looks
        at the job afterwards.
        """
        playlist = self.generate_fixture_playlists()
        job = playlist_builds_service.start_build_job(playlist)
        job = playlist_builds_service.end_build_job(
            playlist, job, True, message="built by the concat filter"
        )
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["message"], "built by the concat filter")

    def test_build_playlist_movie_file_reports_the_fallback(self):
        """
        When the concat demuxer rejects the previews and the re-encoding
        concat filter builds the movie instead, the job says so rather
        than reporting a plain success (cgwire/kitsu#2184).
        """
        playlist = self.generate_fixture_playlists()
        job = playlist_builds_service.start_build_job(playlist)
        params = EncodingParameters(width=1920, height=1080, fps="25.00")

        def fake_build(mode, tmp_file_paths, movie_file_path, **kwargs):
            if mode is movie.concat_demuxer:
                return {
                    "success": False,
                    "message": "a.mp4 has an unexpected video/audio "
                    "stream number (3)",
                }
            open(movie_file_path, "w").close()
            return {"success": True}

        with (
            patch.object(
                playlists_service,
                "playlist_previews",
                return_value=[{"id": "a", "extension": "mp4"}],
            ),
            patch.object(
                playlist_builds_service,
                "retrieve_playlist_tmp_files",
                return_value=[("/tmp/a.mp4", "a.mp4")],
            ),
            patch.object(movie, "build_playlist_movie", fake_build),
            patch.object(playlist_builds_service.file_store, "add_movie"),
        ):
            job = playlist_builds_service.build_playlist_movie_file(
                playlist, job, [], params, False, False
            )

        self.assertEqual(job["status"], "succeeded")
        self.assertIn("concat filter", job["message"])
        self.assertIn("stream number", job["message"])

    def test_a_handed_over_remote_build_stays_running(self):
        """
        When the worker stops while Nomad builds the movie, the build goes
        on in the next worker: it is neither failed nor ended.
        """
        playlist = self.generate_fixture_playlists()
        job = playlist_builds_service.start_build_job(playlist)
        params = EncodingParameters(width=1920, height=1080, fps="25.00")

        with (
            patch.object(
                playlists_service,
                "playlist_previews",
                return_value=[{"id": "a", "extension": "mp4"}],
            ),
            patch.object(
                playlist_builds_service,
                "_run_remote_job_build_playlist",
                side_effect=remote_job.NomadJobHandedOver(),
            ),
            patch.object(
                playlist_builds_service, "end_build_job"
            ) as end_build_job,
        ):
            self.assertRaises(
                remote_job.NomadJobHandedOver,
                playlist_builds_service.build_playlist_movie_file,
                playlist,
                job,
                [],
                params,
                False,
                True,
            )

        end_build_job.assert_not_called()

    def test_a_remote_build_downloads_no_preview(self):
        """
        The remote runner fetches the previews itself: the worker neither
        downloads them nor checks them.
        """
        playlist = self.generate_fixture_playlists()
        job = playlist_builds_service.start_build_job(playlist)
        params = EncodingParameters(width=1920, height=1080, fps="25.00")
        previews = [{"id": "preview-1", "extension": "mp4"}]

        with (
            patch.object(
                playlists_service, "playlist_previews", return_value=previews
            ),
            patch.object(
                playlist_builds_service, "retrieve_playlist_tmp_files"
            ) as retrieve,
            patch.object(
                playlist_builds_service, "_run_remote_job_build_playlist"
            ) as run_remote,
        ):
            job = playlist_builds_service.build_playlist_movie_file(
                playlist, job, [], params, False, True
            )

        retrieve.assert_not_called()
        self.assertEqual(run_remote.call_args.args[2], previews)
        self.assertEqual(job["status"], "succeeded")

    def test_a_remote_build_without_movie_dispatches_nothing(self):
        playlist = self.generate_fixture_playlists()
        job = playlist_builds_service.start_build_job(playlist)
        params = EncodingParameters(width=1920, height=1080, fps="25.00")

        with (
            patch.object(
                playlists_service, "playlist_previews", return_value=[]
            ),
            patch.object(
                playlist_builds_service, "_run_remote_job_build_playlist"
            ) as run_remote,
        ):
            self.assertRaises(
                Exception,
                playlist_builds_service.build_playlist_movie_file,
                playlist,
                job,
                [],
                params,
                False,
                True,
            )

        run_remote.assert_not_called()

    def test_a_remote_build_warms_the_download_cache(self):
        """
        The built movie is fetched right after the remote job, into the
        cache entry the download route reads.
        """
        job = {"id": fields.gen_uuid()}
        params = EncodingParameters(width=1920, height=1080, fps="25.00")
        movie_file_path = playlist_builds_service.get_playlist_movie_file_path(
            job
        )
        self.addCleanup(fs.rm_file, movie_file_path)

        with (
            patch.object(playlist_builds_service.remote_job, "run_job"),
            patch.object(
                playlist_builds_service.config_store,
                "get_nomad_playlist_job",
                return_value="zou-playlist",
            ),
            patch.object(
                playlist_builds_service.file_store,
                "open_movie",
                return_value=iter([b"built ", b"movie"]),
            ),
        ):
            playlist_builds_service._run_remote_job_build_playlist(
                MagicMock(), job, [], params, movie_file_path, False
            )

        self.assertEqual(
            movie_file_path,
            fs.get_cache_file_path(config, "playlists", job["id"], "mp4"),
        )
        with open(movie_file_path, "rb") as movie_file:
            self.assertEqual(movie_file.read(), b"built movie")

    def test_an_interrupted_download_leaves_no_truncated_movie(self):
        job = {"id": fields.gen_uuid()}
        params = EncodingParameters(width=1920, height=1080, fps="25.00")
        movie_file_path = playlist_builds_service.get_playlist_movie_file_path(
            job
        )
        self.addCleanup(fs.rm_file, movie_file_path)

        def interrupted(*_):
            yield b"built "
            raise ConnectionError("reset")

        with (
            patch.object(playlist_builds_service.remote_job, "run_job"),
            patch.object(
                playlist_builds_service.config_store,
                "get_nomad_playlist_job",
                return_value="zou-playlist",
            ),
            patch.object(
                playlist_builds_service.file_store, "open_movie", interrupted
            ),
        ):
            self.assertRaises(
                ConnectionError,
                playlist_builds_service._run_remote_job_build_playlist,
                MagicMock(),
                job,
                [],
                params,
                movie_file_path,
                False,
            )

        self.assertFalse(os.path.exists(movie_file_path))

    def test_build_playlist_job_mails_the_finished_build(self):
        # The job dict handed to the queue says "running" for ever: the
        # status to test is the one the build returns.
        self.generate_fixture_preview_files()
        self.generate_fixture_playlists()
        playlist = self.playlist.serialize()
        job = playlist_builds_service.start_build_job(playlist)
        finished = {**job, "status": "succeeded"}

        with (
            patch.object(
                playlist_builds_service,
                "build_playlist_movie_file",
                return_value=finished,
            ),
            patch.object(
                playlist_builds_service.emails, "send_email"
            ) as send_email,
        ):
            playlist_builds_service.build_playlist_job(
                playlist, job, [], None, self.user["email"], False, False
            )

        send_email.assert_called_once()
        self.assertIn(job["id"], send_email.call_args.args[1])

    def test_playlist_tmp_copies_keep_their_own_file(self):
        """
        Two previews of a playlist may carry the same display name (the
        original file name option): their local copies used to overwrite
        each other, and pile up in TMP_DIR.
        """
        self.generate_fixture_preview_files()
        movie_fixture = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
        )
        previews = [
            self.preview_file_1.serialize(),
            self.preview_file_2.serialize(),
        ]
        for preview in previews:
            file_store.add_movie("previews", preview["id"], movie_fixture)
        tmp_dir = tempfile.mkdtemp()
        try:
            with patch.object(
                playlist_builds_service.names_service,
                "get_preview_file_name",
                return_value="render.mp4",
            ):
                copies = playlist_builds_service.retrieve_playlist_tmp_files(
                    previews, tmp_dir=tmp_dir
                )
            paths = [path for path, _ in copies]
            self.assertEqual(len(set(paths)), 2)
            self.assertTrue(all(path.startswith(tmp_dir) for path in paths))
            self.assertEqual([name for _, name in copies], ["render.mp4"] * 2)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            for preview in previews:
                file_store.remove_movie("previews", preview["id"], force=True)

    def test_a_movie_stored_as_low_def_only_is_found(self):
        self.generate_fixture_preview_files()
        movie_fixture = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
        )
        preview = self.preview_file_1.serialize()
        file_store.add_movie("lowdef", preview["id"], movie_fixture)
        tmp_dir = tempfile.mkdtemp()
        try:
            path, _ = playlist_builds_service.retrieve_playlist_tmp_file(
                preview, tmp_dir
            )
            self.assertTrue(os.path.exists(path))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            file_store.remove_movie("lowdef", preview["id"], force=True)

    def test_a_transient_failure_does_not_switch_movie_version(self):
        # Only a confirmed absence sends the build to the next version: a
        # storage hiccup must not concatenate the low def movie instead.
        self.generate_fixture_preview_files()
        preview = self.preview_file_1.serialize()
        with patch.object(
            playlist_builds_service.fs,
            "get_file_path_and_file",
            side_effect=playlist_builds_service.fs.FileNotFound("previews-x"),
        ) as get_file:
            with self.assertRaises(playlist_builds_service.fs.FileNotFound):
                playlist_builds_service._retrieve_playlist_movie(preview)
        self.assertEqual(get_file.call_count, 1)

    def test_playlist_zip_keeps_the_previews_sharing_a_name(self):
        tmp_dir = tempfile.mkdtemp()
        copies = []
        for index in range(2):
            path = os.path.join(tmp_dir, f"{index:04d}_render.mp4")
            with open(path, "w") as copy:
                copy.write(str(index))
            copies.append((path, "render.mp4"))
        playlist = {"id": "zip-names", "shots": []}
        try:
            with patch.object(
                playlist_builds_service,
                "retrieve_playlist_tmp_files",
                return_value=copies,
            ):
                zip_path = playlist_builds_service.build_playlist_zip_file(
                    playlist
                )
            with ZipFile(zip_path) as archive:
                self.assertEqual(
                    archive.namelist(), ["render.mp4", "0001_render.mp4"]
                )
            os.remove(zip_path)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_a_build_without_tmp_dir_still_ends_its_job(self):
        # The working directory was created before the try: a full or
        # missing TMP_DIR left the job "running" for ever.
        with (
            patch.object(
                playlist_builds_service.tempfile,
                "mkdtemp",
                side_effect=OSError("No space left on device"),
            ),
            patch.object(
                playlist_builds_service, "end_build_job", return_value={}
            ) as end_build_job,
        ):
            with self.assertRaises(Exception):
                playlist_builds_service.build_playlist_movie_file(
                    {"id": "playlist"}, {"id": "job"}, [], None, False, False
                )
        end_build_job.assert_called_once()

    def test_a_failed_concatenation_is_logged(self):
        # The log call used to hand a tuple to two placeholders: the
        # logging module reported its own error and the trace was lost.
        from zou.app import app

        def broken_mode(*args, **kwargs):
            raise RuntimeError("ffmpeg exploded")

        with self.assertLogs(app.logger, level="ERROR") as logs:
            success, _ = playlist_builds_service._run_concatenation(
                {"id": "pl-1"},
                {"id": "job-1"},
                [],
                "/tmp/out.mp4",
                None,
                broken_mode,
            )
        self.assertFalse(success)
        self.assertTrue(
            any("Unable to build playlist" in line for line in logs.output)
        )

    def test_end_build_job_of_a_deleted_job(self):
        # The job row may be gone by the time the build ends: the clients
        # still get the event, and the caller an empty dict rather than a
        # crash inside the queue worker.
        playlist = self.generate_fixture_playlists()
        job = playlist_builds_service.start_build_job(playlist)
        BuildJob.get(job["id"]).delete()
        self.assertEqual(
            playlist_builds_service.end_build_job(playlist, job, True), {}
        )
