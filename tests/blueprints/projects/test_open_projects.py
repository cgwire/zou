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

    def add_descriptors(self, project_id):
        """
        Give the project a descriptor kept to the studio and one published
        to clients. Returns the published one.
        """
        projects_service.add_metadata_descriptor(
            project_id, "Asset", "Contractor", "string", [], False
        )
        return projects_service.add_metadata_descriptor(
            project_id, "Asset", "Delivery", "string", [], True
        )

    def descriptor_ids(self, project):
        return [descriptor["id"] for descriptor in project["descriptors"]]

    def test_the_descriptors_follow_the_role_held_on_each_project(self):
        # A listing resolves no project, so its descriptors were narrowed on
        # the global role: a manager who is a client on a production read
        # the ones kept to the studio.
        client_project_id = self.project_id
        managed_project_id = str(self.generate_fixture_project("Agent 327").id)
        published = self.add_descriptors(client_project_id)
        self.add_descriptors(managed_project_id)
        manager_id = self.generate_fixture_user_manager()["id"]
        projects_service.add_team_member(
            client_project_id, manager_id, role="client"
        )
        projects_service.add_team_member(managed_project_id, manager_id)
        self.log_in_manager()

        projects = {
            project["id"]: project
            for project in self.get("data/projects/open")
        }

        self.assertEqual(
            self.descriptor_ids(projects[client_project_id]),
            [published["id"]],
        )
        self.assertEqual(len(projects[managed_project_id]["descriptors"]), 2)
        # A read by its id serves the same descriptors.
        self.assertEqual(
            self.get(f"data/projects/{client_project_id}")["descriptors"],
            projects[client_project_id]["descriptors"],
        )

    def test_a_client_promoted_on_a_project_lists_every_descriptor(self):
        self.add_descriptors(self.project_id)
        client_id = self.generate_fixture_user_client()["id"]
        projects_service.add_team_member(
            self.project_id, client_id, role="user"
        )
        self.log_in_client()

        projects = self.get("data/projects/open")

        self.assertEqual(len(projects[0]["descriptors"]), 2)

    def test_a_demoted_vendor_lists_their_departments_descriptors(self):
        # The manager belongs to no department: as a vendor on the project,
        # only the descriptors limited to no department are theirs.
        self.generate_fixture_department()
        shared = projects_service.add_metadata_descriptor(
            self.project_id, "Asset", "Contractor", "string", [], False
        )
        projects_service.add_metadata_descriptor(
            self.project_id,
            "Asset",
            "Rig",
            "string",
            [],
            False,
            [str(self.department.id)],
        )
        manager_id = self.generate_fixture_user_manager()["id"]
        projects_service.add_team_member(
            self.project_id, manager_id, role="vendor"
        )
        self.log_in_manager()

        projects = self.get("data/projects/open")

        self.assertEqual(self.descriptor_ids(projects[0]), [shared["id"]])

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
