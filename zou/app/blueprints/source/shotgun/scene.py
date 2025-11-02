from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.project import Project
from zou.app.models.entity import Entity

from zou.app.services import shots_service, persons_service

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunScenesResource(BaseImportShotgunResource):
    def __init__(self):
        BaseImportShotgunResource.__init__(self)

    @jwt_required()
    def post(self):
        """
        Import shotgun scenes
        ---
        description: Import Shotgun scenes. Send a list of Shotgun scene
          entries in the JSON body. Returns created or updated scenes linked
          to sequences.
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
                      description: Shotgun ID of the scene
                      example: 12345
                    code:
                      type: string
                      description: Scene code
                      example: "SC01"
                    project:
                      type: object
                      description: Project information
                      properties:
                        name:
                          type: string
                          example: "My Project"
              example:
                - id: 12345
                  code: "SC01"
                  project:
                    name: "My Project"
        responses:
          200:
            description: Scenes imported successfully
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
                        description: Scene unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Scene name
                        example: "SC01"
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
        self.scene_type = shots_service.get_shot_type()
        self.project_map = Project.get_id_map(field="name")
        self.current_user_id = persons_service.get_current_user()["id"]

    def extract_data(self, sg_scene):
        project_id = self.get_project(sg_scene, self.project_map)
        sequence_id = self.get_sequence(sg_scene)
        scene_type = shots_service.get_scene_type()

        data = {
            "name": sg_scene["code"],
            "shotgun_id": sg_scene["id"],
            "project_id": project_id,
            "entity_type_id": scene_type["id"],
            "parent_id": sequence_id,
        }
        return data

    def get_project(self, sg_scene, project_map):
        project_id = None
        if sg_scene["project"] is not None:
            project_id = project_map.get(sg_scene["project"]["name"], None)
        return project_id

    def get_sequence(self, sg_scene):
        sequence_id = None
        sequence_key = "sequence_sg_scenes_1_sequences"
        if (
            sequence_key in sg_scene
            and sg_scene[sequence_key] is not None
            and len(sg_scene[sequence_key]) > 0
        ):
            sequence_id = self.get_sequence_id(sg_scene[sequence_key][0]["id"])
        return sequence_id

    def import_entry(self, data):
        scene = Entity.get_by(
            shotgun_id=data["shotgun_id"],
            entity_type_id=shots_service.get_scene_type()["id"],
        )

        if scene is None:
            scene = Entity.create(**data, created_by=self.current_user_id)
            current_app.logger.info("Scene created: %s" % scene)

        else:
            scene.update(data)
            scene.save()
            current_app.logger.info("Scene updated: %s" % scene)

        return scene

    def filtered_entries(self):
        return self.sg_entries


class ImportRemoveShotgunSceneResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(
            self, Entity, entity_type_id=shots_service.get_scene_type()["id"]
        )

    @jwt_required()
    def post(self):
        """
        Remove shotgun scene
        ---
        description: Remove a Shotgun scene from the database. Provide the
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
                    description: Shotgun ID of the scene to remove
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
                      description: ID of the removed scene, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
