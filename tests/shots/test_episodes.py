from tests.base import ApiDBTestCase

from zou.app.services import projects_service, tasks_service


class EpisodeTestCase(ApiDBTestCase):

    def setUp(self):
        super(EpisodeTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode("E01")
        self.project_id = str(self.project.id)
        self.serialized_episode = self.episode.serialize(obj_type="Episode")
        self.episode_id = str(self.episode.id)

        self.generate_fixture_sequence("SE01")
        self.serialized_sequence = self.sequence.serialize(obj_type="Sequence")

        self.generate_fixture_shot("SH01")
        self.generate_fixture_shot("SH02")
        self.generate_fixture_shot("SH03")

        self.generate_fixture_sequence("SE02")
        self.generate_fixture_sequence("SE03")
        self.generate_fixture_sequence("SE04")

        episode_02 = self.generate_fixture_episode("E02")
        self.episode_02_id = str(episode_02.id)
        self.generate_fixture_sequence("SE01", episode_id=episode_02.id)
        self.generate_fixture_episode("E03")

    def test_get_sequences_for_episode(self):
        sequences = self.get("data/episodes/%s/sequences" % self.episode_id)
        self.assertEqual(len(sequences), 4)
        self.assertDictEqual(sequences[0], self.serialized_sequence)

    def test_get_shots_for_episode(self):
        shots = self.get("data/episodes/%s/shots" % self.episode_id)
        self.assertEqual(len(shots), 3)
        self.assertEqual(shots[0]["type"], "Shot")

    def test_get_sequences_for_episode_with_vendor(self):
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task(name="Secondary")
        self.generate_fixture_user_vendor()
        task_id = self.shot_task.id
        project_id = self.project_id
        person_id = self.user_vendor["id"]
        projects_service.add_team_member(project_id, person_id)
        projects_service.clear_project_cache(str(project_id))
        self.log_in_vendor()
        sequences = self.get("data/episodes/%s/sequences" % self.episode_id)
        self.assertEqual(len(sequences), 0)
        tasks_service.assign_task(task_id, person_id)
        sequences = self.get("data/episodes/%s/sequences" % self.episode_id)
        self.assertEqual(len(sequences), 1)

    def test_get_episodes(self):
        episodes = self.get("data/episodes")
        self.assertEqual(len(episodes), 3)
        self.assertDictEqual(
            episodes[0],
            self.serialized_episode
        )

    def test_get_episode(self):
        episode = self.get("data/episodes/%s" % self.episode.id)
        self.assertEqual(episode["id"], str(self.episode.id))
        self.assertEqual(episode["name"], self.episode.name)
        self.assertEqual(episode["project_name"], self.project.name)

    def test_get_episode_by_name(self):
        episodes = self.get("data/episodes?name=%s" % self.episode.name.lower())
        self.assertEqual(episodes[0]["id"], str(self.episode.id))

    def test_create_episode(self):
        episode_name = "NE01"
        data = {"name": episode_name}
        episode = self.post("data/projects/%s/episodes" % self.project.id, data)
        episode = self.get("data/episodes/%s" % episode["id"])
        self.assertEqual(episode["name"], episode_name)

    def test_get_episodes_for_project(self):
        episodes = self.get("data/projects/%s/episodes" % self.project.id)
        self.assertEqual(len(episodes), 3)
        self.assertEqual(episodes[0], self.serialized_episode)

    def test_get_episodes_for_project_with_vendor(self):
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task(name="Secondary")
        self.generate_fixture_user_vendor()
        task_id = self.shot_task.id
        project_id = self.project_id
        person_id = self.user_vendor["id"]
        projects_service.add_team_member(project_id, person_id)
        self.log_in_vendor()
        episodes = self.get("data/projects/%s/episodes" % project_id)
        self.assertEqual(len(episodes), 0)
        tasks_service.assign_task(task_id, person_id)
        episodes = self.get("data/projects/%s/episodes" % project_id)
        self.assertEqual(len(episodes), 1)

    def test_get_episodes_for_project_404(self):
        self.get("data/projects/unknown/episodes", 404)

    def test_get_episodes_by_project_and_name(self):
        self.get("data/episodes?project_id=undefined&name=E01", 400)
        episodes = self.get(
            "data/episodes?project_id=%s&name=E02" % self.project_id
        )
        self.assertEqual(episodes[0]["id"], str(self.episode_02_id))

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        episodes = self.get(
            "data/episodes?project_id=%s&name=E01" % self.project_id, 403
        )

    def test_delete_episode(self):
        self.get("data/episodes/%s" % self.episode_id)
        self.delete("data/episodes/%s" % self.episode_id, 400)
        self.delete("data/episodes/%s?force=true" % self.episode_id)
        self.get("data/episodes/%s" % self.episode_id, 404)

    def test_episode_stats(self):
        pass
