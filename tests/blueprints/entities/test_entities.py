from tests.base import ApiDBTestCase
from zou.app.models.entity import EntityConceptLink
from zou.app.models.time_spent import TimeSpent
from zou.app.services import (
    comments_service,
    news_service,
    projects_service,
    tasks_service,
)
from zou.app.utils import fields


class EntityRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_task()

    def test_get_entity_news(self):
        result = self.get(f"/data/entities/{self.asset.id}/news")
        self.assertEqual(result["data"], [])

    def test_get_entity_news_with_comment(self):
        comment = comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.user["id"]),
            "Test comment",
        )
        task_dict = self.task.serialize()
        news_service.create_news_for_task_and_comment(task_dict, comment)
        result = self.get(f"/data/entities/{self.asset.id}/news")
        self.assertEqual(len(result["data"]), 1)

    def test_get_entity_preview_files(self):
        result = self.get(f"/data/entities/{self.asset.id}/preview-files")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_get_entity_preview_files_with_data(self):
        self.generate_fixture_preview_file()
        result = self.get(f"/data/entities/{self.asset.id}/preview-files")
        self.assertGreater(len(result), 0)

    def test_get_entity_time_spents(self):
        result = self.get(f"/data/entities/{self.asset.id}/time-spents")
        self.assertEqual(result, [])

    def test_get_entity_time_spents_with_data(self):
        TimeSpent.create(
            person_id=self.person.id,
            task_id=self.task.id,
            date="2024-01-15",
            duration=120,
        )
        result = self.get(f"/data/entities/{self.asset.id}/time-spents")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["duration"], 120)

    def test_entity_listings_paginate(self):
        """
        The preview files and time spents of an entity answer the plain
        list without page nor limit, and the paginated envelope with them.
        """
        for revision in [1, 2, 3]:
            self.generate_fixture_preview_file(revision=revision)
        for day in ["2024-01-15", "2024-01-16", "2024-01-17"]:
            TimeSpent.create(
                person_id=self.person.id,
                task_id=self.task.id,
                date=day,
                duration=120,
            )
        for route in ["preview-files", "time-spents"]:
            path = f"/data/entities/{self.asset.id}/{route}"
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)
                full = self.assert_pages_match_full_list(path, limit=2)
                self.assertEqual(len(full), 3)

    def test_entity_news_paginate(self):
        """
        Without page nor limit the entity news keep their single page of
        2000 entries. With them, the requested page is returned.
        """
        for text in ["First", "Second", "Third"]:
            comment = comments_service.new_comment(
                str(self.task.id),
                str(self.task_status.id),
                str(self.user["id"]),
                text,
            )
            news_service.create_news_for_task_and_comment(
                self.task.serialize(), comment
            )
        path = f"/data/entities/{self.asset.id}/news"
        full = self.get(path)
        self.assertEqual(full["limit"], 2000)
        self.assertEqual(full["page"], 1)
        self.assertEqual(full["total"], 3)
        ids = []
        for page in [1, 2, 3]:
            result = self.get(f"{path}?page={page}&limit=1")
            self.assertEqual(result["total"], 3)
            self.assertEqual(result["limit"], 1)
            self.assertEqual(result["page"], page)
            ids += [news["id"] for news in result["data"]]
        self.assertEqual(ids, [news["id"] for news in full["data"]])
        first_page = self.get(f"{path}?limit=2")
        self.assertEqual(first_page["page"], 1)
        self.assertEqual(len(first_page["data"]), 2)

    def test_get_entities_linked_with_tasks(self):
        result = self.get(
            f"/data/entities/{self.asset.id}/entities-linked/with-tasks"
        )
        self.assertEqual(result, [])

    def test_get_entities_linked_with_tasks_with_link(self):
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        EntityConceptLink.create(
            entity_in_id=self.shot.id,
            entity_out_id=self.asset.id,
        )
        result = self.get(
            f"/data/entities/{self.asset.id}/entities-linked/with-tasks"
        )
        self.assertGreater(len(result), 0)

    def test_get_entities_linked_with_tasks_paginated(self):
        self.generate_fixture_sequence()
        for name in ["P01", "P02", "P03"]:
            shot = self.generate_fixture_shot(name)
            self.generate_fixture_shot_task(name="Main", shot_id=shot.id)
            self.generate_fixture_shot_task(name="Extra", shot_id=shot.id)
            EntityConceptLink.create(
                entity_in_id=shot.id, entity_out_id=self.asset.id
            )
        path = f"/data/entities/{self.asset.id}/entities-linked/with-tasks"
        self.assert_opt_in_pagination(path)
        full = self.assert_pages_match_full_list(path, ordered=False)
        self.assertEqual(len(full), 3)
        self.assertTrue(all(len(row["tasks"]) == 2 for row in full))
        self.assert_pages_match_full_list(path, limit=2, ordered=False)

    def test_linked_entities_with_tasks_follow_the_caller_role(self):
        """
        A vendor gets the linked entities holding a task of theirs, with
        those tasks only, and a client gets the studio fields of the tasks
        blank. Both used to get every task, assignees included.
        """
        self.generate_fixture_sequence()
        shots = []
        for name in ["P01", "P02"]:
            shot = self.generate_fixture_shot(name)
            self.generate_fixture_shot_task(name="Main", shot_id=shot.id)
            self.generate_fixture_shot_task(name="Extra", shot_id=shot.id)
            EntityConceptLink.create(
                entity_in_id=shot.id, entity_out_id=self.asset.id
            )
            shots.append(shot)
        vendor_task = self.shot_task
        path = f"/data/entities/{self.asset.id}/entities-linked/with-tasks"
        project_id = str(self.project.id)

        client_id = self.generate_fixture_user_client()["id"]
        projects_service.add_team_member(project_id, client_id)
        self.log_in_client()
        result = self.get(path)
        self.assertEqual(len(result), 2)
        for task in [task for row in result for task in row["tasks"]]:
            self.assertEqual(task["assignees"], [])
        self.assert_opt_in_pagination(path)

        vendor_id = self.generate_fixture_user_vendor()["id"]
        projects_service.add_team_member(project_id, vendor_id)
        tasks_service.assign_task(self.task.id, vendor_id)
        tasks_service.assign_task(vendor_task.id, vendor_id)
        self.log_in_vendor()
        result = self.get(path)
        self.assertEqual([row["id"] for row in result], [str(shots[1].id)])
        self.assertEqual(
            [task["id"] for task in result[0]["tasks"]], [str(vendor_task.id)]
        )
        self.assert_opt_in_pagination(path)

    def test_delete_entities(self):
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        asset_id = str(self.asset.id)
        shot_id = str(self.shot.id)
        path = f"/actions/projects/{self.project.id}/delete-entities"
        result = self.post(path, [asset_id, shot_id], 200)
        self.assertEqual(result, [asset_id, shot_id])
        # The asset has a task: it is canceled, not removed.
        asset = self.get(f"/data/assets/{asset_id}")
        self.assertTrue(asset["canceled"])
        # The shot has no task: it is removed for real.
        self.get(f"/data/shots/{shot_id}", 404)

    def test_delete_entities_removes_canceled_asset(self):
        self.asset.update({"canceled": True})
        asset_id = str(self.asset.id)
        path = f"/actions/projects/{self.project.id}/delete-entities"
        self.post(path, [asset_id], 200)
        self.get(f"/data/assets/{asset_id}", 404)

    def test_delete_entities_with_force(self):
        # Force removes the entities and their tasks for real, even though
        # they have tasks and were never canceled before.
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        asset_id = str(self.asset.id)
        shot_id = str(self.shot.id)
        asset_task_id = str(self.task.id)
        shot_task_id = str(self.shot_task.id)
        path = (
            f"/actions/projects/{self.project.id}"
            "/delete-entities?force=true"
        )
        result = self.post(path, [asset_id, shot_id], 200)
        self.assertEqual(result, [asset_id, shot_id])
        self.get(f"/data/assets/{asset_id}", 404)
        self.get(f"/data/shots/{shot_id}", 404)
        self.get(f"/data/tasks/{asset_task_id}", 404)
        self.get(f"/data/tasks/{shot_task_id}", 404)

    def test_delete_entities_ignores_absent_entities(self):
        # An id that no longer exists (e.g. deleted by someone else) must not
        # fail the whole batch: it is skipped and the others are processed.
        self.asset.update({"canceled": True})
        asset_id = str(self.asset.id)
        missing_id = str(fields.gen_uuid())
        path = f"/actions/projects/{self.project.id}/delete-entities"
        result = self.post(path, [missing_id, asset_id], 200)
        self.assertEqual(result, [asset_id])
        self.get(f"/data/assets/{asset_id}", 404)

    def test_delete_entities_skips_unsupported_entity_type(self):
        self.generate_fixture_sequence()
        sequence_id = str(self.sequence.id)
        path = f"/actions/projects/{self.project.id}/delete-entities"
        result = self.post(path, [sequence_id], 200)
        # A sequence is not a deletable type: it is skipped, not deleted.
        self.assertEqual(result, [])
        self.get(f"/data/entities/{sequence_id}")

    def test_delete_entities_skips_entity_from_other_project(self):
        asset_id = str(self.asset.id)
        other_project = self.generate_fixture_project(name="Other Project")
        path = f"/actions/projects/{other_project.id}/delete-entities"
        result = self.post(path, [asset_id], 200)
        # The asset belongs to another project: it is skipped, not deleted.
        self.assertEqual(result, [])
        self.get(f"/data/assets/{asset_id}")

    def test_delete_entities_as_artist_is_forbidden(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        path = f"/actions/projects/{self.project.id}/delete-entities"
        self.post(path, [str(self.asset.id)], 403)
