import datetime
import unittest
import uuid

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.event import ApiEvent
from zou.app.models.news import News
from zou.app.models.entity_type import EntityType
from zou.app.models.playlist import Playlist
from zou.app.models.project import Project
from zou.app.models.studio import Studio
from zou.app.models.task_status import TaskStatus
from zou.app.commands import (
    sync_service,
)
from zou.app.services import news_service


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
        A comment carries the news of the status it set, its notifications
        and its attachments. Dropping the row alone leaves all of it behind,
        pointing at a comment that no longer exists.
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
        # The news is written by the comment route, not by the service the
        # fixture calls: post it here as the route would.
        news_service.create_news_for_task_and_comment(
            self.task.serialize(), comment
        )
        self.assertEqual(
            News.query.filter_by(comment_id=comment["id"]).count(), 1
        )

        sync_service.delete_entry("comments", "comment", Comment)(
            {"comment_id": comment["id"]}
        )

        self.assertIsNone(Comment.get(comment["id"]))
        self.assertEqual(
            News.query.filter_by(comment_id=comment["id"]).count(), 0
        )

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

    def test_a_single_production_keeps_its_relations(self):
        """
        The team, the task types, the task statuses and the asset types of
        a production only come with the relations. Scoping the request to
        one production replaced the parameters instead of adding to them,
        and the production landed with an empty team and no task type.
        """
        params = self.fetch_params("projects", project="Cosmos Landromat")
        self.assertEqual(params["relations"], "true")

    def test_the_filters_of_a_single_production_are_scoped_to_it(self):
        params = self.fetch_params("search-filters", project="Cosmos")
        self.assertEqual(params["project_id"], self.remote_project_id)
        self.assertEqual(params["relations"], "true")

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
