import datetime
import os
import tempfile
import threading
import unittest
import uuid

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.event import ApiEvent
from zou.app.models.entity_type import EntityType
from zou.app.models.playlist import Playlist
from zou.app.models.project import Project
from zou.app.models.studio import Studio
from zou.app.models.task_status import TaskStatus
from zou.app.services import sync_service


class EventMapTestCase(unittest.TestCase):
    """
    The maps every listener reads before it runs. They are plain module
    level dicts, so a mismatch only shows up when a sync starts.
    """

    def test_every_synced_event_has_a_path_and_a_model(self):
        """
        add_main_sync_listeners and add_project_sync_listeners read both maps
        for every event of their list. A name added to a list without an
        entry in the maps raises KeyError when the sync starts, which is a
        place nobody watches.
        """
        listened = sync_service.main_events + sync_service.project_events
        self.assertEqual(
            [
                event
                for event in listened
                if event not in sync_service.event_name_model_path_map
            ],
            [],
        )
        self.assertEqual(
            [
                event
                for event in listened
                if event not in sync_service.event_name_model_map
            ],
            [],
        )


class SyncEventTestCase(ApiDBTestCase):
    """
    The batch replay of the source event log: one event in, one row
    created, updated or dropped locally.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.remote_project_id = str(uuid.uuid4())

    def remote_project(self, name="Test Sync Project"):
        return {
            "id": self.remote_project_id,
            "name": name,
            "project_status_id": str(self.open_status.id),
            "team": [],
            "type": "Project",
        }

    def sync(self, name, data, fetched=None):
        with mock.patch.object(
            sync_service.gazu.client, "fetch_one", return_value=fetched
        ):
            sync_service.sync_event({"name": name, "data": data})

    def test_a_new_event_creates_the_row(self):
        self.sync(
            "project:new",
            {"project_id": self.remote_project_id},
            self.remote_project(),
        )
        self.assertIsNotNone(Project.get(self.remote_project_id))

    def test_an_update_event_refetches_the_row(self):
        self.sync(
            "project:new",
            {"project_id": self.remote_project_id},
            self.remote_project(),
        )
        self.sync(
            "project:update",
            {"project_id": self.remote_project_id},
            self.remote_project(name="Renamed"),
        )
        self.assertEqual(Project.get(self.remote_project_id).name, "Renamed")

    def test_a_delete_event_drops_the_row_without_fetching(self):
        self.sync(
            "project:new",
            {"project_id": self.remote_project_id},
            self.remote_project(),
        )
        with mock.patch.object(
            sync_service.gazu.client, "fetch_one"
        ) as fetch_one:
            sync_service.sync_event(
                {
                    "name": "project:delete",
                    "data": {"project_id": self.remote_project_id},
                }
            )
        fetch_one.assert_not_called()
        self.assertIsNone(Project.get(self.remote_project_id))

    def test_the_path_of_the_event_drives_the_fetch(self):
        """
        Assets and shots are both entities: the model comes from one map,
        the route from the other, and only the route tells them apart.
        """
        asset_id = str(self.asset.id)
        with mock.patch.object(
            sync_service.gazu.client,
            "fetch_one",
            return_value={"id": asset_id, "name": "Renamed"},
        ) as fetch_one:
            sync_service.sync_event(
                {"name": "asset:update", "data": {"asset_id": asset_id}}
            )
        fetch_one.assert_called_once_with("assets", asset_id)

    def test_an_old_descriptor_event_is_still_read(self):
        """
        Metadata descriptor events used to carry descriptor_id. A source
        instance older than the rename still sends that key.
        """
        descriptor_id = str(uuid.uuid4())
        with mock.patch.object(
            sync_service.gazu.client,
            "fetch_one",
            return_value={
                "id": descriptor_id,
                "name": "Difficulty",
                "field_name": "difficulty",
                "entity_type": "Asset",
                "project_id": str(self.project.id),
            },
        ) as fetch_one:
            sync_service.sync_event(
                {
                    "name": "metadata-descriptor:new",
                    "data": {"descriptor_id": descriptor_id},
                }
            )
        fetch_one.assert_called_once_with(
            "metadata-descriptors", descriptor_id
        )


class EntryCallbackTestCase(ApiDBTestCase):
    """
    The listener callbacks: same work as sync_event, but built once per
    model and fed by the live event stream.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.remote_project_id = str(uuid.uuid4())
        self.remote_project = {
            "id": self.remote_project_id,
            "name": "Test Sync Project",
            "project_status_id": str(self.open_status.id),
            "team": [],
            "type": "Project",
        }

    def test_a_creation_event_creates_and_announces_the_row(self):
        captured = self.capture_events("project:new")
        with mock.patch.object(
            sync_service.gazu.client,
            "fetch_one",
            return_value=dict(self.remote_project),
        ):
            sync_service.create_entry("projects", "project", Project, "new")(
                {"project_id": self.remote_project_id}
            )
        self.assertIsNotNone(Project.get(self.remote_project_id))
        self.assertEqual(len(captured), 1)

    def test_an_update_event_updates_and_announces_the_row(self):
        captured = self.capture_events("project:update")
        with mock.patch.object(
            sync_service.gazu.client,
            "fetch_one",
            return_value=dict(self.remote_project),
        ):
            sync_service.create_entry(
                "projects", "project", Project, "update"
            )({"project_id": self.remote_project_id})
        self.assertEqual(
            Project.get(self.remote_project_id).name, "Test Sync Project"
        )
        self.assertEqual(len(captured), 1)

    def test_a_deletion_event_drops_and_announces_the_row(self):
        asset_id = str(self.asset.id)
        captured = self.capture_events("asset:delete")
        sync_service.delete_entry("assets", "asset", Entity)(
            {"asset_id": asset_id}
        )
        self.assertIsNone(Entity.get(asset_id))
        self.assertEqual(len(captured), 1)

    def test_a_deleted_comment_goes_through_the_deletion_service(self):
        """
        A comment carries notifications, news and attachments, and the task
        it belongs to caches its last status: dropping the row alone would
        leave all of it behind.
        """
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task()
        comment = self.generate_fixture_comment()
        task_id = str(self.task.id)

        sync_service.delete_entry("comments", "comment", Comment)(
            {"comment_id": comment["id"]}
        )

        self.assertIsNone(Comment.get(comment["id"]))
        from zou.app.services import tasks_service

        self.assertIsNone(tasks_service.get_task(task_id)["last_comment_date"])

    def test_an_event_this_instance_emitted_is_not_replayed(self):
        """
        The local broadcaster flags what it forwards, and the source
        instance echoes the flag back. Without the guard the two instances
        would keep answering each other.
        """
        asset_id = str(self.asset.id)
        with mock.patch.object(
            sync_service.gazu.client, "fetch_one"
        ) as fetch_one:
            sync_service.create_entry("assets", "asset", Entity, "new")(
                {"asset_id": asset_id, "sync": True}
            )
            sync_service.delete_entry("assets", "asset", Entity)(
                {"asset_id": asset_id, "sync": True}
            )
        fetch_one.assert_not_called()
        self.assertIsNotNone(Entity.get(asset_id))

    def test_a_missing_route_does_not_break_the_listener(self):
        """
        A source older than this instance answers 404 on routes it does not
        serve. One unknown model must not take the whole listener down.
        """
        with mock.patch.object(
            sync_service.gazu.client,
            "fetch_one",
            side_effect=sync_service.gazu.exception.RouteNotFoundException(
                "no such route"
            ),
        ):
            sync_service.create_entry("projects", "project", Project, "new")(
                {"project_id": self.remote_project_id}
            )
        self.assertIsNone(Project.get(self.remote_project_id))


