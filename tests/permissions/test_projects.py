from flask_jwt_extended import verify_jwt_in_request

from zou.app import app
from zou.app.services import (
    entities_service,
    permissions_service,
    metadata_descriptors_service,
)
from zou.app.utils import permissions
from tests.permissions.cases import DemotedRoleTestCase


class ProjectReadRoleTestCase(DemotedRoleTestCase):
    """
    crud/project.py ProjectResource.get_serialized_instance checks the
    project access before narrowing the metadata descriptors it serves, so
    a demoted client only reads the ones published to clients, as the
    metadata descriptors route serves them.
    """

    def test_demoted_client_reads_the_published_descriptors_only(self):
        project_id = str(self.project.id)
        metadata_descriptors_service.add_metadata_descriptor(
            project_id, "Asset", "Contractor", "list", ["in", "out"], False
        )
        published = metadata_descriptors_service.add_metadata_descriptor(
            project_id, "Asset", "Delivery", "list", ["in", "out"], True
        )
        self.demote_manager("client")

        project = self.get(f"data/projects/{project_id}")

        self.assertEqual(
            [entry["id"] for entry in project["descriptors"]],
            [published["id"]],
        )


class MetadataDescriptorsRoleTestCase(DemotedRoleTestCase):
    """
    projects/resources.py ProductionMetadataDescriptorsResource.get narrows
    the descriptors on the role its access check resolves, so a demoted
    vendor only reads the ones of their departments, here of none.
    """

    def test_demoted_vendor_reads_the_descriptors_of_no_department(self):
        project_id = str(self.project.id)
        shared = metadata_descriptors_service.add_metadata_descriptor(
            project_id, "Asset", "Contractor", "string", [], False
        )
        metadata_descriptors_service.add_metadata_descriptor(
            project_id,
            "Asset",
            "Rig",
            "string",
            [],
            False,
            [str(self.department.id)],
        )
        self.demote_manager("vendor")

        descriptors = self.get(
            f"data/projects/{project_id}/metadata-descriptors"
        )

        self.assertEqual(
            [entry["id"] for entry in descriptors], [shared["id"]]
        )


class EntityMetadataRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: permissions_service.check_metadata_department_access
    resolves check_belong_to_project before has_manager/has_supervisor, so
    a demoted manager loses entity metadata write access.

    Exercised at the service level: crud/entity.py's EntityResource.put
    wraps check_update_permissions in a bare `except Exception` that
    downgrades PermissionDenied (403) to 400 before the response reaches
    the client, a pre-existing bug unrelated to this fix. Calling the
    service directly under a real, JWT-verified request context isolates
    the ordering fix from that unrelated bug.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_asset()

    def test_demoted_manager_cannot_update_entity_metadata(self):
        self.demote_manager("user")
        entity = entities_service.get_entity(str(self.asset.id))
        with app.test_request_context(headers=self.auth_headers):
            verify_jwt_in_request()
            self.assertRaises(
                permissions.PermissionDenied,
                permissions_service.check_metadata_department_access,
                entity,
                {"name": "Updated Tree"},
            )


class AllDepartmentsAccessRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: permissions_service.check_all_departments_access resolves
    check_belong_to_project before has_manager/has_supervisor, so a
    demoted manager loses department-wide access.
    """

    def test_demoted_manager_cannot_create_metadata_descriptor(self):
        self.demote_manager("user")
        data = {
            "name": "Custom Field",
            "data_type": "string",
            "entity_type": "Asset",
        }
        self.post(
            f"data/projects/{self.project.id}/metadata-descriptors",
            data,
            403,
        )
