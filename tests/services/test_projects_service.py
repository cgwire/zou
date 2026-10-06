from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task
from zou.app.services import (
    breakdown_service,
    deletion_service,
    projects_service,
)
from zou.app.exceptions import (
    DepartmentNotFoundException,
    MetadataDescriptorNotFoundException,
    ProjectNotFoundException,
    WrongParameterException,
)


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
        deletion_service.remove_project(project_id)
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


class ProjectMetadataDescriptorTestCase(ApiDBTestCase):
    """
    The custom columns a production adds to its assets, shots or to
    itself. They carry a position, which is what the reorder route
    rewrites, and renaming or removing one rewrites the entity data
    that used the old name.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_project_closed()

    def names_and_positions(self, descriptors):
        return [(d["name"], d["position"]) for d in descriptors]

    def add(self, name, entity_type="Asset", choices=None, task_type_id=None):
        """
        A string descriptor of given name, the shape all these tests want.
        """
        return projects_service.add_metadata_descriptor(
            self.project.id,
            entity_type,
            name,
            "list" if choices else "string",
            choices or [],
            False,
            task_type_id=task_type_id,
        )

    def generate_entity_of_each_type(self):
        """
        One entity of each type a column can describe, keyed by that type.
        """
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_edit()
        return {
            "Asset": self.asset,
            "Shot": self.shot,
            "Scene": self.scene,
            "Sequence": self.sequence,
            "Episode": self.episode,
            "Edit": self.edit,
        }

    def stored_data(self, entities):
        """
        The data each of given entities holds in the database, keyed like
        them.
        """
        return {
            entity_type: Entity.get(entity.id).data
            for entity_type, entity in entities.items()
        }

    def test_add_asset_metadata_descriptor(self):
        descriptor = self.add("Is Outdoor")
        self.assertIsNotNone(MetadataDescriptor.get(descriptor["id"]))
        descriptor = projects_service.add_metadata_descriptor(
            self.project.id,
            "Asset",
            "Contractor",
            "list",
            ["contractor 1", "contractor 2"],
            False,
        )
        descriptors = projects_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(len(descriptors), 2)
        self.assertEqual(descriptors[0]["id"], descriptor["id"])
        self.assertEqual(descriptors[0]["field_name"], "contractor")
        self.assertEqual(descriptors[1]["field_name"], "is_outdoor")

        descriptors = projects_service.get_metadata_descriptors(
            self.project.id, for_client=True
        )
        self.assertEqual(descriptors, [])

    def test_update_metadata_descriptor(self):
        asset = self.generate_fixture_asset_type()
        asset = self.generate_fixture_asset()
        descriptor = self.add("Contractor")
        asset.update({"data": {"contractor": "contractor 1"}})
        self.assertIn("contractor", asset.data)
        projects_service.update_metadata_descriptor(
            descriptor["id"], {"name": "Team", "for_client": True}
        )
        descriptors = projects_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(len(descriptors), 1)
        self.assertTrue(descriptors[0]["for_client"])
        asset = Entity.get(asset.id)
        self.assertEqual(asset.data.get("team"), "contractor 1")

    def test_update_project_metadata_descriptor_renames_project_data(self):
        descriptor = self.add("Studio code", "Project")
        self.project.update({"data": {"studio_code": "A1"}})
        projects_service.update_metadata_descriptor(
            descriptor["id"], {"name": "Code", "for_client": False}
        )
        self.project = Project.get(self.project.id)
        self.assertEqual(self.project.data.get("code"), "A1")
        self.assertIsNone(self.project.data.get("studio_code"))

    def test_remove_project_metadata_descriptor_clears_project_data(self):
        descriptor = self.add("Studio code", "Project")
        self.project.update({"data": {"studio_code": "A1"}})
        projects_service.remove_metadata_descriptor(descriptor["id"])
        self.project = Project.get(self.project.id)
        self.assertIsNone((self.project.data or {}).get("studio_code"))
        self.assertEqual(
            [
                d
                for d in projects_service.get_metadata_descriptors(
                    self.project.id
                )
                if d["entity_type"] == "Project"
            ],
            [],
        )

    def test_reorder_project_metadata_descriptors(self):
        d1 = self.add("Alpha", "Project")
        d2 = self.add("Beta", "Project")
        d3 = self.add("Gamma", "Project")
        reordered = projects_service.reorder_metadata_descriptors(
            self.project.id,
            "Project",
            [str(d3["id"]), str(d1["id"]), str(d2["id"])],
        )
        self.assertEqual(reordered[0]["id"], d3["id"])
        self.assertEqual(reordered[0]["position"], 1)
        self.assertEqual(reordered[1]["id"], d1["id"])
        self.assertEqual(reordered[2]["id"], d2["id"])

    def test_add_delete_metadata_descriptor(self):
        asset = self.generate_fixture_asset_type()
        asset = self.generate_fixture_asset()
        descriptor = self.add("Contractor")
        asset.update({"data": {"contractor": "contractor 1"}})
        self.assertIn("contractor", asset.data)

        projects_service.remove_metadata_descriptor(descriptor["id"])
        descriptors = projects_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(descriptors, [])
        asset = Entity.get(asset.id)
        self.assertNotIn("contractor", asset.data)

    def test_remove_metadata_descriptor_keeps_the_other_types_values(self):
        # A field name is unique per entity type only: each type may have
        # its own Difficulty column, and removing one of them must leave
        # the values of the others in place.
        entities = self.generate_entity_of_each_type()
        for entity_type in entities:
            with self.subTest(entity_type=entity_type):
                for other_type, entity in entities.items():
                    entity.update({"data": {"difficulty": other_type}})
                descriptor = self.add("Difficulty", entity_type)

                projects_service.remove_metadata_descriptor(descriptor["id"])

                self.assertEqual(
                    self.stored_data(entities),
                    {
                        other_type: (
                            {}
                            if other_type == entity_type
                            else {"difficulty": other_type}
                        )
                        for other_type in entities
                    },
                )

    def test_rename_metadata_descriptor_keeps_the_other_types_values(self):
        # A rename moves the values of its own type only: the other types
        # keep theirs under the old field name.
        entities = self.generate_entity_of_each_type()
        for entity_type in entities:
            with self.subTest(entity_type=entity_type):
                for other_type, entity in entities.items():
                    entity.update({"data": {"difficulty": other_type}})
                descriptor = self.add("Difficulty", entity_type)

                projects_service.update_metadata_descriptor(
                    descriptor["id"], {"name": "Complexity"}
                )

                self.assertEqual(
                    self.stored_data(entities),
                    {
                        other_type: (
                            {"complexity": other_type}
                            if other_type == entity_type
                            else {"difficulty": other_type}
                        )
                        for other_type in entities
                    },
                )

    def test_rename_metadata_descriptor_onto_another_column_is_refused(self):
        # A rename onto the name or the field name of another column moved
        # the values onto its key, overwriting them, before the unique
        # index failed: both columns lost their values.
        self.generate_fixture_asset()
        difficulty = self.add("Difficulty")
        self.add("Complexity")
        self.asset.update(
            {"data": {"difficulty": "hard", "complexity": "low"}}
        )
        for name in ("Complexity", "COMPLEXITY"):
            with self.subTest(name=name):
                with self.assertRaises(WrongParameterException):
                    projects_service.update_metadata_descriptor(
                        difficulty["id"], {"name": name}
                    )
                self.assertEqual(
                    Entity.get(self.asset.id).data,
                    {"difficulty": "hard", "complexity": "low"},
                )
                self.assertEqual(
                    MetadataDescriptor.get(difficulty["id"]).field_name,
                    "difficulty",
                )

    def test_rename_metadata_descriptor_onto_the_name_of_a_column(self):
        # A column renamed through the admin CRUD route keeps its field
        # name, so its name alone can collide: the values moved before the
        # name index failed.
        self.generate_fixture_asset()
        difficulty = self.add("Difficulty")
        MetadataDescriptor.create(
            project_id=self.project.id,
            entity_type="Asset",
            name="Weight",
            data_type="string",
            field_name="legacy_weight",
        )
        self.asset.update(
            {"data": {"difficulty": "hard", "legacy_weight": "heavy"}}
        )
        with self.assertRaises(WrongParameterException):
            projects_service.update_metadata_descriptor(
                difficulty["id"], {"name": "Weight"}
            )
        self.assertEqual(
            Entity.get(self.asset.id).data,
            {"difficulty": "hard", "legacy_weight": "heavy"},
        )

    def test_rename_metadata_descriptor_next_to_columns_of_other_scopes(self):
        # A case change keeps the column's own field name, and a column of
        # another type or of another production does not block the rename.
        self.generate_fixture_asset()
        self.asset.update({"data": {"difficulty": "hard"}})
        difficulty = self.add("Difficulty")
        self.add("Weight", "Shot")
        other_project = self.generate_fixture_project(name="Other Project")
        projects_service.add_metadata_descriptor(
            other_project.id, "Asset", "Complexity", "string", [], False
        )
        for name, field_name in (
            ("DIFFICULTY", "difficulty"),
            ("Weight", "weight"),
            ("Complexity", "complexity"),
        ):
            with self.subTest(name=name):
                descriptor = projects_service.update_metadata_descriptor(
                    difficulty["id"], {"name": name}
                )
                self.assertEqual(descriptor["field_name"], field_name)
                self.assertEqual(
                    Entity.get(self.asset.id).data, {field_name: "hard"}
                )

    def test_rename_task_metadata_descriptor_within_its_task_type(self):
        # Task columns are unique per task type: a column of the same task
        # type refuses the rename, a column of another one does not.
        task = self.generate_fixture_task()
        layer = self.add("Layer", "Task", task_type_id=self.task_type.id)
        self.add("Pass", "Task", task_type_id=self.task_type.id)
        self.add("Note", "Task", task_type_id=self.task_type_modeling.id)
        task.update({"data": {"layer": "bg", "pass": "beauty"}})

        with self.assertRaises(WrongParameterException):
            projects_service.update_metadata_descriptor(
                layer["id"], {"name": "Pass"}
            )
        self.assertEqual(
            Task.get(task.id).data, {"layer": "bg", "pass": "beauty"}
        )

        projects_service.update_metadata_descriptor(
            layer["id"], {"name": "Note"}
        )
        self.assertEqual(
            Task.get(task.id).data, {"note": "bg", "pass": "beauty"}
        )

    def test_rename_metadata_descriptor_with_a_malformed_department(self):
        # The departments are resolved before the values move: a malformed
        # id failed the request once the rename was committed on the data.
        self.generate_fixture_asset()
        self.asset.update({"data": {"difficulty": "hard"}})
        difficulty = self.add("Difficulty")
        with self.assertRaises(DepartmentNotFoundException):
            projects_service.update_metadata_descriptor(
                difficulty["id"],
                {"name": "Complexity", "departments": ["not-a-uuid"]},
            )
        self.assertEqual(
            Entity.get(self.asset.id).data, {"difficulty": "hard"}
        )

    def test_rename_metadata_descriptor_to_a_name_too_long(self):
        # The name and field name columns hold 120 characters: a longer
        # name, or a name whose slug is longer, failed the update of the
        # descriptor once the values had moved to the new key. A Chinese
        # character slugifies to about five letters.
        self.generate_fixture_asset()
        self.asset.update({"data": {"difficulty": "hard"}})
        difficulty = self.add("Difficulty")
        for name in ("A" * 121, "\u955c" * 31):
            with self.subTest(name=name):
                with self.assertRaises(WrongParameterException):
                    projects_service.update_metadata_descriptor(
                        difficulty["id"], {"name": name}
                    )
                self.assertEqual(
                    Entity.get(self.asset.id).data, {"difficulty": "hard"}
                )

    def test_rename_metadata_descriptor_commits_the_values_with_it(self):
        # The moved values wait for the commit of the descriptor update, so
        # that a failure of that update rolls them back too. A real failure
        # cannot run here: each test runs in one transaction, which the
        # rollback would end, fixtures included. So no commit may carry the
        # moved values before the descriptor holds its new field name. Other
        # commits can come first: the asset query creates the entity types
        # the fixtures lack, such as Concept.
        from unittest import mock
        from zou.app import db

        task = self.generate_fixture_task()
        for entity_type, task_type_id, model, row_id in (
            ("Asset", None, Entity, self.asset.id),
            ("Task", self.task_type.id, Task, task.id),
            ("Project", None, Project, self.project.id),
        ):
            with self.subTest(entity_type=entity_type):
                difficulty = self.add(
                    "Difficulty", entity_type, task_type_id=task_type_id
                )
                model.get(row_id).update({"data": {"difficulty": "hard"}})
                descriptor = MetadataDescriptor.get(difficulty["id"])
                commit = db.session.commit
                commits = []

                def record_commit():
                    moved = "complexity" in (model.get(row_id).data or {})
                    commits.append((descriptor.field_name, moved))
                    commit()

                with mock.patch.object(
                    db.session, "commit", side_effect=record_commit
                ):
                    projects_service.update_metadata_descriptor(
                        difficulty["id"], {"name": "Complexity"}
                    )

                self.assertIn(("complexity", True), commits)
                self.assertNotIn(("difficulty", True), commits)
                self.assertEqual(
                    model.get(row_id).data, {"complexity": "hard"}
                )

    def test_rename_metadata_descriptor_on_projects_checks_them_all_first(
        self,
    ):
        # The projects renamed before the one holding the new name kept the
        # rename. Each project holds that column in turn, so that one of
        # the runs reaches the other project first, whatever order the
        # query returns them in.
        first_project = self.project
        second_project = self.generate_fixture_project(name="Second Project")
        projects = (first_project, second_project)
        project_ids = [str(project.id) for project in projects]
        for index, colliding in enumerate(projects):
            with self.subTest(colliding=index):
                old_field = f"code_{index}"
                new_name = f"Label {index}"
                new_field = f"label_{index}"
                for project in projects:
                    projects_service.add_metadata_descriptor(
                        project.id,
                        "Project",
                        f"Code {index}",
                        "string",
                        [],
                        False,
                    )
                    project.update({"data": {old_field: "old"}})
                projects_service.add_metadata_descriptor(
                    colliding.id, "Project", new_name, "string", [], False
                )
                colliding.update(
                    {"data": {old_field: "old", new_field: "kept"}}
                )

                with self.assertRaises(WrongParameterException):
                    projects_service.update_metadata_descriptor_on_projects(
                        project_ids, "Project", old_field, {"name": new_name}
                    )

                for project in projects:
                    field_names = [
                        descriptor["field_name"]
                        for descriptor in (
                            projects_service.get_metadata_descriptors(
                                project.id
                            )
                        )
                    ]
                    self.assertIn(old_field, field_names)
                    self.assertEqual(
                        Project.get(project.id).data.get(old_field), "old"
                    )
                self.assertEqual(
                    Project.get(colliding.id).data.get(new_field), "kept"
                )

    def test_remove_metadata_descriptor_of_an_unlisted_type(self):
        # The admin CRUD route takes any entity type. No entity list shows
        # such a column, so removing it strips no value.
        entities = self.generate_entity_of_each_type()
        for entity_type, entity in entities.items():
            entity.update({"data": {"difficulty": entity_type}})
        descriptor = MetadataDescriptor.create(
            project_id=self.project.id,
            entity_type="Concept",
            name="Difficulty",
            data_type="string",
            field_name="difficulty",
        )

        projects_service.remove_metadata_descriptor(str(descriptor.id))

        self.assertEqual(
            self.stored_data(entities),
            {
                entity_type: {"difficulty": entity_type}
                for entity_type in entities
            },
        )

    def test_remove_metadata_descriptor_leaves_the_rows_without_value(self):
        # Only the rows holding a value are rewritten: the other shots keep
        # their modification date.
        filled = self.generate_fixture_shot()
        empty = self.generate_fixture_shot("P02")
        descriptor = self.add("Difficulty", "Shot")
        filled.update({"data": {"difficulty": "hard"}})
        updated_at = Entity.get(empty.id).updated_at

        projects_service.remove_metadata_descriptor(descriptor["id"])

        self.assertEqual(Entity.get(filled.id).data, {})
        self.assertEqual(Entity.get(empty.id).updated_at, updated_at)

    def test_remove_task_metadata_descriptor_leaves_the_tasks_without_value(
        self,
    ):
        # Same for a Task column: the tasks without a value keep their
        # modification date.
        filled = self.generate_fixture_task()
        empty = self.generate_fixture_task("Second")
        descriptor = projects_service.add_metadata_descriptor(
            self.project.id,
            "Task",
            "Difficulty",
            "string",
            [],
            False,
            task_type_id=self.task_type.id,
        )
        filled.update({"data": {"difficulty": "hard"}})
        empty.update({"data": {"other": "value"}})
        updated_at = Task.get(empty.id).updated_at

        projects_service.remove_metadata_descriptor(descriptor["id"])

        self.assertEqual(Task.get(filled.id).data, {})
        self.assertEqual(Task.get(empty.id).updated_at, updated_at)

    def test_reorder_metadata_descriptors(self):
        # Zone and Angle are created in the order that contradicts their
        # alphabetical one, which is the order the leftovers fall back to.
        descriptor1 = self.add("Contractor")
        descriptor2 = self.add("Zone")
        descriptor3 = self.add("Location")
        descriptor4 = self.add("Angle")
        descriptor5 = self.add("Status")

        self.assertEqual(
            len(projects_service.get_metadata_descriptors(self.project.id)), 5
        )

        reordered = projects_service.reorder_metadata_descriptors(
            self.project.id,
            "Asset",
            [
                str(descriptor3["id"]),
                str(descriptor1["id"]),
                str(descriptor5["id"]),
            ],
        )

        # The three named first, then the two left out, alphabetically
        # rather than in the order they were created.
        self.assertEqual(
            self.names_and_positions(reordered),
            [
                ("Location", 1),
                ("Contractor", 2),
                ("Status", 3),
                ("Angle", 4),
                ("Zone", 5),
            ],
        )

    def test_reorder_metadata_descriptors_all_included(self):
        descriptor1 = self.add("Contractor")
        descriptor2 = self.add("Environment")

        reordered = projects_service.reorder_metadata_descriptors(
            self.project.id,
            "Asset",
            [str(descriptor2["id"]), str(descriptor1["id"])],
        )

        self.assertEqual(
            self.names_and_positions(reordered),
            [("Environment", 1), ("Contractor", 2)],
        )

    def test_reorder_metadata_descriptors_empty_list(self):
        self.add("Contractor")
        self.add("Environment")
        self.add("Location")

        reordered = projects_service.reorder_metadata_descriptors(
            self.project.id, "Asset", []
        )

        # Naming none of them still renumbers, alphabetically.
        self.assertEqual(
            self.names_and_positions(reordered),
            [("Contractor", 1), ("Environment", 2), ("Location", 3)],
        )

    def test_reorder_metadata_descriptors_descriptor_not_found(self):
        self.add("Contractor")

        fake_id = "00000000-0000-0000-0000-000000000000"
        descriptor_ids = [fake_id]

        with self.assertRaises(WrongParameterException):
            projects_service.reorder_metadata_descriptors(
                self.project.id, "Asset", descriptor_ids
            )

    def test_reorder_metadata_descriptors_different_entity_type(self):
        self.add("Contractor")
        shot_descriptor = self.add("Location", "Shot")
        descriptor_ids = [str(shot_descriptor["id"])]

        with self.assertRaises(WrongParameterException):
            projects_service.reorder_metadata_descriptors(
                self.project.id, "Asset", descriptor_ids
            )

    def test_get_metadata_descriptor_raw(self):
        descriptor = self.add("Weight")
        raw = projects_service.get_metadata_descriptor_raw(descriptor["id"])
        self.assertEqual(str(raw.id), descriptor["id"])
        self.assertRaises(
            MetadataDescriptorNotFoundException,
            projects_service.get_metadata_descriptor_raw,
            "wrong-id",
        )

    def test_get_metadata_descriptor(self):
        descriptor = self.add("Weight")
        result = projects_service.get_metadata_descriptor(descriptor["id"])
        self.assertEqual(result["id"], descriptor["id"])
        self.assertEqual(result["name"], "Weight")