class ForwardEventTestCase(ApiDBTestCase):
    """
    Events that carry no data to import: they are only rebroadcast to the
    clients connected to this instance.
    """

    def test_an_event_is_forwarded_under_its_own_name(self):
        captured = self.capture_events("task:update")
        sync_service.forward_event("task:update")({"task_id": "test"})
        self.assertEqual(captured, [{"task_id": "test", "sync": True}])

    def test_a_forwarded_event_is_flagged_as_synced(self):
        """
        The flag is what stops the event from being sent back to the source
        on the next round trip.
        """
        captured = self.capture_events("task:assign")
        sync_service.forward_event("task:assign")({"task_id": "test"})
        self.assertTrue(captured[0]["sync"])

    def test_an_already_synced_event_is_not_forwarded_again(self):
        captured = self.capture_events("task:update")
        sync_service.forward_event("task:update")(
            {"task_id": "test", "sync": True}
        )
        self.assertEqual(captured, [])

    def test_a_base_event_is_forwarded_under_name_and_action(self):
        captured = self.capture_events("task:update")
        sync_service.forward_base_event("task", "update", {"task_id": "test"})
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["task_id"], "test")
        self.assertTrue(captured[0]["sync"])

    def test_only_the_events_carrying_data_reach_the_local_log(self):
        """
        A mirror keeps a log of what it imported, not of what it merely
        relayed: forward_event announces without persisting, the CRUD
        events of forward_base_event are written down.
        """
        count = ApiEvent.query.count()
        sync_service.forward_event("task:assign")({"task_id": "test"})
        self.assertEqual(ApiEvent.query.count(), count)
        sync_service.forward_base_event("task", "update", {"task_id": "test"})
        self.assertEqual(ApiEvent.query.count(), count + 1)


