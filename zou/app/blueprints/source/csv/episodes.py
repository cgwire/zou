from zou.app.blueprints.source.csv.base import RowException
from zou.app.blueprints.source.csv.entities import (
    BaseCsvEntityImportResource,
)
from zou.app.exceptions import WrongParameterException
from zou.app.models.entity import ENTITY_STATUSES
from zou.app.services import (
    entity_types_service,
    projects_service,
    shots_service,
)
from zou.app.services.tasks_service import get_tasks_for_episode
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")

EPISODE_STATUSES = [status for status, _ in ENTITY_STATUSES]


class EpisodesCsvImportResource(BaseCsvEntityImportResource):
    entity_type_name = "Episode"
    has_episode = False

    @swag_from(SPECS["EpisodesCsvImportResource_post"])
    def post(self, project_id):
        """
        Import episodes csv
        """
        return super().post(project_id)

    def prepare_import(self, project_id):
        project = projects_service.get_project(project_id)
        if not projects_service.is_tv_show(project):
            raise WrongParameterException(
                "Episodes can only be imported in a TV show"
            )
        super().prepare_import(project_id)

    def get_extra_values(self, row):
        # An empty cell keeps the status: "running" for a new episode.
        status = (row.get("Status") or "").strip()
        if status == "":
            return {}
        if status.lower() not in EPISODE_STATUSES:
            raise RowException(f"Episode status not found for {status}")
        return {"status": status.lower()}

    def get_entity_type(self):
        return entity_types_service.get_episode_type()

    def create_entity(self, project_id, name, parent_id, values):
        return shots_service.create_episode(
            project_id,
            name,
            status=values.get("status", "running"),
            description=values.get("description", ""),
            data=values["data"],
            created_by=self.current_user_id,
        )

    def update_entity(self, entity_id, values):
        return shots_service.update_episode(entity_id, values)

    def get_tasks(self, entity_id):
        return get_tasks_for_episode(entity_id, relations=True)
