from flask import current_app
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import IntegrityError

from zou.app.models.project import Project
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)

from zou.app.services import (
    assets_service,
    deletion_service,
    tasks_service,
    files_service,
    persons_service,
)

from zou.app.services.exception import AssetNotFoundException


class ImportShotgunAssetsResource(BaseImportShotgunResource):
    def __init__(self):
        BaseImportShotgunResource.__init__(self)

    @jwt_required()
    def post(self):
        """
        Import shotgun assets
        ---
        description: Import Shotgun assets. Send a list of Shotgun asset
          entries in the JSON body. Returns created or updated assets with
          parent-child relationships.
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
                      description: Shotgun ID of the asset
                      example: 12345
                    code:
                      type: string
                      description: Asset code
                      example: "Asset01"
                    description:
                      type: string
                      description: Asset description
                      example: "Main character asset"
                    sg_asset_type:
                      type: string
                      description: Asset type name
                      example: "Character"
                    project:
                      type: object
                      description: Project information
                      properties:
                        id:
                          type: integer
                          example: 11111
                    parents:
                      type: array
                      description: Parent assets
                      items:
                        type: object
                        properties:
                          id:
                            type: integer
                            example: 22222
              example:
                - id: 12345
                  code: "Asset01"
                  description: "Main character asset"
                  sg_asset_type: "Character"
                  project:
                    id: 11111
                  parents:
                    - id: 22222
        responses:
          200:
            description: Assets imported successfully
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
                        description: Asset unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Asset name
                        example: "Asset01"
                      description:
                        type: string
                        description: Asset description
                        example: "Main character asset"
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
        entity_type_names = self.extract_entity_type_names(self.sg_entries)
        assets_service.create_asset_types(entity_type_names)
        self.project_ids = Project.get_id_map()
        self.entity_type_ids = EntityType.get_id_map(field="name")
        self.parent_map = {}
        self.current_user_id = persons_service.get_current_user()["id"]

    def extract_entity_type_names(self, sg_assets):
        return {
            x["sg_asset_type"]
            for x in sg_assets
            if x["sg_asset_type"] is not None
        }

    def extract_data(self, sg_asset):
        entity_type_id = self.entity_type_ids.get(
            sg_asset["sg_asset_type"], None
        )
        project_id = self.project_ids.get(sg_asset["project"]["id"], None)
        parent_shotgun_ids = [
            asset["id"] for asset in sg_asset.get("parents", [])
        ]

        return {
            "name": sg_asset["code"],
            "shotgun_id": sg_asset["id"],
            "description": sg_asset["description"],
            "entity_type_id": entity_type_id,
            "project_id": project_id,
            "parent_shotgun_ids": parent_shotgun_ids,
        }

    def import_entry(self, data):
        entity = None
        parent_shotgun_ids = data["parent_shotgun_ids"]
        del data["parent_shotgun_ids"]

        try:
            entity = self.save_entity(data)
        except IntegrityError:
            current_app.logger.error(
                "Similar asset already exists "
                "or project is missing: %s" % data
            )

        if entity is not None:
            for parent_shotgun_id in parent_shotgun_ids:
                self.parent_map.setdefault(parent_shotgun_id, [])
                self.parent_map[parent_shotgun_id].append(
                    Entity.get(entity.id)
                )

        return entity

    def save_entity(self, data):
        entity = None
        try:
            entity = assets_service.get_raw_asset_by_shotgun_id(
                data["shotgun_id"]
            )
            entity.update(data)
            assets_service.clear_asset_cache(str(entity.id))
            current_app.logger.info("Entity updated: %s" % entity)
        except AssetNotFoundException:
            if data.get("entity_type_id", None) is not None:
                entity = Entity.create(**data, created_by=self.current_user_id)
                entity.save()
                current_app.logger.info("Entity created: %s" % entity)
            else:
                current_app.logger.info("Entity ignored: %s" % data["name"])
        return entity

    def post_processing(self):
        # We handle the fact that an asset can have multiple parents by using
        # the entities out field as a children field.
        for key in self.parent_map.keys():
            try:
                asset = assets_service.get_asset_by_shotgun_id(key)
                data = {"entities_out": self.parent_map[key]}
                assets_service.update_asset(asset["id"], data)
                assets_service.clear_asset_cache(asset["id"])
            except AssetNotFoundException:
                pass

        return self.parent_map


class ImportRemoveShotgunAssetResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(
            self, Entity, self.delete_func
        )

    @jwt_required()
    def post(self):
        """
        Remove shotgun asset
        ---
        description: Remove a Shotgun asset from the database. Provide the
          Shotgun entry ID in the JSON body. If the asset has working files
          linked to tasks, it will be cancelled instead of deleted.
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
                    description: Shotgun ID of the asset to remove
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
                      description: ID of the removed asset, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()

    def delete_func(self, asset):
        try:
            asset = assets_service.get_asset_by_shotgun_id(asset.shotgun_id)
            tasks = tasks_service.get_tasks_for_asset(asset["id"])
            if self.is_working_files_linked(tasks):
                assets_service.cancel_asset(asset["id"])
            else:
                for task in tasks:
                    deletion_service.remove_task(task["id"])
                assets_service.remove_asset(asset["id"])
            return asset
        except AssetNotFoundException:
            return None

    def is_working_files_linked(self, tasks):
        is_working_files = False
        for task in tasks:
            working_files = files_service.get_working_files_for_task(
                task["id"]
            )
            if len(working_files) > 0:
                is_working_files = True
                break
        return is_working_files