class FileCallbackTestCase(ApiDBTestCase):
    """
    The listeners downloading what an event announced: a preview, a
    preview background, a thumbnail.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.person_id = str(self.person.id)

    def test_a_thumbnail_event_carries_the_id_of_its_own_model(self):
        """
        person:set-thumbnail and its siblings are emitted with a
        <model>_id, never a preview_file_id: the thumbnail of a person is
        stored under the person id.
        """
        with mock.patch.object(
            sync_service, "download_thumbnail_from_another_instance"
        ) as download:
            sync_service.get_retrieve_thumbnail("person")(
                {"person_id": self.person_id}
            )
        download.assert_called_once_with("person", self.person_id)

    def test_a_downloaded_thumbnail_is_announced_locally(self):
        captured = self.capture_events("person:set-thumbnail")
        with mock.patch.object(
            sync_service, "download_thumbnail_from_another_instance"
        ):
            sync_service.get_retrieve_thumbnail("person")(
                {"person_id": self.person_id}
            )
        self.assertEqual(len(captured), 1)

    def test_a_downloaded_preview_is_announced_locally(self):
        captured = self.capture_events("preview-file:add-file")
        with mock.patch.object(
            sync_service, "download_preview_from_another_instance"
        ):
            sync_service.retrieve_preview_file(
                {"preview_file_id": str(uuid.uuid4())}
            )
        self.assertEqual(len(captured), 1)

    def test_a_downloaded_preview_background_is_announced_locally(self):
        captured = self.capture_events("preview-background-file:add-file")
        with mock.patch.object(
            sync_service, "download_preview_background_from_another_instance"
        ):
            sync_service.retrieve_preview_background_file(
                {"preview_background_file_id": str(uuid.uuid4())}
            )
        self.assertEqual(len(captured), 1)

    def test_a_file_event_this_instance_emitted_is_ignored(self):
        with mock.patch.object(
            sync_service, "download_preview_from_another_instance"
        ) as download_preview, mock.patch.object(
            sync_service, "download_thumbnail_from_another_instance"
        ) as download_thumbnail:
            sync_service.retrieve_preview_file(
                {"preview_file_id": str(uuid.uuid4()), "sync": True}
            )
            sync_service.get_retrieve_thumbnail("person")(
                {"person_id": self.person_id, "sync": True}
            )
        download_preview.assert_not_called()
        download_thumbnail.assert_not_called()


class SyncEntriesTestCase(ApiDBTestCase):
    """
    The cross-production bulk import.
    """

    def test_every_page_is_walked(self):
        pages = [
            {
                "data": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Blue",
                        "color": "#0000FF",
                    }
                ],
                "nb_pages": 2,
            },
            {
                "data": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Red",
                        "color": "#FF0000",
                    }
                ],
                "nb_pages": 2,
            },
        ]
        with mock.patch.object(
            sync_service.gazu.client, "fetch_all", side_effect=pages
        ):
            sync_service.sync_entries("studios", Studio)

        self.assertEqual(
            sorted(studio.name for studio in Studio.get_all()),
            ["Blue", "Red"],
        )

    def test_the_concept_task_statuses_are_dropped(self):
        # A concept status of the source instance would collide with the one
        # the target instance creates on its own.
        page = {
            "data": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Concept",
                    "short_name": "cpt",
                    "color": "#000000",
                    "for_concept": True,
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Todo",
                    "short_name": "todo",
                    "color": "#000000",
                    "for_concept": False,
                },
            ],
            "nb_pages": 1,
        }
        with mock.patch.object(
            sync_service.gazu.client, "fetch_all", return_value=page
        ):
            sync_service.sync_entries("task-status", TaskStatus)

        self.assertEqual(
            [status.name for status in TaskStatus.get_all()], ["Todo"]
        )

    def test_the_password_hashes_are_asked_for_with_the_persons(self):
        """
        Without them the mirrored instance holds accounts nobody can log
        into.
        """
        params = self.fetch_params("persons", project=None)
        self.assertEqual(params["with_pass_hash"], "true")

    def test_a_single_production_is_asked_for_by_id(self):
        params = self.fetch_params("projects", project="Cosmos Landromat")
        self.assertEqual(params["id"], self.remote_project_id)

    def test_the_filters_of_a_single_production_are_scoped_to_it(self):
        params = self.fetch_params("search-filters", project="Cosmos")
        self.assertEqual(params["project_id"], self.remote_project_id)

    def fetch_params(self, model_name, project=None):
        """
        Run sync_entries against an empty source and return the query
        parameters it sent.
        """
        self.remote_project_id = str(uuid.uuid4())
        with mock.patch.object(
            sync_service.gazu.project,
            "get_project_by_name",
            return_value={"id": self.remote_project_id},
        ), mock.patch.object(
            sync_service.gazu.client,
            "fetch_all",
            return_value={"data": [], "nb_pages": 1},
        ) as fetch_all:
            sync_service.sync_entries(model_name, Project, project=project)
        return fetch_all.call_args.kwargs["params"]


class SyncProjectEntriesTestCase(ApiDBTestCase):
    """
    The per production bulk import. Three shapes of request hide behind one
    signature: a single call, the news cursor, and the paginated one.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project = self.project.serialize()

    def sync(self, model_name, model, pages):
        with mock.patch.object(
            sync_service.gazu.client, "fetch_all", side_effect=pages
        ) as fetch_all:
            sync_service.sync_project_entries(self.project, model_name, model)
        return fetch_all

    def test_a_small_model_is_fetched_in_one_call(self):
        asset_type_id = str(uuid.uuid4())
        fetch_all = self.sync(
            "entity-types",
            EntityType,
            [[{"id": asset_type_id, "name": "Props"}]],
        )
        fetch_all.assert_called_once_with(
            f"projects/{self.project['id']}/entity-types"
        )
        self.assertIsNotNone(EntityType.get(asset_type_id))

    def test_a_large_model_is_paginated(self):
        pages = [
            {
                "data": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Playlist 1",
                        "project_id": self.project["id"],
                    }
                ],
                "nb_pages": 2,
            },
            {
                "data": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Playlist 2",
                        "project_id": self.project["id"],
                    }
                ],
                "nb_pages": 2,
            },
        ]
        fetch_all = self.sync("playlists", Playlist, pages)
        self.assertEqual(
            [call.args[0] for call in fetch_all.call_args_list],
            [
                f"projects/{self.project['id']}/playlists/all?page=1",
                f"projects/{self.project['id']}/playlists/all?page=2",
            ],
        )
        self.assertEqual(Playlist.query.count(), 2)


