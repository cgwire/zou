from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.project import Project
from zou.app.models.entity import Entity

from zou.app.services import shots_service, persons_service

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunShotsResource(BaseImportShotgunResource):
    def __init__(self):
        BaseImportShotgunResource.__init__(self)

    @jwt_required()
    def post(self):
        """
        Import shotgun shots
        ---
        description: Import Shotgun shots. Send a list of Shotgun shot
          entries in the JSON body. Returns created or updated shots with
          frame ranges, custom fields, and asset links.
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
                      description: Shotgun ID of the shot
                      example: 12345
                    code:
                      type: string
                      description: Shot code
                      example: "SH010"
                    sg_cut_in:
                      type: integer
                      description: Cut in frame
                      example: 1001
                    sg_cut_duration:
                      type: integer
                      description: Cut duration in frames
                      example: 50
                    project:
                      type: object
                      description: Project information
                      properties:
                        name:
                          type: string
                          example: "My Project"
                    sg_sequence:
                      type: object
                      description: Sequence information
                      properties:
                        id:
                          type: integer
                          example: 11111
                    sg_scene:
                      type: object
                      description: Scene information
                      properties:
                        id:
                          type: integer
                          example: 22222
                    assets:
                      type: array
                      description: Linked assets
                      items:
                        type: object
                        properties:
                          id:
                            type: integer
                            example: 33333
              example:
                - id: 12345
                  code: "SH010"
                  sg_cut_in: 1001
                  sg_cut_duration: 50
                  project:
                    name: "My Project"
                  sg_sequence:
                    id: 11111
                  sg_scene:
                    id: 22222
                  assets:
                    - id: 33333
        responses:
          200:
            description: Shots imported successfully
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
                        description: Shot unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Shot name
                        example: "SH010"
                      data:
                        type: object
                        description: Shot data with frame ranges and custom
                          fields
                        example:
                          frame_in: 1001
                          frame_out: 1051
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
        self.shot_type = shots_service.get_shot_type()
        self.project_map = Project.get_id_map(field="name")
        self.current_user_id = persons_service.get_current_user()["id"]

    def extract_status_names(self, sg_projects):
        return {x["sg_status"] for x in sg_projects}

    def extract_data(self, sg_shot):
        (frame_in, frame_out) = self.extract_frame_range(sg_shot)
        custom_fields = self.extract_custom_data(sg_shot)
        project_id = self.get_project(sg_shot, self.project_map)
        sequence_id = self.get_sequence(sg_shot)
        scene_id = self.get_scene(sg_shot)
        assets = self.extract_assets(sg_shot)

        shot_type = shots_service.get_shot_type()

        data = {
            "name": sg_shot["code"],
            "shotgun_id": sg_shot["id"],
            "project_id": project_id,
            "entity_type_id": shot_type["id"],
            "parent_id": sequence_id,
            "source_id": scene_id,
            "entities_out": assets,
        }
        data_field_content = {"frame_in": frame_in, "frame_out": frame_out}
        custom_fields.update(data_field_content)
        data["data"] = custom_fields
        return data

    def get_project(self, sg_shot, project_map):
        project_id = None
        if sg_shot["project"] is not None:
            project_id = project_map.get(sg_shot["project"]["name"], None)
        return project_id

    def get_scene(self, sg_shot):
        scene_id = None
        if "sg_scene" in sg_shot and sg_shot["sg_scene"] is not None:
            scene_id = self.get_scene_id(sg_shot["sg_scene"]["id"])
        return scene_id

    def get_sequence(self, sg_shot):
        sequence_id = None
        if "sg_sequence" in sg_shot and sg_shot["sg_sequence"] is not None:
            sequence_id = self.get_sequence_id(sg_shot["sg_sequence"]["id"])
        return sequence_id

    def extract_frame_range(self, sg_shot):
        frame_in = sg_shot["sg_cut_in"]
        frame_out = frame_in
        if frame_in is not None and sg_shot["sg_cut_duration"] is not None:
            frame_out = sg_shot["sg_cut_in"] + sg_shot["sg_cut_duration"]
        return (frame_in, frame_out)

    def extract_assets(self, sg_shot):
        assets = []
        if "assets" in sg_shot and len(sg_shot["assets"]) > 0:
            for sg_asset in sg_shot["assets"]:
                entity_id = self.get_asset_id(sg_asset["id"])
                if entity_id is not None:
                    asset = Entity.get(entity_id)
                    assets.append(asset)
        return assets

    def is_custom_field(self, name):
        non_custom_fields = ["sg_cut_in", "sg_cut_out", "sg_sequence"]
        return name[:3] == "sg_" and name not in non_custom_fields

    def import_entry(self, data):
        shot = Entity.get_by(
            shotgun_id=data["shotgun_id"],
            entity_type_id=shots_service.get_shot_type()["id"],
        )

        if shot is None:
            shot = Entity.create(**data, created_by=self.current_user_id)
            current_app.logger.info("Shot created: %s" % shot)

        else:
            if shot.data is None:
                shot.data = {}
            shot.update(data)
            shot.data.update(data["data"])
            shot.save()
            shots_service.clear_shot_cache(str(shot.id))
            current_app.logger.info("Shot updated: %s" % shot)

        return shot


class ImportRemoveShotgunShotResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(
            self, Entity, entity_type_id=shots_service.get_shot_type()["id"]
        )

    @jwt_required()
    def post(self):
        """
        Remove shotgun shot
        ---
        description: Remove a Shotgun shot from the database. Provide the
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
                    description: Shotgun ID of the shot to remove
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
                      description: ID of the removed shot, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
