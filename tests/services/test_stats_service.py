from tests.base import ApiDBTestCase

from zou.app.services import stats_service


class StatsServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super(StatsServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()

    def test_get_main_stats(self):
        result = stats_service.get_main_stats()
        self.assertIn("number_of_video_previews", result)
        self.assertIn("number_of_picture_previews", result)
        self.assertIn("number_of_model_previews", result)
        self.assertIn("number_of_comments", result)
        self.assertEqual(result["number_of_comments"], 0)

    def test_get_main_stats_with_data(self):
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_preview_file()
        result = stats_service.get_main_stats()
        self.assertEqual(result["number_of_video_previews"], 1)

    def test_get_episode_stats_for_project_empty(self):
        result = stats_service.get_episode_stats_for_project(
            str(self.project.id)
        )
        self.assertEqual(result, {})

    def test_get_episode_stats_for_project(self):
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        result = stats_service.get_episode_stats_for_project(
            str(self.project.id)
        )
        self.assertIn(str(self.episode.id), result)
        self.assertIn("all", result)

    def test_get_episode_retake_stats_for_project_empty(self):
        result = stats_service.get_episode_retake_stats_for_project(
            str(self.project.id)
        )
        self.assertIn("all", result)
        self.assertIn("all", result["all"])

    def test_get_episode_retake_stats_for_project(self):
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        result = stats_service.get_episode_retake_stats_for_project(
            str(self.project.id)
        )
        self.assertIn(str(self.episode.id), result)
        episode_stats = result[str(self.episode.id)]
        self.assertIn("all", episode_stats)
        self.assertIn("max_retake_count", episode_stats["all"])

    def test_add_entry_to_stats(self):
        results = {}
        stats_service.add_entry_to_stats(
            results,
            project_id="p1",
            episode_id="e1",
            task_type_id="tt1",
            task_status_id="ts1",
            task_status_short_name="wip",
            task_status_color="#FFFFFF",
            task_count=5,
            task_nb_drawings=10,
            entity_nb_frames=100,
        )
        self.assertEqual(results["e1"]["tt1"]["ts1"]["count"], 5)
        self.assertEqual(results["e1"]["tt1"]["ts1"]["frames"], 100)
        self.assertEqual(results["e1"]["tt1"]["ts1"]["drawings"], 10)
        # Aggregated "all" for episode
        self.assertEqual(results["e1"]["all"]["ts1"]["count"], 5)

    def test_add_entry_to_all_stats(self):
        results = {}
        stats_service.add_entry_to_all_stats(
            results,
            project_id="p1",
            episode_id="e1",
            task_type_id="tt1",
            task_status_id="ts1",
            task_status_short_name="wip",
            task_status_color="#FFFFFF",
            task_count=3,
            task_nb_drawings=6,
            entity_nb_frames=50,
        )
        self.assertEqual(results["all"]["tt1"]["ts1"]["count"], 3)
        self.assertEqual(results["all"]["all"]["ts1"]["count"], 3)
        self.assertEqual(results["all"]["all"]["ts1"]["frames"], 50)
