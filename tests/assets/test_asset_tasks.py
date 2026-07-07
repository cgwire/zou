import orjson

from tests.base import ApiDBTestCase

from zou.app.models.entity import EntityLink
from zou.app.services import (
    projects_service,
    tasks_service,
    assets_service,
    persons_service,
)


def rebuild_from_compact(asset_fields, task_fields, rows):
    """
    Reverse the compact encoding by mapping positional values back to
    field names, as a client is expected to do.
    """
    assets = []
    for row in rows:
        asset = dict(zip(asset_fields, row))
        asset["tasks"] = [
            dict(zip(task_fields, task_row)) for task_row in asset["tasks"]
        ]
        assets.append(asset)
    return assets


class AssetTasksTestCase(ApiDBTestCase):
    def setUp(self):
        super(AssetTasksTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task_status()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()
        self.generate_fixture_task()
        self.generate_fixture_metadata_descriptor()
        self.person_id = str(self.person.id)
        self.asset_id = self.asset.id
        self.meta_descriptor_id = self.meta_descriptor.id
        self.department_id = self.department.id
        self.task_type_dict = self.task_type.serialize()

    def test_get_tasks_for_asset(self):
        tasks = self.get(f"data/assets/{self.asset.id}/tasks")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.task.id))

    def test_get_assets_and_tasks(self):
        self.generate_fixture_task(name="Secondary")
        assets = self.get("data/assets/with-tasks")
        self.assertEqual(len(assets), 1)
        self.assertEqual(len(assets[0]["tasks"]), 2)
        self.assertEqual(
            assets[0]["tasks"][0]["assignees"][0], str(self.person_id)
        )

    def test_get_assets_and_tasks_compact(self):
        self.generate_fixture_task(name="Secondary")
        reference = self.get("data/assets/with-tasks")
        payload = self.get("data/assets/with-tasks?compact=true")
        self.assertTrue(payload["compact"])
        rebuilt = rebuild_from_compact(
            payload["asset_fields"], payload["task_fields"], payload["rows"]
        )
        self.assertEqual(rebuilt, reference)

    def test_get_assets_and_tasks_stream(self):
        self.generate_fixture_task(name="Secondary")
        reference = self.get("data/assets/with-tasks")
        response = self.app.get(
            "data/assets/with-tasks?stream=true", headers=self.base_headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/x-ndjson")
        lines = response.data.decode("utf-8").strip().split("\n")
        header = orjson.loads(lines[0])
        self.assertFalse(header["compact"])
        assets = [orjson.loads(line) for line in lines[1:]]
        self.assertEqual(assets, reference)

    def test_get_assets_and_tasks_stream_compact(self):
        self.generate_fixture_task(name="Secondary")
        reference = self.get("data/assets/with-tasks")
        response = self.app.get(
            "data/assets/with-tasks?stream=true&compact=true",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 200)
        lines = response.data.decode("utf-8").strip().split("\n")
        header = orjson.loads(lines[0])
        self.assertTrue(header["compact"])
        rebuilt = rebuild_from_compact(
            header["asset_fields"],
            header["task_fields"],
            [orjson.loads(line) for line in lines[1:]],
        )
        self.assertEqual(rebuilt, reference)

    def test_get_assets_and_tasks_episode_filter(self):
        """
        An asset both sourced from an episode and cast in it through an
        entity link must come back exactly once with its tasks, and an
        asset unrelated to the episode must not come back at all.
        """
        self.generate_fixture_episode("E01")
        episode_id = str(self.episode.id)
        self.asset.update({"source_id": self.episode.id})
        EntityLink.create(
            entity_in_id=self.episode.id, entity_out_id=self.asset.id
        )
        self.generate_fixture_asset_character()

        assets = assets_service.get_assets_and_tasks(
            {"episode_id": episode_id}
        )
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["id"], str(self.asset_id))
        self.assertEqual(len(assets[0]["tasks"]), 1)
        self.assertEqual(
            assets[0]["tasks"][0]["assignees"], [str(self.person_id)]
        )

        main_assets = assets_service.get_assets_and_tasks(
            {"episode_id": "main"}
        )
        self.assertEqual(len(main_assets), 1)
        self.assertEqual(main_assets[0]["id"], str(self.asset_character.id))

    def test_get_assets_and_tasks_vendor(self):
        self.generate_fixture_task(name="Secondary")
        self.generate_fixture_user_vendor()
        task_id = self.task.id
        project_id = self.project.id
        person_id = self.user_vendor["id"]
        self.log_in_vendor()
        assets = self.get(
            f"data/assets/with-tasks?project_id={project_id}", 403
        )
        projects_service.add_team_member(project_id, person_id)
        projects_service.clear_project_cache(str(project_id))
        assets = self.get(f"data/assets/with-tasks?project_id={project_id}")
        self.assertEqual(len(assets), 0)
        tasks_service.assign_task(task_id, person_id)
        assets = self.get(f"data/assets/with-tasks?project_id={project_id}")
        self.assertEqual(len(assets), 1)
        self.assertEqual(len(assets[0]["tasks"]), 1)
        self.assertTrue(str(person_id) in assets[0]["tasks"][0]["assignees"])

        assets_service.update_asset(
            self.asset_id, {"data": {"contractor": "test"}}
        )
        assets = self.get(f"data/assets/with-tasks?project_id={project_id}")
        self.assertEqual(assets[0]["data"]["contractor"], "test")

        projects_service.update_metadata_descriptor(
            self.meta_descriptor_id, {"departments": [self.department_id]}
        )
        persons_service.add_to_department(str(self.department_id), person_id)
        assets = self.get(f"data/assets/with-tasks?project_id={project_id}")
        self.assertEqual(assets[0]["data"]["contractor"], "test")

        persons_service.remove_from_department(
            str(self.department_id), person_id
        )
        assets = self.get(f"data/assets/with-tasks?project_id={project_id}")
        self.assertTrue("contractor" not in assets[0]["data"])

    def test_get_task_types_for_asset(self):
        task_types = self.get(f"data/assets/{self.asset_id}/task-types")
        self.assertEqual(len(task_types), 1)
        self.assertDictEqual(task_types[0], self.task_type_dict)

    def test_get_task_types_for_asset_not_found(self):
        self.get("data/assets/no-asset/task-types", 404)
