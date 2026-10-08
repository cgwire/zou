from flasgger import swag_from
from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.project import Project
from zou.app.models.entity import Entity
from zou.app.services import (
    persons_service,
    entity_types_service,
)
from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)
from zou.app.blueprints.source.shotgun.exception import (
    ShotgunEntryImportFailed,
)


class ImportShotgunEpisodesResource(BaseImportShotgunResource):
    @jwt_required()
    @swag_from("openapi/ImportShotgunEpisodesResource_post.yml")
    def post(self):
        """
        Import shotgun episodes
        """
        return super().post()

    def prepare_import(self):
        self.episode_type = entity_types_service.get_episode_type()
        self.project_map = Project.get_id_map(field="name")
        self.current_user_id = persons_service.get_current_user()["id"]

    def extract_data(self, sg_episode):
        project_id = self.get_project(sg_episode)
        if project_id is None:
            raise ShotgunEntryImportFailed

        return {
            "name": sg_episode["code"],
            "shotgun_id": sg_episode["id"],
            "description": sg_episode["description"],
            "project_id": project_id,
            "entity_type_id": self.episode_type["id"],
        }

    def get_project(self, sg_episode):
        project_id = None
        if sg_episode["project"] is not None:
            project_name = sg_episode["project"]["name"]
            project_id = self.project_map.get(project_name, None)
        return project_id

    def import_entry(self, data):
        episode = Entity.get_by(
            shotgun_id=data["shotgun_id"],
            entity_type_id=self.episode_type["id"],
        )

        if episode is None:
            episode = Entity.create(**data, created_by=self.current_user_id)
            current_app.logger.info(f"Episode created: {episode}")

        else:
            episode.update(data)
            episode.save()
            current_app.logger.info(f"Episode updated: {episode}")

        return episode


class ImportRemoveShotgunEpisodeResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(
            self,
            Entity,
            entity_type_id=entity_types_service.get_episode_type()["id"],
        )

    @jwt_required()
    @swag_from("openapi/ImportRemoveShotgunEpisodeResource_post.yml")
    def post(self):
        """
        Remove shotgun episode
        """
        return super().post()
