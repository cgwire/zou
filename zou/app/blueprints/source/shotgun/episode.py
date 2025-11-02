from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.project import Project
from zou.app.models.entity import Entity
from zou.app.services import shots_service, persons_service
from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)
from zou.app.blueprints.source.shotgun.exception import (
    ShotgunEntryImportFailed,
)


class ImportShotgunEpisodesResource(BaseImportShotgunResource):
    @jwt_required()
    def post(self):
        """
        Import shotgun episodes
        ---
        description: Import Shotgun episodes. Send a list of Shotgun episode
          entries in the JSON body. Returns created or updated episodes.
        tags:
          - Import
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      description: Shotgun ID of the episode
                      example: 12345
                    code:
                      type: string
                      description: Episode code
                      example: "EP01"
                    description:
                      type: string
                      description: Episode description
                      example: "First episode"
                    project:
                      type: object
                      description: Project information
                      properties:
                        name:
                          type: string
                          example: "My Project"
              example:
                - id: 12345
                  code: "EP01"
                  description: "First episode"
                  project:
                    name: "My Project"
        responses:
          200:
            description: Episodes imported successfully
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Episode unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Episode name
                        example: "EP01"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Update timestamp
                        example: "2024-01-15T11:00:00Z"
          400:
            description: Invalid request body or data format error
        """
        return super().post()

    def prepare_import(self):
        self.episode_type = shots_service.get_episode_type()
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
            current_app.logger.info("Episode created: %s" % episode)

        else:
            episode.update(data)
            episode.save()
            current_app.logger.info("Episode updated: %s" % episode)

        return episode


class ImportRemoveShotgunEpisodeResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(
            self, Entity, entity_type_id=shots_service.get_episode_type()["id"]
        )

    @jwt_required()
    def post(self):
        """
        Remove shotgun episode
        ---
        description: Remove a Shotgun episode from the database. Provide the
          Shotgun entry ID in the JSON body.
        tags:
          - Import
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - id
                properties:
                  id:
                    type: integer
                    description: Shotgun ID of the episode to remove
                    example: 12345
              example:
                id: 12345
        responses:
          200:
            description: Removal result returned
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: boolean
                      description: Whether the removal was successful
                      example: true
                    removed_instance_id:
                      type: string
                      format: uuid
                      description: ID of the removed episode, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
