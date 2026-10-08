from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.services import metadata_descriptors_service
from zou.app.exceptions import (
    DepartmentNotFoundException,
    MetadataDescriptorNotFoundException,
    WrongParameterException,
)
from zou.app.models.project import Project
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.task import Task


class VendorMetadataTestCase(ApiDBTestCase):
    """
    A vendor sees the custom fields of their own departments only. The two
    halves are separate on purpose: one reads the descriptors of the
    production, the other strips a payload with what it was handed.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.project_id = str(self.project.id)
        self.own_department = str(self.department.id)
        self.other_department = str(self.department_animation.id)

    def a_descriptor(self, name, entity_type="Asset", departments=None):
        return metadata_descriptors_service.add_metadata_descriptor(
            self.project_id,
            entity_type,
            name,
            "string",
            [],
            False,
            departments=departments or [],
        )

    def test_a_descriptor_of_no_department_is_visible_to_everyone(self):
        self.a_descriptor("Contractor")

        self.assertEqual(
            metadata_descriptors_service.get_not_allowed_descriptors_fields_for_vendor(
                departments=[], projects_ids=[self.project_id]
            ),
            {self.project_id: []},
        )

    def test_a_descriptor_of_another_department_is_hidden(self):
        self.a_descriptor("Rig Notes", departments=[self.other_department])

        self.assertEqual(
            metadata_descriptors_service.get_not_allowed_descriptors_fields_for_vendor(
                departments=[self.own_department],
                projects_ids=[self.project_id],
            ),
            {self.project_id: ["rig_notes"]},
        )

    def test_a_descriptor_of_ones_own_department_stays_visible(self):
        self.a_descriptor("Rig Notes", departments=[self.own_department])

        self.assertEqual(
            metadata_descriptors_service.get_not_allowed_descriptors_fields_for_vendor(
                departments=[self.own_department],
                projects_ids=[self.project_id],
            ),
            {self.project_id: []},
        )

    def test_the_kind_of_entity_is_taken_into_account(self):
        self.a_descriptor(
            "Rig Notes",
            entity_type="Shot",
            departments=[self.other_department],
        )

        self.assertEqual(
            metadata_descriptors_service.get_not_allowed_descriptors_fields_for_vendor(
                entity_type="Asset",
                departments=[self.own_department],
                projects_ids=[self.project_id],
            ),
            {self.project_id: []},
        )

    def test_remove_not_allowed_fields_from_metadata(self):
        data = {"rig_notes": "secret", "contractor": "Acme"}

        self.assertEqual(
            metadata_descriptors_service.remove_not_allowed_fields_from_metadata(
                ["rig_notes"], data
            ),
            {"contractor": "Acme"},
        )
        self.assertEqual(
            metadata_descriptors_service.remove_not_allowed_fields_from_metadata(
                [], data
            ),
            data,
        )
        self.assertEqual(
            metadata_descriptors_service.remove_not_allowed_fields_from_metadata(),
            {},
        )


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
        return metadata_descriptors_service.add_metadata_descriptor(
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
        descriptor = metadata_descriptors_service.add_metadata_descriptor(
            self.project.id,
            "Asset",
            "Contractor",
            "list",
            ["contractor 1", "contractor 2"],
            False,
        )
        descriptors = metadata_descriptors_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(len(descriptors), 2)
        self.assertEqual(descriptors[0]["id"], descriptor["id"])
        self.assertEqual(descriptors[0]["field_name"], "contractor")
        self.assertEqual(descriptors[1]["field_name"], "is_outdoor")

        descriptors = metadata_descriptors_service.get_metadata_descriptors(
            self.project.id, for_client=True
        )
        self.assertEqual(descriptors, [])

    def test_update_metadata_descriptor(self):
        asset = self.generate_fixture_asset_type()
        asset = self.generate_fixture_asset()
        descriptor = self.add("Contractor")
        asset.update({"data": {"contractor": "contractor 1"}})
        self.assertIn("contractor", asset.data)
        metadata_descriptors_service.update_metadata_descriptor(
            descriptor["id"], {"name": "Team", "for_client": True}
        )
        descriptors = metadata_descriptors_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(len(descriptors), 1)
        self.assertTrue(descriptors[0]["for_client"])
        asset = Entity.get(asset.id)
        self.assertEqual(asset.data.get("team"), "contractor 1")

    def test_update_project_metadata_descriptor_renames_project_data(self):
        descriptor = self.add("Studio code", "Project")
        self.project.update({"data": {"studio_code": "A1"}})
        metadata_descriptors_service.update_metadata_descriptor(
            descriptor["id"], {"name": "Code", "for_client": False}
        )
        self.project = Project.get(self.project.id)
        self.assertEqual(self.project.data.get("code"), "A1")
        self.assertIsNone(self.project.data.get("studio_code"))

    def test_remove_project_metadata_descriptor_clears_project_data(self):
        descriptor = self.add("Studio code", "Project")
        self.project.update({"data": {"studio_code": "A1"}})
        metadata_descriptors_service.remove_metadata_descriptor(
            descriptor["id"]
        )
        self.project = Project.get(self.project.id)
        self.assertIsNone((self.project.data or {}).get("studio_code"))
        self.assertEqual(
            [
                d
                for d in metadata_descriptors_service.get_metadata_descriptors(
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
        reordered = metadata_descriptors_service.reorder_metadata_descriptors(
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

        metadata_descriptors_service.remove_metadata_descriptor(
            descriptor["id"]
        )
        descriptors = metadata_descriptors_service.get_metadata_descriptors(
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

                metadata_descriptors_service.remove_metadata_descriptor(
                    descriptor["id"]
                )

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

                metadata_descriptors_service.update_metadata_descriptor(
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
                    metadata_descriptors_service.update_metadata_descriptor(
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
            metadata_descriptors_service.update_metadata_descriptor(
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
        metadata_descriptors_service.add_metadata_descriptor(
            other_project.id, "Asset", "Complexity", "string", [], False
        )
        for name, field_name in (
            ("DIFFICULTY", "difficulty"),
            ("Weight", "weight"),
            ("Complexity", "complexity"),
        ):
            with self.subTest(name=name):
                descriptor = (
                    metadata_descriptors_service.update_metadata_descriptor(
                        difficulty["id"], {"name": name}
                    )
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
            metadata_descriptors_service.update_metadata_descriptor(
                layer["id"], {"name": "Pass"}
            )
        self.assertEqual(
            Task.get(task.id).data, {"layer": "bg", "pass": "beauty"}
        )

        metadata_descriptors_service.update_metadata_descriptor(
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
            metadata_descriptors_service.update_metadata_descriptor(
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
                    metadata_descriptors_service.update_metadata_descriptor(
                        difficulty["id"], {"name": name}
                    )
                self.assertEqual(
                    Entity.get(self.asset.id).data, {"difficulty": "hard"}
                )

    def test_update_metadata_descriptor_without_a_name(self):
        # A body may leave the name out: the update keeps the column name
        # instead of failing on it with a 500, and applies the rest. An
        # empty name left the column without one.
        difficulty = self.add("Difficulty")
        for name in (None, ""):
            with self.subTest(name=name):
                descriptor = (
                    metadata_descriptors_service.update_metadata_descriptor(
                        difficulty["id"],
                        {
                            "name": name,
                            "for_client": True,
                            "data_type": "string",
                        },
                    )
                )
                self.assertEqual(descriptor["name"], "Difficulty")
                self.assertEqual(descriptor["field_name"], "difficulty")
                self.assertTrue(descriptor["for_client"])

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
                    metadata_descriptors_service.update_metadata_descriptor(
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
                    metadata_descriptors_service.add_metadata_descriptor(
                        project.id,
                        "Project",
                        f"Code {index}",
                        "string",
                        [],
                        False,
                    )
                    project.update({"data": {old_field: "old"}})
                metadata_descriptors_service.add_metadata_descriptor(
                    colliding.id, "Project", new_name, "string", [], False
                )
                colliding.update(
                    {"data": {old_field: "old", new_field: "kept"}}
                )

                with self.assertRaises(WrongParameterException):
                    metadata_descriptors_service.update_metadata_descriptor_on_projects(
                        project_ids, "Project", old_field, {"name": new_name}
                    )

                for project in projects:
                    field_names = [
                        descriptor["field_name"]
                        for descriptor in (
                            metadata_descriptors_service.get_metadata_descriptors(
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

        metadata_descriptors_service.remove_metadata_descriptor(
            str(descriptor.id)
        )

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

        metadata_descriptors_service.remove_metadata_descriptor(
            descriptor["id"]
        )

        self.assertEqual(Entity.get(filled.id).data, {})
        self.assertEqual(Entity.get(empty.id).updated_at, updated_at)

    def test_remove_task_metadata_descriptor_leaves_the_tasks_without_value(
        self,
    ):
        # Same for a Task column: the tasks without a value keep their
        # modification date.
        filled = self.generate_fixture_task()
        empty = self.generate_fixture_task("Second")
        descriptor = metadata_descriptors_service.add_metadata_descriptor(
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

        metadata_descriptors_service.remove_metadata_descriptor(
            descriptor["id"]
        )

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
            len(
                metadata_descriptors_service.get_metadata_descriptors(
                    self.project.id
                )
            ),
            5,
        )

        reordered = metadata_descriptors_service.reorder_metadata_descriptors(
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

        reordered = metadata_descriptors_service.reorder_metadata_descriptors(
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

        reordered = metadata_descriptors_service.reorder_metadata_descriptors(
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
            metadata_descriptors_service.reorder_metadata_descriptors(
                self.project.id, "Asset", descriptor_ids
            )

    def test_reorder_metadata_descriptors_different_entity_type(self):
        self.add("Contractor")
        shot_descriptor = self.add("Location", "Shot")
        descriptor_ids = [str(shot_descriptor["id"])]

        with self.assertRaises(WrongParameterException):
            metadata_descriptors_service.reorder_metadata_descriptors(
                self.project.id, "Asset", descriptor_ids
            )

    def test_get_metadata_descriptor_raw(self):
        descriptor = self.add("Weight")
        raw = metadata_descriptors_service.get_metadata_descriptor_raw(
            descriptor["id"]
        )
        self.assertEqual(str(raw.id), descriptor["id"])
        self.assertRaises(
            MetadataDescriptorNotFoundException,
            metadata_descriptors_service.get_metadata_descriptor_raw,
            "wrong-id",
        )

    def test_get_metadata_descriptor(self):
        descriptor = self.add("Weight")
        result = metadata_descriptors_service.get_metadata_descriptor(
            descriptor["id"]
        )
        self.assertEqual(result["id"], descriptor["id"])
        self.assertEqual(result["name"], "Weight")
