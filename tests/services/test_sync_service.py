import unittest
import uuid

from unittest import mock

import gazu

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.studio import Studio
from zou.app.models.task_status import TaskStatus
from zou.app.services import sync_service
from zou.app.utils import events


class SyncServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(SyncServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

        self.last_event_data = {}
        events.unregister_all()
        self.new_project_id = str(uuid.uuid4())

        self.real_fetch_one = gazu.client.fetch_one

        def fetch_one_mock(model_name, model_id):
            return {
                "id": self.new_project_id,
                "name": "Test Sync Project",
                "project_status_id": str(self.open_status.id),
                "team": [],
                "type": "Project",
            }

        gazu.client.fetch_one = fetch_one_mock

    def tearDown(self):
        super(SyncServiceTestCase, self).tearDown()
        gazu.client.fetch_one = self.real_fetch_one

    def handle_event(self, data={}):
        self.last_event_data = data

    def test_sync_event(self):
        sync_service.sync_event(
            {
                "name": "project:new",
                "data": {"project_id": self.new_project_id},
            }
        )
        self.assertIsNotNone(Project.get(self.new_project_id))
        sync_service.sync_event(
            {
                "name": "project:delete",
                "data": {"project_id": self.new_project_id},
            }
        )
        self.assertIsNone(Project.get(self.new_project_id))

    def test_create_entry(self):
        events.register("project:new", "handle_event", self)
        create_func = sync_service.create_entry(
            "projects", "project", Project, "new"
        )
        create_func({"project_id": self.new_project_id})
        self.assertTrue("project_id" in self.last_event_data)
        self.assertIsNotNone(Project.get(self.last_event_data["project_id"]))

        self.last_event_data = {}
        events.unregister_all()
        events.register("project:update", "handle_event", self)
        create_func = sync_service.create_entry(
            "projects", "project", Project, "update"
        )
        create_func({"project_id": self.new_project_id})
        self.assertTrue("project_id" in self.last_event_data)
        project = Project.get(self.last_event_data["project_id"])
        self.assertEqual(project.name, "Test Sync Project")

    def test_delete_entry(self):
        asset_id = str(self.asset.id)
        events.register("asset:delete", "handle_event", self)
        delete_func = sync_service.delete_entry("assets", "asset", Entity)
        delete_func({"asset_id": asset_id})
        self.assertIsNone(Entity.get(asset_id))
        self.assertTrue("asset_id" in self.last_event_data)

    def test_forward_event(self):
        events.register("task:update", "handle_event", self)
        forward_func = sync_service.forward_event("task:update")
        forward_func({"task_id": "test"})
        self.assertTrue("task_id" in self.last_event_data)

    def test_forward_base_event(self):
        events.register("task:update", "handle_event", self)
        sync_service.forward_base_event("task", "update", {"task_id": "test"})
        self.assertTrue("task_id" in self.last_event_data)

    def test_verify_target_counters_compile(self):
        """
        Every target-side count helper for sync-verify must produce valid
        SQL on the current schema. Run them all against a project that has
        no scoped data; each must return 0 instead of raising.
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

    def test_verify_project_sync_accepts_push_direction(self):
        """
        sync-push-verify reuses verify_project_sync with direction="push".
        Smoke test: the call should not raise on a project that exists both
        on the (mocked) remote and locally.
        """
        project_name = self.project.name

        real_get = gazu.project.get_project_by_name

        def fake_get(name):
            return {"id": str(self.project.id), "name": name}

        gazu.project.get_project_by_name = fake_get
        try:
            sync_service.verify_project_sync(project_name, direction="push")
            sync_service.verify_project_sync(project_name, direction="pull")
        finally:
            gazu.project.get_project_by_name = real_get

    def test_every_synced_event_has_a_path_and_a_model(self):
        """
        add_main_sync_listeners and add_project_sync_listeners read both maps
        for every event of their list. A name added to a list without an
        entry in the maps raises KeyError when the sync starts, which is a
        place nobody watches.
        """
        listened = list(sync_service.main_events) + list(
            sync_service.project_events
        )
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

    def test_write_multithread_dict_errors_nests_by_prefix(self):
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

    def test_write_multithread_dict_errors_loses_nothing_under_threads(self):
        """
        The function exists to be called from a worker pool, so the point is
        that concurrent writers do not drop each other's entries.
        """
        import threading

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


class SyncEntriesTestCase(ApiDBTestCase):
    def test_sync_entries_walks_every_page(self):
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

    def test_sync_entries_drops_the_concept_task_statuses(self):
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
