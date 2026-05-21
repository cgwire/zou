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
        sequences = self.get(f"data/episodes/{self.episode_id}/sequences")
        self.assertEqual(len(sequences), 4)
        self.assertDictEqual(sequences[0], self.serialized_sequence)

    def test_get_shots_for_episode(self):
        shots = self.get(f"data/episodes/{self.episode_id}/shots")
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
        sequences = self.get(f"data/episodes/{self.episode_id}/sequences")
        self.assertEqual(len(sequences), 0)
        tasks_service.assign_task(task_id, person_id)
        sequences = self.get(f"data/episodes/{self.episode_id}/sequences")
        self.assertEqual(len(sequences), 1)

    def test_get_episodes(self):
        episodes = self.get("data/episodes")
        self.assertEqual(len(episodes), 3)
        self.assertDictEqual(episodes[0], self.serialized_episode)

    def test_get_episode(self):
        episode = self.get(f"data/episodes/{self.episode.id}")
        self.assertEqual(episode["id"], str(self.episode.id))
        self.assertEqual(episode["name"], self.episode.name)
        self.assertEqual(episode["project_name"], self.project.name)

    def test_get_episode_by_name(self):
        episodes = self.get(f"data/episodes?name={self.episode.name.lower()}")
        self.assertEqual(episodes[0]["id"], str(self.episode.id))

    def test_create_episode(self):
        episode_name = "NE01"
        data = {"name": episode_name}
        episode = self.post(f"data/projects/{self.project.id}/episodes", data)
        episode = self.get(f"data/episodes/{episode['id']}")
        self.assertEqual(episode["name"], episode_name)

    def test_get_episodes_for_project(self):
        episodes = self.get(f"data/projects/{self.project.id}/episodes")
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
        episodes = self.get(f"data/projects/{project_id}/episodes")
        self.assertEqual(len(episodes), 0)
        tasks_service.assign_task(task_id, person_id)
        episodes = self.get(f"data/projects/{project_id}/episodes")
        self.assertEqual(len(episodes), 1)

    def test_get_episodes_for_project_404(self):
        self.get("data/projects/unknown/episodes", 404)

    def test_get_episodes_by_project_and_name(self):
        self.get("data/episodes?project_id=undefined&name=E01", 400)
        episodes = self.get(
            f"data/episodes?project_id={self.project_id}&name=E02"
        )
        self.assertEqual(episodes[0]["id"], str(self.episode_02_id))

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        episodes = self.get(
            f"data/episodes?project_id={self.project_id}&name=E01", 403
        )

    def _setup_vendor(self):
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task(name="VendorTask")
        self.generate_fixture_user_vendor()
        projects_service.add_team_member(
            self.project_id, self.user_vendor["id"]
        )
        projects_service.clear_project_cache(str(self.project_id))
        self.log_in_vendor()

    def test_get_episodes_vendor_filters(self):
        self._setup_vendor()
        episodes = self.get(f"data/episodes?project_id={self.project_id}")
        self.assertEqual(len(episodes), 0)
        tasks_service.assign_task(self.shot_task.id, self.user_vendor["id"])
        episodes = self.get(f"data/episodes?project_id={self.project_id}")
        self.assertEqual(len(episodes), 1)

    def test_get_episode_vendor_no_task(self):
        self._setup_vendor()
        self.get(f"data/episodes/{self.episode_02_id}", 403)

    def test_get_episode_tasks_vendor_blocked_no_task(self):
        self._setup_vendor()
        self.get(f"data/episodes/{self.episode_id}/tasks", 403)

    def test_get_episodes_with_tasks_vendor_blocked(self):
        self._setup_vendor()
        self.get(
            f"data/episodes/with-tasks?project_id={self.project_id}",
            403,
        )

    def test_force_delete_episode(self):
        self.get(f"data/episodes/{self.episode_id}")
        self.delete(f"data/episodes/{self.episode_id}?force=true")
        self.get(f"data/episodes/{self.episode_id}", 404)

    def test_cant_delete_episode(self):
        self.get(f"data/episodes/{self.episode_id}")
        self.delete(f"data/episodes/{self.episode_id}", 400)

    def test_episode_stats(self):
        pass
