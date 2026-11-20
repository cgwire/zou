from zou.app.blueprints.source.csv.entities import (
    BaseCsvEntityImportResource,
)
from zou.app.services import entity_types_service, shots_service
from zou.app.services.tasks_service import get_tasks_for_sequence
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class SequencesCsvImportResource(BaseCsvEntityImportResource):
    entity_type_name = "Sequence"
    # A sequence outside any episode shows on no episode page.
    is_episode_required = True

    @swag_from(SPECS["SequencesCsvImportResource_post"])
    def post(self, project_id):
        """
        Import sequences csv
        """
        return super().post(project_id)

    def get_entity_type(self):
        return entity_types_service.get_sequence_type()

    def create_entity(self, project_id, name, parent_id, values):
        return shots_service.create_sequence(
            project_id,
            parent_id,
            name,
            description=values.get("description", ""),
            data=values["data"],
            created_by=self.current_user_id,
        )

    def update_entity(self, entity_id, values):
        return shots_service.update_sequence(entity_id, values)

    def get_tasks(self, entity_id):
        return get_tasks_for_sequence(entity_id, relations=True)
