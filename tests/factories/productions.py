from zou.app.services import (
    file_tree_service,
)

from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus


class ProductionFactories:
    """
    Projects, their statuses and metadata descriptors.
    """

    def generate_fixture_project_status(self):
        if hasattr(self, "open_status"):
            return
        self.open_status = ProjectStatus.create(name="Open", color="#FFFFFF")

    def generate_fixture_project_closed_status(self):
        if hasattr(self, "closed_status"):
            return
        self.closed_status = ProjectStatus.create(
            name="closed", color="#FFFFFF"
        )

    def generate_fixture_project(self, name="Cosmos Landromat"):
        if (
            name == "Cosmos Landromat"
            and hasattr(self, "project")
            and self.project.name == name
        ):
            return self.project
        self.generate_fixture_project_status()
        self.project = Project.create(
            name=name, project_status_id=self.open_status.id
        )
        self.project_id = self.project.id
        self.project.update(
            {"file_tree": file_tree_service.get_tree_from_file("simple")}
        )
        return self.project

    def generate_fixture_project_closed(self):
        if hasattr(self, "project_closed"):
            return
        self.generate_fixture_project_closed_status()
        self.project_closed = Project.create(
            name="Old Project", project_status_id=self.closed_status.id
        )

    def generate_fixture_project_standard(self):
        if hasattr(self, "project_standard"):
            return self.project_standard
        self.generate_fixture_project_status()
        self.project_standard = Project.create(
            name="Big Buck Bunny", project_status_id=self.open_status.id
        )
        self.project_standard.update(
            {"file_tree": file_tree_service.get_tree_from_file("default")}
        )
        return self.project_standard

    def generate_fixture_metadata_descriptor(self, entity_type="Asset"):
        self.meta_descriptor = MetadataDescriptor.create(
            project_id=self.project.id,
            name="Contractor",
            data_type="list",
            field_name="contractor",
            choices=["value 1", "value 2"],
            entity_type=entity_type,
        )
        return self.meta_descriptor
