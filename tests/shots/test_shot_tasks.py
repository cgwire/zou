from tests.base import ApiDBTestCase

from zou.app.services import (
    persons_service,
    projects_service,
    tasks_service,
    shots_service,
)


class ShotTasksTestCase(ApiDBTestCase):
    def setUp(self):
        super(ShotTasksTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task_status()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()
        self.generate_fixture_metadata_descriptor(entity_type="Shot")
        self.person_id = str(self.person.id)
        self.shot_id = str(self.shot.id)
        self.meta_descriptor_id = self.meta_descriptor.id
        self.department_id = self.department.id

    def test_get_tasks_for_shot(self):
        tasks = self.get("data/shots/%s/tasks" % self.shot_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.shot_task.id))

    def test_get_shots_and_tasks(self):
        self.generate_fixture_shot_task(name="Secondary")
        shots = self.get("data/shots/with-tasks")
        self.assertEqual(len(shots), 1)
        self.assertEqual(len(shots[0]["tasks"]), 2)
        self.assertEqual(shots[0]["tasks"][0]["assignees"][0], self.person_id)
        self.assertEqual(shots[0]["episode_name"], "E01")
        self.assertEqual(shots[0]["sequence_name"], "S01")

    def test_get_shots_and_tasks_vendor(self):
        self.generate_fixture_shot_task(name="Secondary")
        self.generate_fixture_user_vendor()
        task_id = self.shot_task.id
        project_id = self.project.id
        person_id = self.user_vendor["id"]
        self.log_in_vendor()
        shots = self.get(
            "data/shots/with-tasks?project_id=%s" % project_id, 403
        )
        projects_service.add_team_member(project_id, person_id)
        shots = self.get("data/shots/with-tasks?project_id=%s" % project_id)
        self.assertEqual(len(shots), 0)
        tasks_service.assign_task(task_id, person_id)
        shots = self.get("data/shots/with-tasks?project_id=%s" % project_id)
        self.assertEqual(len(shots), 1)
        self.assertEqual(len(shots[0]["tasks"]), 1)
        self.assertTrue(str(person_id) in shots[0]["tasks"][0]["assignees"])

        shots_service.update_shot(
            self.shot_id, {"data": {"contractor": "test"}}
        )
        shots = self.get("data/shots/with-tasks?project_id=%s" % project_id)
        self.assertEqual(shots[0]["data"]["contractor"], "test")

        projects_service.update_metadata_descriptor(
            self.meta_descriptor_id, {"departments": [self.department_id]}
        )
        persons_service.add_to_department(str(self.department_id), person_id)
        shots = self.get("data/shots/with-tasks?project_id=%s" % project_id)
        self.assertEqual(shots[0]["data"]["contractor"], "test")

        persons_service.remove_from_department(
            str(self.department_id), person_id
        )
        shots = self.get("data/shots/with-tasks?project_id=%s" % project_id)
        self.assertTrue("contractor" not in shots[0]["data"])

    def test_get_task_types_for_shot(self):
        task_types = self.get("/data/shots/%s/task-types" % self.shot_id)
        self.assertEqual(len(task_types), 1)
        self.assertDictEqual(
            task_types[0], self.task_type_animation.serialize()
        )
