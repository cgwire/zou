from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class OpenProjectRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.project_id = str(self.generate_fixture_project().id)

    def test_open_projects(self):
        projects = self.get("data/projects/open/")

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], self.project.name)

    def a_tv_show_with(self, episodes):
        """
        A tv show carrying given (name, status) episodes. Returns them by
        name, since generate_fixture_episode repoints self.episode.
        """
        self.project.update({"production_type": "tvshow"})
        built = {}
        for name, status in episodes:
            episode = self.generate_fixture_episode(name)
            episode.update({"status": status})
            built[name] = episode
        return built

    def first_episode_id(self):
        return self.get("data/projects/open/")[0]["first_episode_id"]

    def test_the_first_episode_is_the_running_one_sorting_first(self):
        episodes = self.a_tv_show_with(
            [("E02", "running"), ("E01", "running")]
        )

        self.assertEqual(self.first_episode_id(), str(episodes["E01"].id))

    def test_a_running_episode_wins_over_a_finished_one_sorting_first(self):
        episodes = self.a_tv_show_with(
            [("E01", "complete"), ("E02", "running")]
        )

        self.assertEqual(self.first_episode_id(), str(episodes["E02"].id))

    def test_a_show_with_nothing_running_falls_back_to_its_episodes(self):
        episodes = self.a_tv_show_with(
            [("E02", "complete"), ("E01", "complete")]
        )
        # An asset sorting before every episode: the fallback is still about
        # episodes.
        self.generate_fixture_asset_type()
        self.generate_fixture_asset("Aardvark")

        self.assertEqual(self.first_episode_id(), str(episodes["E01"].id))

    def test_get_team(self):
        """
        A manager reads the team with each member's departments and
        per-project role embedded.
        """
        person = self.generate_fixture_person()
        self.generate_fixture_department()
        person.departments.append(self.department)
        person.save()
        projects_service.add_team_member(self.project_id, str(person.id))

        team = self.get(f"data/projects/{self.project_id}/team")

        self.assertEqual(len(team), 1)
        member = team[0]
        self.assertEqual(member["id"], str(person.id))
        self.assertEqual(member["departments"], [str(self.department.id)])
        self.assertIsNone(member["project_role"])
        self.assertNotIn("password", member)

    def test_add_team_member(self):
        self.person_id = str(self.generate_fixture_person().id)
        self.post(
            f"data/projects/{self.project_id}/team",
            {"person_id": self.person_id},
        )
        project = projects_service.get_project(self.project_id, relations=True)
        self.assertEqual(project["team"], [str(self.person_id)])

    def test_remove_team_member(self):
        self.person_id = str(self.generate_fixture_person().id)
        projects_service.add_team_member(self.project_id, self.person_id)
        self.delete(f"data/projects/{self.project_id}/team/{self.person_id}")
        project = projects_service.get_project(self.project_id, relations=True)
        self.assertEqual(project["team"], [])
