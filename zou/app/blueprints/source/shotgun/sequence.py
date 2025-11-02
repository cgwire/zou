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


class ImportShotgunSequencesResource(BaseImportShotgunResource):
    @jwt_required()
    def post(self):
        """
        Import shotgun sequences
        ---
        description: Import Shotgun sequences. Send a list of Shotgun
          sequence entries in the JSON body. Returns created or updated
          sequences linked to episodes.
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
                      description: Shotgun ID of the sequence
                      example: 12345
                    code:
                      type: string
                      description: Sequence code
                      example: "SQ01"
                    description:
                      type: string
                      description: Sequence description
                      example: "Main sequence"
                    project:
                      type: object
                      description: Project information
                      properties:
                        name:
                          type: string
                          example: "My Project"
                    episode:
                      type: object
                      description: Episode information
                      properties:
                        id:
                          type: integer
                          example: 11111
              example:
                - id: 12345
                  code: "SQ01"
                  description: "Main sequence"
                  project:
                    name: "My Project"
                  episode:
                    id: 11111
        responses:
          200:
            description: Sequences imported successfully
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
                        description: Sequence unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Sequence name
                        example: "SQ01"
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
        self.sequence_type = shots_service.get_sequence_type()
        self.project_map = Project.get_id_map(field="name")
        self.current_user_id = persons_service.get_current_user()["id"]

    def get_episode(self, sg_sequence):
        sg_episode = sg_sequence.get("episode", {"id": None})
        if sg_episode is not None:
            episode_sg_id = sg_episode.get("id", None)
            return self.get_episode_id(episode_sg_id)
        else:
            return None

    def extract_data(self, sg_sequence):
        project_id = self.get_project(sg_sequence)
        episode_id = self.get_episode(sg_sequence)
        if project_id is None:
            raise ShotgunEntryImportFailed
        return {
            "name": sg_sequence["code"],
            "shotgun_id": sg_sequence["id"],
            "description": sg_sequence["description"],
            "project_id": project_id,
            "parent_id": episode_id,
            "entity_type_id": self.sequence_type["id"],
        }

    def get_project(self, sg_sequence):
        project_id = None
        if sg_sequence["project"] is not None:
            project_name = sg_sequence["project"]["name"]
            project_id = self.project_map.get(project_name, None)
        return project_id

    def import_entry(self, data):
        sequence = Entity.get_by(
            shotgun_id=data["shotgun_id"],
            entity_type_id=self.sequence_type["id"],
        )

        similar_sequence = Entity.get_by(
            name=data["name"],
            parent_id=data["parent_id"],
            project_id=data["project_id"],
            entity_type_id=self.sequence_type["id"],
        )

        if sequence is None and similar_sequence is None:
            sequence = Entity.create(**data, created_by=self.current_user_id)
            current_app.logger.info("Sequence created: %s" % sequence)

        elif sequence is not None:
            if similar_sequence is None:
                sequence.update(data)
                sequence.save()
            else:
                sequence.update(
                    {
                        "description": data["description"],
                        "shotgun_id": data["shotgun_id"],
                    }
                )
                sequence.save()
            current_app.logger.info("Sequence updated: %s" % sequence)

        return sequence


class ImportRemoveShotgunSequenceResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(
            self,
            Entity,
            entity_type_id=shots_service.get_sequence_type()["id"],
        )

    @jwt_required()
    def post(self):
        """
        Remove shotgun sequence
        ---
        description: Remove a Shotgun sequence from the database. Provide the
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
                    description: Shotgun ID of the sequence to remove
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
                      description: ID of the removed sequence, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