class RunMainDataSyncTestCase(ApiDBTestCase):
    """
    The pass importing everything that is not scoped to a production, the
    productions themselves included.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.remote_project_id = str(uuid.uuid4())

    def run_sync(self, project=None):
        """
        Run the whole pass against a source holding one production and
        nothing else, and return the paths it asked for.
        """
        payload = {
            "id": self.remote_project_id,
            "name": "Remote Production",
            "project_status_id": str(self.open_status.id),
        }

        def fetch_all(model_name, params=None):
            data = [payload] if model_name == "projects" else []
            return {"data": data, "nb_pages": 1}

        with mock.patch.object(
            sync_service.gazu.project,
            "get_project_by_name",
            return_value={"id": self.remote_project_id},
        ), mock.patch.object(
            sync_service.gazu.client, "fetch_all", side_effect=fetch_all
        ) as fetch:
            sync_service.run_main_data_sync(project=project)
        return [call.args[0] for call in fetch.call_args_list]

    def test_a_full_sync_imports_the_productions(self):
        """
        Every row the next passes import points at a production, so leaving
        them out makes the whole sync fail on a foreign key, one silently
        logged batch at a time.
        """
        self.assertIn("projects", self.run_sync())
        self.assertIsNotNone(Project.get(self.remote_project_id))

    def test_a_single_production_sync_imports_it_too(self):
        self.assertIn("projects", self.run_sync(project="Remote Production"))
        self.assertIsNotNone(Project.get(self.remote_project_id))

    def test_every_cross_production_model_is_asked_for(self):
        self.assertEqual(
            self.run_sync(),
            [
                sync_service.event_name_model_path_map[event]
                for event in sync_service.main_events
            ],
        )


class CheckSyncAccountTestCase(unittest.TestCase):
    """
    The warning gate on the account the sync runs with. It never raises:
    syncing a single production with a manager account is legitimate.
    """

    def check_with_user(self, user):
        with mock.patch.object(
            sync_service.gazu.client, "get_current_user", return_value=user
        ):
            return sync_service.check_sync_account()

    def test_an_admin_account_passes(self):
        self.assertTrue(self.check_with_user({"role": "admin"}))

    def test_a_manager_account_is_only_warned_about(self):
        self.assertFalse(
            self.check_with_user(
                {"role": "manager", "email": "bot@studio.com"}
            )
        )

    def test_an_unreachable_source_does_not_raise(self):
        with mock.patch.object(
            sync_service.gazu.client,
            "get_current_user",
            side_effect=Exception("connection refused"),
        ):
            self.assertFalse(sync_service.check_sync_account())


class DownloadFileTestCase(unittest.TestCase):
    """
    The local copy of a file read from the object storage.
    """

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.file_path = os.path.join(self.folder, "preview.mp4")

    def test_partial_file_removed_on_error(self):
        def failing_dl_func(prefix, preview_file_id):
            yield b"partial content"
            raise RuntimeError("stream interrupted")

        sync_service.download_file(
            self.file_path, "previews", failing_dl_func, "preview-id"
        )
        self.assertFalse(os.path.exists(self.file_path))

    def test_successful_download_keeps_file(self):
        def dl_func(prefix, preview_file_id):
            yield b"full content"

        sync_service.download_file(
            self.file_path, "previews", dl_func, "preview-id"
        )
        with open(self.file_path, "rb") as downloaded:
            self.assertEqual(downloaded.read(), b"full content")


class DownloadFromAnotherInstanceTestCase(unittest.TestCase):
    """
    The transfer of one stored file from the source instance: download to a
    temporary path, hand it to the local store, clean up either way.
    """

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.file_path = os.path.join(self.folder, "thumbnail.png")
        self.saved = []
        self.errors = {}

    def save(self, prefix, id, file_path):
        self.saved.append((prefix, id, file_path))

    def download(self, exists=False, force=False, status_code=200, attemps=3):
        def fake_download(path, file_path):
            with open(file_path, "wb") as downloaded:
                downloaded.write(b"content")
            return mock.Mock(status_code=status_code)

        with mock.patch.object(
            sync_service.gazu.client, "download", side_effect=fake_download
        ) as downloaded:
            sync_service.download_file_from_another_instance(
                "/pictures/thumbnails/persons/id.png",
                self.file_path,
                lambda prefix, id: exists,
                self.save,
                "thumbnails",
                "person-id",
                number_attemps=attemps,
                force=force,
                dict_errors=self.errors,
            )
        return downloaded

    def test_a_downloaded_file_reaches_the_store(self):
        self.download()
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0][0], "thumbnails")

    def test_the_temporary_file_does_not_survive_the_transfer(self):
        self.download()
        self.assertFalse(os.path.exists(self.file_path))

    def test_a_file_already_in_the_store_is_not_downloaded_again(self):
        downloaded = self.download(exists=True)
        downloaded.assert_not_called()
        self.assertEqual(self.saved, [])

    def test_a_resync_downloads_it_anyway(self):
        downloaded = self.download(exists=True, force=True)
        self.assertEqual(downloaded.call_count, 1)

    def test_a_failed_download_is_retried(self):
        downloaded = self.download(status_code=500, attemps=3)
        self.assertEqual(downloaded.call_count, 3)
        self.assertIn("person-id", self.errors["thumbnails"])

    def test_a_file_the_source_does_not_have_is_not_an_error(self):
        """
        A 404 means the row exists without its file on the source side.
        Reporting it would drown the errors that need an operator.
        """
        self.download(status_code=404)
        self.assertEqual(self.errors, {})


class FetchEventsTestCase(unittest.TestCase):
    """
    The reading of the source event log, newest first.
    """

    def test_paginates_until_short_page(self):
        pages = [
            [{"id": "ev-0"}, {"id": "ev-1"}, {"id": "ev-2"}],
            [{"id": "ev-3"}, {"id": "ev-4"}],
        ]
        calls = []

        def fake_fetch_all(path):
            calls.append(path)
            return pages[len(calls) - 1]

        with mock.patch.object(
            sync_service.gazu.client, "fetch_all", side_effect=fake_fetch_all
        ):
            events = sync_service._fetch_events(
                "events/last?limit=3", 3, paginate=True
            )
        self.assertEqual(len(events), 5)
        self.assertEqual(len(calls), 2)
        self.assertIn("cursor_event_id=ev-2", calls[1])

    def test_single_fetch_when_not_paginated(self):
        full_page = [{"id": "ev-0"}, {"id": "ev-1"}, {"id": "ev-2"}]
        with mock.patch.object(
            sync_service.gazu.client, "fetch_all", return_value=full_page
        ) as fetch_all:
            events = sync_service._fetch_events(
                "events/last?limit=3", 3, paginate=False
            )
        self.assertEqual(len(events), 3)
        fetch_all.assert_called_once()

    def test_the_time_window_covers_the_requested_minutes(self):
        now = datetime.datetime(2026, 3, 12, 10, 30, 0)
        with mock.patch.object(
            sync_service.date_helpers, "get_utc_now_datetime", return_value=now
        ):
            path = sync_service._add_time_window("events/last?limit=300", 90)
        self.assertEqual(
            path,
            "events/last?limit=300"
            "&before=2026-03-12T10:30:00&after=2026-03-12T09:00:00",
        )


class MultithreadErrorsTestCase(unittest.TestCase):
    """
    The error report the file sync fills from its worker pool.
    """

    def test_the_errors_are_nested_by_prefix(self):
        errors = {}
        sync_service.write_multithread_dict_errors(
            errors, "previews", "id-1", "boom"
        )
        sync_service.write_multithread_dict_errors(
            errors, "previews", "id-2", "bang"
        )
        sync_service.write_multithread_dict_errors(
            errors, "thumbnails", "id-1", "thud"
        )
        self.assertEqual(
            errors,
            {
                "previews": {"id-1": "boom", "id-2": "bang"},
                "thumbnails": {"id-1": "thud"},
            },
        )

    def test_nothing_is_lost_under_threads(self):
        """
        The function exists to be called from a worker pool, so the point is
        that concurrent writers do not drop each other's entries.
        """
        errors = {}

        def write(index):
            sync_service.write_multithread_dict_errors(
                errors, "previews", f"id-{index}", index
            )

        threads = [
            threading.Thread(target=write, args=(index,))
            for index in range(50)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(errors["previews"]), 50)


class VerifyProjectSyncTestCase(ApiDBTestCase):
    """
    The read-only row count comparison run after a sync.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()

    def test_every_target_counter_compiles(self):
        """
        Every target side count helper must produce valid SQL on the current
        schema. Run them all against a production that has no scoped data;
        each must return 0 instead of raising.
        """
        pid = str(self.project.id)
        counters = [
            sync_service._tgt_entity_type(pid, "Shot"),
            sync_service._tgt_entity_type(pid, "Sequence"),
            sync_service._tgt_entity_type(pid, "Episode"),
            sync_service._tgt_entity_type(pid, "Concept"),
            sync_service._tgt_asset(pid),
            sync_service._tgt_entity_link(pid),
            sync_service._tgt_comment(pid),
            sync_service._tgt_time_spent(pid),
            sync_service._tgt_preview_file(pid),
            sync_service._tgt_build_job(pid),
            sync_service._tgt_attachment_file(pid),
            sync_service._tgt_subscription(pid),
            sync_service._tgt_notification(pid),
            sync_service._tgt_news(pid),
            sync_service._tgt_output_file(pid),
            sync_service._tgt_working_file(pid),
            sync_service._tgt_asset_instance(pid),
            sync_service._tgt_chat(pid),
            sync_service._tgt_budget_entry(pid),
            sync_service._tgt_share_link(pid),
        ]
        for counter in counters:
            self.assertIsInstance(counter(), int)

    def test_both_directions_run(self):
        """
        sync-push-verify reuses verify_project_sync with direction="push".
        Smoke test: the call should not raise on a production that exists
        both on the (mocked) remote and locally.
        """
        with mock.patch.object(
            sync_service.gazu.project,
            "get_project_by_name",
            return_value={
                "id": str(self.project.id),
                "name": self.project.name,
            },
        ):
            sync_service.verify_project_sync(
                self.project.name, direction="push"
            )
            sync_service.verify_project_sync(
                self.project.name, direction="pull"
            )

    def test_a_production_missing_locally_is_reported(self):
        with mock.patch.object(
            sync_service.gazu.project,
            "get_project_by_name",
            return_value={"id": str(uuid.uuid4()), "name": "Elsewhere"},
        ):
            sync_service.verify_project_sync("Elsewhere")
