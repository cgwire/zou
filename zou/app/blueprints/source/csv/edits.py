from zou.app.blueprints.source.csv.entities import (
    BaseCsvEntityImportResource,
)
from zou.app.services import edits_service, entity_types_service
from zou.app.services.tasks_service import get_tasks_for_edit
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class EditsCsvImportResource(BaseCsvEntityImportResource):
    entity_type_name = "Edit"

    @swag_from(SPECS["EditsCsvImportResource_post"])
    def post(self, project_id):
        """
        Import edits csv
        """
        return super().post(project_id)

    def get_entity_type(self):
        return entity_types_service.get_edit_type()

    def create_entity(self, project_id, name, parent_id, values):
        return edits_service.create_edit(
            project_id,
            name,
            data=values["data"],
            description=values.get("description", ""),
            parent_id=parent_id,
            created_by=self.current_user_id,
        )

    def update_entity(self, entity_id, values):
        return edits_service.update_edit(entity_id, values)

    def get_tasks(self, entity_id):
        return get_tasks_for_edit(entity_id)
