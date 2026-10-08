from tests.base import ApiDBTestCase

from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.services import (
    breakdown_service,
    projects_service,
    cascade_deletion_service,
)
from zou.app.exceptions import (
    ProjectNotFoundException,
    WrongParameterException,
)
import os
import tempfile
from tests.services.cases import PreviewFileTestCase


class ProjectServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_project_closed()

    def test_get_open_projects(self):
        projects = projects_service.open_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual("Cosmos Landromat", projects[0]["name"])

    def test_get_projects(self):
        projects = projects_service.get_projects()
        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0]["project_status_name"], "Open")

    def test_get_or_create_project_status(self):
        project_status = projects_service.get_or_create_project_status(
            "Frozen"
        )
        self.assertEqual(project_status["name"], "Frozen")
        self.assertEqual(ProjectStatus.query.count(), 3)

        # Asking again returns the same row rather than adding one. The
        # count has to be read back, the second call is what could add it.
        again = projects_service.get_or_create_project_status("Frozen")
        self.assertEqual(again["id"], project_status["id"])
        self.assertEqual(ProjectStatus.query.count(), 3)

    def test_get_or_create_open_status(self):
        project_status = projects_service.get_or_create_open_status()
        self.assertEqual(project_status["name"], "Open")

    def test_save_project_status(self):
        statuses = projects_service.save_project_status(
            ["Frozen", "Postponed"]
        )
        self.assertEqual(len(statuses), 2)
        statuses = ProjectStatus.query.all()
        self.assertEqual(len(statuses), 4)

        statuses = projects_service.save_project_status(
            ["Frozen", "Postponed"]
        )
        self.assertEqual(len(statuses), 2)
        statuses = ProjectStatus.query.all()
        self.assertEqual(len(statuses), 4)

    def test_get_project_by_name(self):
        project = projects_service.get_project_by_name(self.project.name)
        self.assertEqual(project["name"], self.project.name)
        self.assertRaises(
            ProjectNotFoundException,
            projects_service.get_project_by_name,
            "missing",
        )

    def test_get_project(self):
        project = projects_service.get_project(self.project.id)
        self.assertEqual(project["name"], self.project.name)
        self.assertRaises(
            ProjectNotFoundException, projects_service.get_project, "wrongid"
        )

    def test_update_project(self):
        new_name = "New name"
        projects_service.update_project(self.project.id, {"name": new_name})
        project = projects_service.get_project(self.project.id)
        self.assertEqual(project["name"], new_name)

    def test_add_team_member(self):
        self.generate_fixture_person()
        projects_service.add_team_member(self.project.id, self.person.id)
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["team"], [str(self.person.id)])

    def test_add_team_member_swallows_concurrent_insert(self):
        from unittest import mock
        from sqlalchemy.exc import IntegrityError

        self.generate_fixture_person()
        project_id = str(self.project.id)
        person_id = str(self.person.id)

        # Simulate the TOCTOU race: a concurrent request inserted the same
        # link first, so our own INSERT raises a UniqueViolation at save.
        # add_team_member must treat it as a no-op instead of bubbling up a
        # 500, and still return the up-to-date project.
        with mock.patch.object(
            projects_service,
            "_save_project",
            side_effect=IntegrityError("duplicate key", {}, Exception()),
        ):
            project = projects_service.add_team_member(project_id, person_id)

        self.assertEqual(project["id"], project_id)

    def test_remove_team_member(self):
        self.generate_fixture_person()
        projects_service.add_team_member(self.project.id, self.person.id)
        projects_service.remove_team_member(self.project.id, self.person.id)
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["team"], [])

    def test_add_and_remove_project_settings(self):
        """
        The three settings that are plain links on the project: adding one
        puts its id in the project relations, removing it takes the id back
        out. The round trip is the contract, so both halves live in one case.
        """
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        cases = [
            ("asset_types", "asset_type_setting", self.asset_type.id),
            ("task_types", "task_type_setting", self.task_type.id),
            ("task_statuses", "task_status_setting", self.task_status.id),
        ]
        # str(), not the UUID: clear_project_cache stringifies the id, so a
        # read made with a UUID object caches under a key no clear reaches
        # and the second half of the round trip sees the first half's value.
        project_id = str(self.project.id)
        for relation, setting, setting_id in cases:
            with self.subTest(relation=relation):
                add = getattr(projects_service, f"add_{setting}")
                remove = getattr(projects_service, f"remove_{setting}")

                add(project_id, setting_id)
                project = projects_service.get_project(
                    project_id, relations=True
                )
                self.assertEqual(project[relation], [str(setting_id)])

                remove(project_id, setting_id)
                project = projects_service.get_project(
                    project_id, relations=True
                )
                self.assertEqual(project[relation], [])

    def test_delete_project(self):
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_assigned_task()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        breakdown_service.create_casting_link(self.shot.id, self.asset.id)

        project_id = str(self.project.id)
        cascade_deletion_service.remove_project(project_id)
        self.assertIsNone(Project.get(project_id))

    def test_is_tv_show(self):
        self.assertFalse(projects_service.is_tv_show(self.project.serialize()))
        self.project.update({"production_type": "tvshow"})
        self.assertTrue(projects_service.is_tv_show(self.project.serialize()))

    def test_is_open(self):
        self.assertTrue(projects_service.is_open(self.project.serialize()))
        self.assertFalse(
            projects_service.is_open(self.project_closed.serialize())
        )

    def test_get_project_raw(self):
        project = projects_service.get_project_raw(self.project.id)
        self.assertEqual(project.name, self.project.name)
        self.assertRaises(
            ProjectNotFoundException,
            projects_service.get_project_raw,
            "wrong-id",
        )

    def test_get_project_statuses(self):
        statuses = projects_service.get_project_statuses()
        self.assertGreater(len(statuses), 0)
        names = [s["name"] for s in statuses]
        self.assertIn("Open", names)

    def test_get_closed_status(self):
        status = projects_service.get_closed_status()
        self.assertEqual(status["name"], "Closed")

    def test_open_project_ids(self):
        ids = projects_service.open_project_ids()
        self.assertIn(str(self.project.id), ids)
        self.assertNotIn(str(self.project_closed.id), ids)

    def test_create_project_task_type_link(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        link = projects_service.create_project_task_type_link(
            str(self.project.id), str(self.task_type.id), 1
        )
        self.assertEqual(link["project_id"], str(self.project.id))
        self.assertEqual(link["task_type_id"], str(self.task_type.id))
        self.assertEqual(link["priority"], 1)
        # Update existing link
        link2 = projects_service.create_project_task_type_link(
            str(self.project.id), str(self.task_type.id), 5
        )
        self.assertEqual(link2["priority"], 5)

    def test_create_project_task_type_link_invalid(self):
        self.assertRaises(
            WrongParameterException,
            projects_service.create_project_task_type_link,
            str(self.project.id),
            "not-a-uuid",
            1,
        )

    def test_create_project_task_status_link(self):
        self.generate_fixture_task_status()
        link = projects_service.create_project_task_status_link(
            str(self.project.id), str(self.task_status.id), 1
        )
        self.assertEqual(link["project_id"], str(self.project.id))
        self.assertEqual(link["task_status_id"], str(self.task_status.id))
        # Update existing link
        link2 = projects_service.create_project_task_status_link(
            str(self.project.id),
            str(self.task_status.id),
            3,
            roles_for_board=["admin"],
        )
        self.assertEqual(link2["priority"], 3)

    def test_create_project_task_status_link_invalid(self):
        self.assertRaises(
            WrongParameterException,
            projects_service.create_project_task_status_link,
            str(self.project.id),
            "not-a-uuid",
            1,
        )

    def test_get_project_task_types(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        projects_service.add_task_type_setting(
            self.project.id, self.task_type.id
        )
        task_types = projects_service.get_project_task_types(self.project.id)
        self.assertEqual(len(task_types), 1)

    def test_get_project_task_types_raw_narrows_to_an_entity_kind(self):
        """
        The importers read the task types of a production per entity kind.
        A task type predating the for_entity column reads NULL and means
        Asset, the model default.
        """
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        for task_type in [
            self.task_type,
            self.task_type_animation,
            self.task_type_concept,
        ]:
            projects_service.add_task_type_setting(
                self.project.id, task_type.id
            )
        self.task_type_concept.update({"for_entity": None})

        names = lambda task_types: sorted(t.name for t in task_types)
        self.assertEqual(
            names(
                projects_service.get_project_task_types_raw(
                    self.project.id, "Asset"
                )
            ),
            [self.task_type_concept.name, self.task_type.name],
        )
        self.assertEqual(
            names(
                projects_service.get_project_task_types_raw(
                    self.project.id, "Shot"
                )
            ),
            [self.task_type_animation.name],
        )
        self.assertEqual(
            len(projects_service.get_project_task_types_raw(self.project.id)),
            3,
        )

    def test_get_project_task_statuses(self):
        self.generate_fixture_task_status()
        projects_service.add_task_status_setting(
            self.project.id, self.task_status.id
        )
        statuses = projects_service.get_project_task_statuses(self.project.id)
        self.assertEqual(len(statuses), 1)

    def test_add_status_automation_setting(self):
        self.generate_fixture_status_automation_to_status()
        automations = projects_service.get_project_status_automations(
            self.project.id
        )
        self.assertEqual(len(automations), 1)

    def test_remove_status_automation_setting(self):
        self.generate_fixture_status_automation_to_status()
        projects_service.remove_status_automation_setting(
            self.project.id, self.status_automation_to_status.id
        )
        automations = projects_service.get_project_status_automations(
            self.project.id
        )
        self.assertEqual(automations, [])

    def test_add_preview_background_file_setting(self):
        self.generate_fixture_preview_background_file()
        projects_service.add_preview_background_file_setting(
            self.project.id, self.preview_background_file.id
        )
        files = projects_service.get_project_preview_background_files(
            self.project.id
        )
        self.assertEqual(len(files), 1)

    def test_remove_preview_background_file_setting(self):
        self.generate_fixture_preview_background_file()
        projects_service.add_preview_background_file_setting(
            self.project.id, self.preview_background_file.id
        )
        projects_service.remove_preview_background_file_setting(
            self.project.id, self.preview_background_file.id
        )
        files = projects_service.get_project_preview_background_files(
            self.project.id
        )
        self.assertEqual(files, [])

    def test_an_update_drops_every_form_of_the_cached_project(self):
        """
        The memoization keys on the argument, and an omitted default is a
        key of its own: the id as a UUID, the id as a string and the
        related serialization would be three entries. An update has to drop
        what every caller reads, whichever form they hold.
        """
        project_id = self.project.id
        projects_service.get_project(project_id)
        projects_service.get_project(str(project_id))
        projects_service.get_project(project_id, relations=True)

        projects_service.update_project(str(project_id), {"fps": "30"})

        self.assertEqual(
            [
                projects_service.get_project(project_id)["fps"],
                projects_service.get_project(str(project_id))["fps"],
                projects_service.get_project(project_id, relations=True)[
                    "fps"
                ],
            ],
            ["30", "30", "30"],
        )

    def test_get_project_fps(self):
        fps = projects_service.get_project_fps(self.project.id)
        self.assertEqual(fps, 25.00)
        projects_service.update_project(self.project.id, {"fps": "30"})
        fps = projects_service.get_project_fps(self.project.id)
        self.assertEqual(fps, 30.00)

    def link_the_same_task_type_to_both_productions(self, here, elsewhere):
        """
        The same task type ordered differently in two productions, which is
        what the scoping has to tell apart.
        """
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_project_standard()
        projects_service.create_project_task_type_link(
            str(self.project.id), str(self.task_type.id), here
        )
        projects_service.create_project_task_type_link(
            str(self.project_standard.id), str(self.task_type.id), elsewhere
        )

    def test_get_task_type_priority_map(self):
        self.link_the_same_task_type_to_both_productions(3, 9)

        priority_map = projects_service.get_task_type_priority_map(
            self.project.id
        )

        self.assertEqual(priority_map, {str(self.task_type.id): 3})

    def test_get_task_type_links(self):
        self.link_the_same_task_type_to_both_productions(2, 9)

        links = projects_service.get_task_type_links(self.project.id)

        self.assertEqual(
            [(link["task_type_id"], link["priority"]) for link in links],
            [(str(self.task_type.id), 2)],
        )

    def test_get_department_team(self):
        """
        Scoped twice: the production and the department. A member of the
        same department on another production stays out.
        """
        from zou.app.services import persons_service

        self.generate_fixture_department()
        self.generate_fixture_person()
        # generate_fixture_person repoints self.person, hence the local.
        here = self.person
        self.generate_fixture_project_standard()
        elsewhere = self.generate_fixture_person(
            first_name="Alice",
            last_name="Zulu",
            desktop_login="alice.zulu",
            email="alice.zulu@gmail.com",
        )
        projects_service.add_team_member(self.project.id, here.id)
        projects_service.add_team_member(
            self.project_standard.id, elsewhere.id
        )
        for person in [here, elsewhere]:
            persons_service.add_to_department(
                str(self.department.id), str(person.id)
            )

        team = projects_service.get_department_team(
            self.project.id, self.department.id
        )

        self.assertEqual([person.id for person in team], [here.id])


class PreviewFileServiceTestCase(PreviewFileTestCase):
    def _write_temp_movie(self, size=1024):
        """
        Create a non-empty temp file standing in for a movie.
        """
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(b"\x00" * size)
        tmp.close()
        self.addCleanup(
            lambda: os.path.exists(tmp.name) and os.remove(tmp.name)
        )
        return tmp.name

    def test_movie_bitrate_validation(self):
        projects_service.validate_movie_bitrate(None)
        projects_service.validate_movie_bitrate(20)
        projects_service.validate_movie_bitrate(28)
        for bitrate in ("20", 20.5, True, 0, 29):
            with self.assertRaises(WrongParameterException):
                projects_service.validate_movie_bitrate(bitrate)

    def test_low_def_bitrate_stays_below_high_def(self):
        validate = projects_service.validate_movie_bitrates
        validate({"hd_bitrate_compression": 20, "ld_bitrate_compression": 20})
        # Against the instance default when the high def is not set.
        validate({"ld_bitrate_compression": 28})
        # Against the object's own high def when only the low def changes.
        validate(
            {"ld_bitrate_compression": 10},
            current={"hd_bitrate_compression": 10},
        )
        # A link leaving its high def unset is checked against the level
        # it inherits from.
        validate(
            {"hd_bitrate_compression": None, "ld_bitrate_compression": 10},
            inherited={"hd_bitrate_compression": 10},
        )
        # Clearing the low def while lowering the high def is fine.
        validate(
            {"hd_bitrate_compression": 4, "ld_bitrate_compression": None},
            current={"ld_bitrate_compression": 6},
        )
        # So is leaving it: the encoder caps a stored low def.
        validate(
            {"hd_bitrate_compression": 4},
            current={"ld_bitrate_compression": 6},
        )
        for data, kwargs in (
            ({"hd_bitrate_compression": 10, "ld_bitrate_compression": 12}, {}),
            (
                {"ld_bitrate_compression": 12},
                {"current": {"hd_bitrate_compression": 10}},
            ),
            (
                {"hd_bitrate_compression": None, "ld_bitrate_compression": 12},
                {"inherited": {"hd_bitrate_compression": 10}},
            ),
        ):
            with self.assertRaises(WrongParameterException):
                validate(data, **kwargs)

    def test_encoding_bitrates_never_exceed_the_ceilings(self):
        project = {"hd_bitrate_compression": 8, "ld_bitrate_compression": None}
        link = {"hd_bitrate_compression": None, "ld_bitrate_compression": 12}
        self.assertEqual(
            projects_service.get_movie_bitrates(project, link), (8, 8)
        )
