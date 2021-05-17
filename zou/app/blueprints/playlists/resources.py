import slugify

from flask import request, send_file as flask_send_file
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app import config
from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions

from zou.app.services import (
    entities_service,
    playlists_service,
    persons_service,
    preview_files_service,
    projects_service,
    shots_service,
    user_service,
)
from zou.app.stores import file_store, queue_store
from zou.app.utils import fs
from zou.utils.movie import EncodingParameters


class ProjectPlaylistsResource(Resource, ArgsMixin):
    """
    Retrieve all playlists related to given project. Result is paginated and
    can be sorted.
    """

    @jwt_required
    def get(self, project_id):
        user_service.block_access_to_vendor()
        user_service.check_project_access(project_id)
        page = self.get_page()
        sort_by = self.get_sort_by()
        task_type_id = self.get_text_parameter("task_type_id")
        return playlists_service.all_playlists_for_project(
            project_id,
            for_client=permissions.has_client_permissions(),
            page=page,
            sort_by=sort_by,
            task_type_id=task_type_id
        )


class EpisodePlaylistsResource(Resource, ArgsMixin):
    """
    Retrieve all playlists related to given episode. The full list is returned
    because the number of playlists in an episode is not that big.
    """

    @jwt_required
    def get(self, project_id, episode_id):
        user_service.block_access_to_vendor()
        user_service.check_project_access(project_id)
        sort_by = self.get_sort_by()
        task_type_id = self.get_text_parameter("task_type_id")
        if episode_id not in ["main", "all"]:
            shots_service.get_episode(episode_id)
        return playlists_service.all_playlists_for_episode(
            project_id,
            episode_id,
            permissions.has_client_permissions(),
            sort_by=sort_by,
            task_type_id=task_type_id,
        )


class ProjectPlaylistResource(Resource):
    @jwt_required
    def get(self, project_id, playlist_id):
        user_service.block_access_to_vendor()
        user_service.check_project_access(project_id)
        return playlists_service.get_playlist_with_preview_file_revisions(
            playlist_id
        )


class EntityPreviewsResource(Resource):
    @jwt_required
    def get(self, entity_id):
        """
        Retrieve all previews related to a given entity. It sends them
        ]as a dict. Keys are related task type ids and values are arrays
        of preview for this task type.
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return playlists_service.get_preview_files_for_entity(entity_id)


class PlaylistDownloadResource(Resource):
    @jwt_required
    def get(self, playlist_id, build_job_id):
        playlist = playlists_service.get_playlist(playlist_id)
        project = projects_service.get_project(playlist["project_id"])
        build_job = playlists_service.get_build_job(build_job_id)
        user_service.check_project_access(playlist["project_id"])

        if build_job["status"] != "succeeded":
            return {"error": True, "message": "Build is not finished"}, 400
        else:
            movie_file_path = fs.get_file_path(
                config,
                file_store.get_local_movie_path,
                file_store.open_movie,
                "playlists",
                build_job_id,
                "mp4",
            )
            context_name = slugify.slugify(project["name"], separator="_")
            if project["production_type"] == "tvshow":
                episode_id = playlist["episode_id"]
                if episode_id is not None:
                    episode = shots_service.get_episode(playlist["episode_id"])
                    episode_name = episode["name"]
                elif playlist["is_for_all"]:
                    episode_name = "all assets"
                else:
                    episode_name = "main pack"
                context_name += "_%s" % slugify.slugify(
                    episode_name, separator="_"
                )
            attachment_filename = "%s_%s_%s.mp4" % (
                slugify.slugify(build_job["created_at"], separator="").replace(
                    "t", "_"
                ),
                context_name,
                slugify.slugify(playlist["name"], separator="_"),
            )
            return flask_send_file(
                movie_file_path,
                conditional=True,
                mimetype="video/mp4",
                as_attachment=True,
                attachment_filename=attachment_filename,
            )


class BuildPlaylistMovieResource(Resource):
    @jwt_required
    def get(self, playlist_id):
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_manager_project_access(playlist["project_id"])

        project = projects_service.get_project(playlist["project_id"])
        (width, height) = preview_files_service.get_preview_file_dimensions(
            project
        )
        fps = preview_files_service.get_preview_file_fps(project)
        params = EncodingParameters(width=width, height=height, fps=fps)

        shots = [
            {"preview_file_id": x.get("preview_file_id")}
            for x in playlist["shots"]
        ]

        if config.ENABLE_JOB_QUEUE:
            remote = config.ENABLE_JOB_QUEUE_REMOTE
            # remote worker can not access files local to the web app
            assert not remote or config.FS_BACKEND in ["s3", "swift"]

            current_user = persons_service.get_current_user()
            queue_store.job_queue.enqueue(
                playlists_service.build_playlist_job,
                args=(playlist, shots, params, current_user["email"], remote),
                job_timeout=3600,
            )
            return {"job": "running"}
        else:
            job = playlists_service.build_playlist_movie_file(
                playlist, shots, params, remote=False
            )
            return {"job": job["status"]}


class PlaylistZipDownloadResource(Resource):
    @jwt_required
    def get(self, playlist_id):
        playlist = playlists_service.get_playlist(playlist_id)
        project = projects_service.get_project(playlist["project_id"])
        user_service.block_access_to_vendor()
        user_service.check_playlist_access(playlist)
        zip_file_path = playlists_service.build_playlist_zip_file(playlist)

        context_name = slugify.slugify(project["name"], separator="_")
        if project["production_type"] == "tvshow":
            episode_id = playlist["episode_id"]
            if episode_id is not None:
                episode = shots_service.get_episode(playlist["episode_id"])
                episode_name = episode["name"]
            elif playlist["is_for_all"]:
                episode_name = "all assets"
            else:
                episode_name = "main pack"
            context_name += "_%s" % slugify.slugify(episode_name, separator="_")
        attachment_filename = "%s_%s.zip" % (
            context_name,
            slugify.slugify(playlist["name"], separator="_"),
        )

        return flask_send_file(
            zip_file_path,
            conditional=True,
            mimetype="application/zip",
            as_attachment=True,
            attachment_filename=attachment_filename,
        )


class BuildJobResource(Resource):
    @jwt_required
    def get(self, playlist_id, build_job_id):
        user_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_playlist_access(playlist)
        return playlists_service.get_build_job(build_job_id)

    @jwt_required
    def delete(self, playlist_id, build_job_id):
        user_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_playlist_access(playlist)
        playlists_service.remove_build_job(playlist, build_job_id)
        return "", 204


class ProjectBuildJobsResource(Resource):
    """
    Retrieve all build jobs related to given project.
    It's mainly used for synchronisation purpose.
    """

    @jwt_required
    def get(self, project_id):
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        return playlists_service.get_build_jobs_for_project(project_id)


class ProjectAllPlaylistsResource(Resource, ArgsMixin):
    """
    Retrieve all playlists related to given project.
    It's mainly used for synchronisation purpose.
    """

    @jwt_required
    def get(self, project_id):
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        page = self.get_page()
        return playlists_service.get_playlists_for_project(project_id, page)


class TempPlaylistResource(Resource, ArgsMixin):
    """
    Retrieve all playlists related to given project.
    It's mainly used for synchronisation purpose.
    """

    @jwt_required
    def post(self, project_id):
        user_service.check_project_access(project_id)
        task_ids = request.json.get("task_ids", [])
        return playlists_service.generate_temp_playlist(task_ids) or []
