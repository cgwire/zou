from tests.base import ApiDBTestCase


class ShotRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(ShotRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()

    def test_get_shot_preview_files(self):
        result = self.get(
            f"/data/shots/{self.shot.id}/preview-files"
        )
        self.assertIsInstance(result, dict)

    def test_get_shot_preview_files_with_data(self):
        self.generate_fixture_preview_file(
            task_id=self.shot_task.id,
        )
        result = self.get(
            f"/data/shots/{self.shot.id}/preview-files"
        )
        self.assertTrue(len(result) > 0)

    def test_get_shot_versions(self):
        result = self.get(f"/data/shots/{self.shot.id}/versions")
        self.assertIsInstance(result, list)

    def test_get_episode_shot_tasks(self):
        result = self.get(
            f"/data/episodes/{self.episode.id}/shot-tasks"
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_get_episode_asset_tasks(self):
        result = self.get(
            f"/data/episodes/{self.episode.id}/asset-tasks"
        )
        self.assertIsInstance(result, list)

    def test_get_sequence_shot_tasks(self):
        result = self.get(
            f"/data/sequences/{self.sequence.id}/shot-tasks"
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_get_project_quotas(self):
        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}"
        )
        self.assertIsInstance(result, dict)

    def test_get_project_person_quotas(self):
        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/persons/{self.person.id}"
        )
        self.assertIsInstance(result, dict)

    def test_set_shot_nb_frames(self):
        result = self.post(
            f"/actions/projects/{self.project.id}"
            f"/task-types/{self.task_type_animation.id}"
            f"/set-shot-nb-frames",
            {},
            200,
        )
        self.assertIsInstance(result, list)
