from tests.base import ApiDBTestCase

from zou.app.services import comments_service


class EpisodeStatsTestCase(ApiDBTestCase):

    def setUp(self):
        super(EpisodeStatsTestCase, self).setUp()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.retake_id = str(self.generate_fixture_task_status_retake().id)
        self.wip_id = str(self.generate_fixture_task_status_wip().id)
        self.done_id = str(self.generate_fixture_task_status_done().id)
        self.generate_fixture_task_status()
        self.person_id = str(self.generate_fixture_person().id)
        self.generate_fixture_assigner()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)
        self.generate_fixture_asset_type()
        self.episode_ids = {}

        for i in range(3):
            episode_name = "E0" + str(i + 1)
            episode = self.generate_fixture_episode(episode_name)
            self.episode_ids[episode_name] = str(episode.id)
            self.generate_fixture_sequence("SE01")
            self.generate_fixture_shot_and_task("SH01", 2, 0)
            self.generate_fixture_shot_and_task("SH02", 3, 1)
            self.generate_fixture_shot_and_task("SH03", 0, 0)
            self.generate_fixture_sequence("SE02")
            self.generate_fixture_shot_and_task("SH01", 2, 2)
            self.generate_fixture_shot_and_task("SH02", 2, 0)
            self.generate_fixture_shot_and_task("SH03", 1, 0)
            self.generate_fixture_sequence("SE03")
            self.generate_fixture_shot_and_task("SH01", 3, 0)
            self.generate_fixture_shot_and_task("SH02", 3, 1)
            self.generate_fixture_shot_and_task("SH03", 0, 0)
            self.generate_fixture_sequence("SE04")
            self.generate_fixture_shot_and_task("SH01", 0, 1)
            self.generate_fixture_shot_and_task("SH02", 0, 0)
            self.generate_fixture_shot_and_task("SH03", 1, 0)

    def generate_fixture_shot_and_task(
        self,
        shot_name,
        layout_retakes=0,
        animation_retakes=0
    ):
        shot = self.generate_fixture_shot(shot_name, 10)
        self.generate_fixture_task(
            entity_id=shot.id,
            task_type_id=self.task_type_layout.id
        )
        self.add_retakes(str(self.task.id), layout_retakes)
        self.generate_fixture_task(
            entity_id=shot.id,
            task_type_id=self.task_type_animation.id
        )
        self.add_retakes(str(self.task.id), animation_retakes)
        comments_service.create_comment(
            self.person_id, str(self.task.id), self.done_id, "", [], {}, None)

    def add_retakes(self, task_id, nb_retakes):
        for i in range(nb_retakes):
            comments_service.create_comment(
                self.person_id, task_id, self.wip_id, "", [], {}, None)
            comments_service.create_comment(
                self.person_id, task_id, self.retake_id, "", [], {}, None)

    def test_retake_stats_by_episode(self):
        ep1_id = self.episode_ids["E01"]
        ep3_id = self.episode_ids["E03"]
        layout_id = str(self.task_type_layout.id)
        animation_id = str(self.task_type_animation.id)
        path = "/data/projects/%s/episodes/retake-stats" % self.project_id
        retake_stats = self.get(path)
        self.assertEqual(
            retake_stats["all"][animation_id]["max_retake_count"], 2)
        self.assertEqual(
            retake_stats["all"][animation_id]["done"]["frames"], 360)
        self.assertEqual(
            retake_stats[ep1_id]["all"]["evolution"]["1"]["count"], 12)
        self.assertEqual(
            retake_stats[ep1_id][animation_id]["evolution"]["1"]["count"], 4)
        self.assertEqual(
            retake_stats[ep1_id][layout_id]["retake"]["frames"], 80)
        self.assertEqual(
            retake_stats[ep3_id][layout_id]["retake"]["count"], 8)
