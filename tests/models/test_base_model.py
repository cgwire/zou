# -*- coding: UTF-8 -*-
from unittest import mock

from tests.base import ApiDBTestCase
from zou.app import db
from zou.app.models.department import Department
from zou.app.models.entity import Entity, EntityConceptLink
from zou.app.models.project import Project, ProjectTaskTypeLink
from zou.app.utils import fields


class BaseModelTestCase(ApiDBTestCase):
    def test_get_by(self):
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        project_id = self.generate_fixture_project("Second project").id
        project = Project.get_by(name="Second project")
        self.assertEqual(project.id, project_id)

    def test_get_all_by(self):
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        project_id = self.generate_fixture_project("Second project").id
        projects = Project.get_all_by(name="Second project")
        self.assertEqual(len(projects), 1)

        project = projects[0]
        self.assertEqual(project.id, project_id)

    def test_create(self):
        """
        create() persists the row and fills what the mixin owns: an id and
        the two timestamps, none of which the caller provides.
        """
        self.generate_fixture_project_status()
        project = Project.create(
            name="Fresh project", project_status_id=self.open_status.id
        )
        self.assertIsNotNone(project.id)
        self.assertIsNotNone(project.created_at)
        self.assertIsNotNone(project.updated_at)
        self.assertEqual(Project.get(project.id).name, "Fresh project")

    def test_get_id_map(self):
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        project_id = self.generate_fixture_project("Second project").id
        project_map = Project.get_id_map(field="name")
        self.assertIn("Second project", project_map)
        project_id_again = project_map["Second project"]
        self.assertEqual(project_id_again, project_id)

    def test_delete_all_by_no_commit(self):
        """
        delete_all_by_no_commit() expires the loaded instances, as a commit
        does: a collection still holding the objects linked by the deleted
        rows would make the flush deleting its owner delete those rows
        again, find none and fail.
        """
        asset = self.generate_fixture_asset()
        concept = Entity.create(
            name="Concept",
            project_id=self.project.id,
            entity_type_id=self.asset_type.id,
            entity_concept_links=[asset],
        )
        concept_id = concept.id
        self.assertEqual(len(concept.entity_concept_links), 1)
        EntityConceptLink.delete_all_by_no_commit(entity_in_id=concept_id)
        concept.delete()
        self.assertIsNone(Entity.get(concept_id))
        self.assertEqual(
            EntityConceptLink.get_all_by(entity_in_id=concept_id), []
        )

    def test_save_rolls_back_on_failure(self):
        self.generate_fixture_project_status()
        project = self.generate_fixture_project()
        with mock.patch.object(
            db.session, "commit", side_effect=RuntimeError("boom")
        ), mock.patch.object(db.session, "rollback") as rollback:
            with self.assertRaises(RuntimeError):
                project.save()
        rollback.assert_called_once_with()

    def test_commit_rolls_back_on_failure(self):
        with mock.patch.object(
            db.session, "commit", side_effect=RuntimeError("boom")
        ), mock.patch.object(db.session, "rollback") as rollback:
            with self.assertRaises(RuntimeError):
                Project.commit()
        rollback.assert_called_once_with()

    def test_update_resolves_relations_given_as_dicts_or_instances(self):
        self.generate_fixture_project_status()
        project = self.generate_fixture_project()
        self.generate_fixture_task_type()

        def linked_task_type_ids():
            return {
                str(link.task_type_id)
                for link in ProjectTaskTypeLink.get_all_by(
                    project_id=project.id
                )
            }

        project.update(
            {
                "task_types": [
                    {"id": str(self.task_type.id)},
                    self.task_type_modeling,
                ]
            }
        )
        self.assertEqual(
            linked_task_type_ids(),
            {str(self.task_type.id), str(self.task_type_modeling.id)},
        )
        # A null relation empties it.
        project.update({"task_types": None})
        self.assertEqual(linked_task_type_ids(), set())

    def test_create_from_import_list_reads_a_data_payload(self):
        department_id = str(fields.gen_uuid())
        Department.create_from_import_list(
            {
                "data": [
                    {
                        "id": department_id,
                        "name": "Lighting",
                        "color": "#000000",
                        "type": "Department",
                    }
                ]
            }
        )
        self.assertEqual(Department.get(department_id).name, "Lighting")

    def test_delete_from_import_ignores_an_unknown_id(self):
        self.generate_fixture_project_status()
        project = self.generate_fixture_project()
        unknown_id = str(fields.gen_uuid())
        self.assertEqual(Project.delete_from_import(unknown_id), unknown_id)
        self.assertIsNotNone(Project.get(project.id))

    def test_save(self):
        self.generate_fixture_project_status()
        project = self.generate_fixture_project()
        project.name = "new name"
        project.save()
        self.assertGreater(project.updated_at, project.created_at)
        project = Project.get(project.id)
        self.assertEqual(project.name, "new name")

    def test_delete(self):
        self.generate_fixture_project_status()
        project = self.generate_fixture_project()
        project.delete()
        project = Project.get(project.id)
        self.assertIsNone(project)

    def test_update(self):
        self.generate_fixture_project_status()
        project = self.generate_fixture_project()
        project.update({"name": "new name"})
        project = Project.get(project.id)
        self.assertEqual(project.name, "new name")
