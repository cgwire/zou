import pytest

from tests.base import ApiDBTestCase

from zou.app.services import base_service
from zou.app.models.entity import Entity
from zou.app.models.output_type import OutputType
from zou.app.models.project import Project
from zou.app.services.exception import (
    AssetNotFoundException,
    ProjectNotFoundException,
)


class BaseServiceTestCase(ApiDBTestCase):
    """
    The lookups every other service builds on: fetch a row or raise the
    caller's exception, and never make the caller tell a missing row from an
    id the driver would not accept.
    """

    def test_get_instance(self):
        project = Project.create(name="Test")

        found = base_service.get_instance(
            Project, project.id, ProjectNotFoundException
        )

        self.assertEqual(found.id, project.id)

    def test_get_instance_raises_on_anything_it_cannot_return(self):
        project = Project.create(name="Test")
        project.delete()
        cases = {
            "a deleted row": project.id,
            "no id at all": None,
            # Not a UUID: the driver raises a StatementError, which callers
            # must not have to tell apart from a missing row.
            "an id of the wrong shape": "unknown",
        }
        for reason, instance_id in cases.items():
            with self.subTest(reason=reason):
                with pytest.raises(ProjectNotFoundException):
                    base_service.get_instance(
                        Project, instance_id, ProjectNotFoundException
                    )

    def test_get_typed_instance(self):
        """
        The polymorphic lookup: an id alone does not say what an entity is,
        so the type has to match too.
        """
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()

        found = base_service.get_typed_instance(
            Entity,
            self.asset.id,
            self.asset_type.id,
            AssetNotFoundException,
        )

        self.assertEqual(found.id, self.asset.id)

    def test_get_typed_instance_raises_on_the_wrong_type(self):
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()

        with pytest.raises(AssetNotFoundException):
            base_service.get_typed_instance(
                Entity,
                self.asset.id,
                self.sequence_type.id,
                AssetNotFoundException,
            )

    def test_get_or_create_instance_by_name(self):
        self.assertIsNone(Project.get_by(name="Test"))

        project = base_service.get_or_create_instance_by_name(
            Project, name="Test"
        )

        self.assertEqual(project["name"], "Test")
        self.assertIsNotNone(Project.get_by(name="Test"))

    def test_get_or_create_instance_by_name_reuses_the_row(self):
        created = base_service.get_or_create_instance_by_name(
            Project, name="Test"
        )

        again = base_service.get_or_create_instance_by_name(
            Project, name="Test"
        )

        self.assertEqual(again["id"], created["id"])
        self.assertEqual(len(Project.query.filter_by(name="Test").all()), 1)

    def test_creating_by_name_announces_the_row(self):
        """
        Announced on creation only, under the table name. Driven through an
        output type, which is what the two real callers create, and which
        belongs to no production: the payload must then say nothing about a
        production rather than name one.
        """
        captured = self.capture_events("output_type:new")

        output_type = base_service.get_or_create_instance_by_name(
            OutputType, name="Cache", short_name="cch"
        )
        base_service.get_or_create_instance_by_name(
            OutputType, name="Cache", short_name="cch"
        )

        self.assertEqual(
            [event["output_type_id"] for event in captured],
            [output_type["id"]],
        )
        self.assertNotIn("project_id", captured[0])

    def test_creating_by_name_names_the_production_when_there_is_one(self):
        # Neither real caller creates a row that belongs to a production,
        # but the payload has to carry one that does.
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        captured = self.capture_events("entity:new")

        base_service.get_or_create_instance_by_name(
            Entity,
            name="Tree",
            project_id=self.project.id,
            entity_type_id=self.asset_type.id,
        )

        self.assertEqual(captured[0]["project_id"], str(self.project.id))

    def test_get_model_map_from_array(self):
        models = [
            {"id": "1", "name": "first"},
            {"id": "2", "name": "second"},
        ]

        self.assertEqual(
            base_service.get_model_map_from_array(models),
            {"1": models[0], "2": models[1]},
        )
