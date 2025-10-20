from flask import request
from flask_restful import Resource, inputs
from flask_jwt_extended import jwt_required

from zou.app.utils import permissions, query
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    assets_service,
    breakdown_service,
    persons_service,
    shots_service,
    tasks_service,
    user_service,
)


def check_criterion_access(criterions):
    project_id = None
    if "project_id" in criterions:
        project_id = criterions.get("project_id", None)
    elif "episode_id" in criterions:
        episode_id = criterions.get("episode_id", None)
        project_id = shots_service.get_episode(episode_id)["project_id"]

    if "project_id" in criterions:
        user_service.check_project_access(project_id)
    return True


class AssetResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, asset_id):
        """
        Get asset
        ---
        description: Retrieve detailed information about a specific asset including metadata, project context, and related data
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            required: true
            description: Unique identifier of the asset
        responses:
          200:
            description: Asset information successfully retrieved
            content:
              application/json:
                schema:
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
                      example: "Character Name"
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    entity_type_id:
                      type: string
                      format: uuid
                      description: Asset type identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        asset = assets_service.get_full_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset["id"])
        return asset

    @jwt_required()
    def delete(self, asset_id):
        """
        Delete asset
        ---
        description: Permanently remove an asset from the system. Only asset creators or project managers can delete assets
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            required: true
            description: Unique identifier of the asset to delete
          - in: query
            name: force
            type: boolean
            required: false
            description: Force deletion bypassing validation checks
            example: false
        responses:
          204:
            description: Asset successfully deleted
        """
        force = self.get_force()

        asset = assets_service.get_full_asset(asset_id)
        if asset["created_by"] == persons_service.get_current_user()["id"]:
            user_service.check_belong_to_project(asset["project_id"])
        else:
            user_service.check_manager_project_access(asset["project_id"])

        assets_service.remove_asset(asset_id, force=force)
        return "", 204


class AllAssetsResource(Resource):

    @jwt_required()
    def get(self):
        """
        Get all assets
        ---
        description: Retrieve all production assets with filtering and pagination. Supports advanced filtering by project, asset type, task status, and other criteria
        tags:
          - Assets
        parameters:
          - in: query
            name: project_id
            type: string
            format: uuid
            description: Filter assets by specific project
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: asset_type_id
            type: string
            format: uuid
            description: Filter assets by asset type
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: page
            type: integer
            description: Page number for pagination
            example: 1
          - in: query
            name: limit
            type: integer
            description: Number of assets per page
            example: 100
        responses:
          200:
            description: List of assets successfully retrieved
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
                        example: "Character Name"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_type_id:
                        type: string
                        format: uuid
                        description: Asset type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      project_name:
                        type: string
                        description: Project name
                        example: "My Project"
                      asset_type_name:
                        type: string
                        description: Asset type name
                        example: "Character"
        """
        criterions = query.get_query_criterions_from_request(request)
        check_criterion_access(criterions)
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return assets_service.get_assets(
            criterions,
            is_admin=permissions.has_admin_permissions(),
        )


class AllAssetsAliasResource(AllAssetsResource):
    pass


class AssetsAndTasksResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self):
        """
        Get assets with tasks
        ---
        description: Retrieve all production assets with their related tasks. Includes project name, asset type name, and all associated tasks. Supports filtering by episode
        tags:
          - Assets
        parameters:
          - in: query
            name: project_id
            type: string
            format: uuid
            description: Filter assets by specific project
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: episode_id
            type: string
            format: uuid
            description: Filter assets by episode (returns assets not linked to episode and assets linked to given episode)
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: asset_type_id
            type: string
            format: uuid
            description: Filter assets by asset type
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: List of assets with tasks successfully retrieved
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
                        example: "Character Name"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_type_id:
                        type: string
                        format: uuid
                        description: Asset type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      project_name:
                        type: string
                        description: Project name
                        example: "My Project"
                      asset_type_name:
                        type: string
                        description: Asset type name
                        example: "Character"
                      tasks:
                        type: array
                        items:
                          type: object
                        description: Array of related tasks
        """
        criterions = query.get_query_criterions_from_request(request)
        check_criterion_access(criterions)
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
            criterions["vendor_departments"] = [
                str(department.id)
                for department in persons_service.get_current_user_raw().departments
            ]
        return assets_service.get_assets_and_tasks(criterions)


class AssetTypeResource(Resource):

    @jwt_required()
    def get(self, asset_type_id):
        """
        Get asset type
        ---
        description: Retrieve detailed information about a specific asset type including metadata and configuration
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_type_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            required: true
            description: Unique identifier of the asset type
        responses:
          200:
            description: Given asset type
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Asset type unique identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    name:
                      type: string
                      description: Asset type name
                      example: "Character"
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        return assets_service.get_asset_type(asset_type_id)


class AssetTypesResource(Resource):

    @jwt_required()
    def get(self):
        """
        Get asset types
        ---
        description: Retrieve all available asset types (entity types that are not shot, sequence, or episode) with filtering support
        tags:
          - Assets
        parameters:
          - in: query
            name: project_id
            type: string
            format: uuid
            description: Filter asset types by project
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: List of asset types successfully retrieved
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
                        description: Asset type unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      name:
                        type: string
                        description: Asset type name
                        example: "Character"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        criterions = query.get_query_criterions_from_request(request)
        return assets_service.get_asset_types(criterions)


class ProjectAssetTypesResource(Resource):

    @jwt_required()
    def get(self, project_id):
        """
        Get project asset types
        ---
        description: Retrieve all asset types available for a specific project
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            required: true
            description: Unique identifier of the project
        responses:
          200:
            description: List of project asset types successfully retrieved
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
                        description: Asset type unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      name:
                        type: string
                        description: Asset type name
                        example: "Character"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
        """
        user_service.check_project_access(project_id)
        return assets_service.get_asset_types_for_project(project_id)


class ShotAssetTypesResource(Resource):

    @jwt_required()
    def get(self, shot_id):
        """
        Get shot asset types
        ---
        description: Retrieve all asset types of assets that are casted in a specific shot
        tags:
          - Assets
        parameters:
          - in: path
            name: shot_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            required: true
            description: Unique identifier of the shot
        responses:
          200:
            description: List of shot asset types successfully retrieved
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
                        description: Asset type unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      name:
                        type: string
                        description: Asset type name
                        example: "Character"
                      shot_id:
                        type: string
                        format: uuid
                        description: Shot identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        return assets_service.get_asset_types_for_shot(shot_id)


class ProjectAssetsResource(Resource):

    @jwt_required()
    def get(self, project_id):
        """
        Get project assets
        ---
        description: Retrieve all assets belonging to a specific project with filtering support
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            required: true
            description: Unique identifier of the project
          - in: query
            name: asset_type_id
            type: string
            format: uuid
            description: Filter assets by asset type
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: page
            type: integer
            description: Page number for pagination
            example: 1
          - in: query
            name: limit
            type: integer
            description: Number of assets per page
            example: 100
        responses:
          200:
            description: List of project assets successfully retrieved
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
                        example: "Character Name"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_type_id:
                        type: string
                        format: uuid
                        description: Asset type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      project_name:
                        type: string
                        description: Project name
                        example: "My Project"
                      asset_type_name:
                        type: string
                        description: Asset type name
                        example: "Character"
        """
        user_service.check_project_access(project_id)
        criterions = query.get_query_criterions_from_request(request)
        criterions["project_id"] = project_id
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return assets_service.get_assets(criterions)


class ProjectAssetTypeAssetsResource(Resource):

    @jwt_required()
    def get(self, project_id, asset_type_id):
        """
        Get project asset type assets
        ---
        description: Retrieve all assets of a specific type within a project.
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: path
            name: asset_type_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset type
          - in: query
            name: page
            type: integer
            description: Page number for pagination
            example: 1
          - in: query
            name: limit
            type: integer
            description: Number of assets per page
            example: 100
        responses:
          200:
            description: List of project asset type assets successfully retrieved
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
                        example: "Character Name"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_type_id:
                        type: string
                        format: uuid
                        description: Asset type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      project_name:
                        type: string
                        description: Project name
                        example: "My Project"
                      asset_type_name:
                        type: string
                        description: Asset type name
                        example: "Character"
        """
        user_service.check_project_access(project_id)
        criterions = query.get_query_criterions_from_request(request)
        criterions["project_id"] = project_id
        criterions["entity_type_id"] = asset_type_id
        if permissions.has_vendor_permissions():
            criterions["assigned_to"] = persons_service.get_current_user()[
                "id"
            ]
        return assets_service.get_assets(criterions)


class AssetAssetsResource(Resource):

    @jwt_required()
    def get(self, asset_id):
        """
        Get linked assets
        ---
        description: Retrieve all assets that are linked to a specific asset through casting relationships
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
        responses:
          200:
            description: List of linked assets successfully retrieved
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
                        description: Linked asset unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Linked asset name
                        example: "Character Name"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_type_id:
                        type: string
                        format: uuid
                        description: Asset type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset_id)
        return breakdown_service.get_entity_casting(asset_id)


class AssetTasksResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, asset_id):
        """
        Get asset tasks
        ---
        description: Retrieve all tasks related to a specific asset.
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
          - in: query
            name: task_type_id
            type: string
            format: uuid
            description: Filter tasks by task type
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_status_id
            type: string
            format: uuid
            description: Filter tasks by task status
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: List of asset tasks successfully retrieved
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
                        description: Task unique identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      name:
                        type: string
                        description: Task name
                        example: "Modeling Task"
                      task_type_id:
                        type: string
                        format: uuid
                        description: Task type identifier
                        example: f79f1jf9-hj20-9110-f625-02908537h70
                      task_status_id:
                        type: string
                        format: uuid
                        description: Task status identifier
                        example: g80g2kg0-ik31-0221-g736-13019648i81
                      entity_id:
                        type: string
                        format: uuid
                        description: Asset identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      assigned_to:
                        type: string
                        format: uuid
                        description: Assigned user identifier
                        example: h91h3lh1-jl42-1332-h847-24120759j92
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return tasks_service.get_tasks_for_asset(
            asset_id, relations=self.get_relations()
        )


class AssetTaskTypesResource(Resource):

    @jwt_required()
    def get(self, asset_id):
        """
        Get asset task types
        ---
        description: Retrieve all task types that are used for tasks related to a specific asset.
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
        responses:
          200:
            description: List of asset task types successfully retrieved
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
                        description: Task type unique identifier
                        example: f79f1jf9-hj20-9110-f625-02908537h70
                      name:
                        type: string
                        description: Task type name
                        example: "Modeling"
                      short_name:
                        type: string
                        description: Task type short name
                        example: "MOD"
                      color:
                        type: string
                        description: Task type color code
                        example: "#FF5733"
                      for_entity:
                        type: string
                        description: Entity type this task type is for
                        example: "Asset"
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return tasks_service.get_task_types_for_asset(asset_id)


class NewAssetResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, project_id, asset_type_id):
        """
        Create asset
        ---
        description: Create a new asset in a specific project with the given asset type and parameters.
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: path
            name: asset_type_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset type
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - description
                  - data
                  - is_shared
                  - source_id
                properties:
                  name:
                    type: string
                    description: Asset name
                    example: "Character Name"
                  description:
                    type: string
                    description: Asset description
                    example: "Main character"
                  data:
                    type: object
                    description: Asset metadata and custom data
                    example: [{"difficulty": "easy", "atmsophere": "sunny"}]
                  is_shared:
                    type: boolean
                    description: Whether the asset is shared across projects
                    example: false
                  source_id:
                    type: string
                    format: uuid
                    description: Source asset identifier for duplication
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  episode_id:
                    type: string
                    format: uuid
                    description: Episode identifier for episodic assets
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          201:
            description: Asset successfully created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Created asset unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Asset name
                      example: "Character Name"
                    description:
                      type: string
                      description: Asset description
                      example: "Main character"
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    entity_type_id:
                      type: string
                      format: uuid
                      description: Asset type identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        (name, description, data, is_shared, source_id) = self.get_arguments()

        user_service.check_manager_project_access(project_id)
        asset = assets_service.create_asset(
            project_id,
            asset_type_id,
            name,
            description,
            data,
            is_shared,
            source_id,
            created_by=persons_service.get_current_user()["id"],
        )
        return asset, 201

    def get_arguments(self):
        args = self.get_args(
            [
                {
                    "name": "name",
                    "required": True,
                    "help": "The asset name is required.",
                },
                "description",
                ("data", {}, False, dict),
                (
                    "is_shared",
                    False,
                    False,
                    inputs.boolean,
                ),
                "episode_id",
            ]
        )

        return (
            args["name"],
            args.get("description", ""),
            args["data"],
            args["is_shared"],
            args["episode_id"],
        )


class AssetCastingResource(Resource):

    @jwt_required()
    def get(self, asset_id):
        """
        Get asset casting
        ---
        description: Retrieve the casting information for a specific asset showing which shots or sequences use this asset
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
        responses:
          200:
            description: Asset casting information successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    asset_id:
                      type: string
                      format: uuid
                      description: Asset unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    casting:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            description: Casting entry unique identifier
                            example: b35b7fb5-df86-5776-b181-68564193d36
                          entity_id:
                            type: string
                            format: uuid
                            description: Entity identifier (shot/sequence)
                            example: d57d9hd7-fh08-7998-d403-80786315f58
                          entity_name:
                            type: string
                            description: Entity name
                            example: "SH001"
                          entity_type:
                            type: string
                            description: Entity type (shot/sequence)
                            example: "shot"
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset_id)
        return breakdown_service.get_casting(asset_id)

    @jwt_required()
    def put(self, asset_id):
        """
        Update asset casting
        ---
        description: Modify the casting relationships for a specific asset by updating which shots or sequences use this asset.
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                description: Casting data to update
                properties:
                  casting:
                    type: array
                    items:
                      type: object
                      properties:
                        entity_id:
                          type: string
                          format: uuid
                          description: Entity identifier to cast
                          example: d57d9hd7-fh08-7998-d403-80786315f58
                        entity_type:
                          type: string
                          description: Entity type (shot/sequence)
                          example: "shot"
        responses:
          200:
            description: Asset casting successfully updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    asset_id:
                      type: string
                      format: uuid
                      description: Asset unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    casting:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            description: Casting entry unique identifier
                            example: b35b7fb5-df86-5776-b181-68564193d36
                          entity_id:
                            type: string
                            format: uuid
                            description: Entity identifier
                            example: d57d9hd7-fh08-7998-d403-80786315f58
                          entity_name:
                            type: string
                            description: Entity name
                            example: "SH001"
        """
        casting = request.json
        asset = assets_service.get_asset(asset_id)
        user_service.check_manager_project_access(asset["project_id"])
        return breakdown_service.update_casting(asset_id, casting)


class AssetCastInResource(Resource):

    @jwt_required()
    def get(self, asset_id):
        """
        Get shots casting asset
        ---
        description: Retrieve all shots that cast a specific asset in their breakdown.
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
        responses:
          200:
            description: List of shots casting the asset successfully retrieved
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
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      name:
                        type: string
                        description: Shot name
                        example: "SH001"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      sequence_id:
                        type: string
                        format: uuid
                        description: Sequence identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      frame_in:
                        type: integer
                        description: Frame in
                        example: 100
                      frame_out:
                        type: integer
                        description: Frame out
                        example: 200
                      duration:
                        type: integer
                        description: Shot duration in frames
                        example: 100
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        user_service.check_entity_access(asset["id"])
        return breakdown_service.get_cast_in(asset_id)


class AssetShotAssetInstancesResource(Resource):

    @jwt_required()
    def get(self, asset_id):
        """
        Get shot asset instances
        ---
        description: Retrieve all shot asset instances that are linked to a specific asset.
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
        responses:
          200:
            description: List of shot asset instances successfully retrieved.
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
                        description: Asset instance unique identifier
                        example: f79f1jf9-hj20-9110-f625-02908537h70
                      asset_id:
                        type: string
                        format: uuid
                        description: Asset identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      shot_id:
                        type: string
                        format: uuid
                        description: Shot identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      number:
                        type: string
                        description: Instance number
                        example: "001"
                      description:
                        type: string
                        description: Instance description
                        example: "Main character instance"
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_shot_asset_instances_for_asset(asset_id)


class AssetSceneAssetInstancesResource(Resource):
    @jwt_required()
    def get(self, asset_id):
        """
        Get scene asset instances
        ---
        description: Retrieve all scene asset instances that are linked to a specific asset.
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
        responses:
          200:
            description: List of scene asset instances successfully retrieved.
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
                        description: Asset instance unique identifier
                        example: f79f1jf9-hj20-9110-f625-02908537h70
                      asset_id:
                        type: string
                        format: uuid
                        description: Asset identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      scene_id:
                        type: string
                        format: uuid
                        description: Scene identifier
                        example: g80g2kg0-ik31-0221-g736-13019648i81
                      number:
                        type: string
                        description: Instance number
                        example: "001"
                      description:
                        type: string
                        description: Instance description
                        example: "Main character instance"
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_scene_asset_instances_for_asset(asset_id)


class AssetAssetInstancesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, asset_id):
        """
        Get asset instances
        ---
        description: Retrieve all asset instances that are instantiated inside a specific asset.
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset
        responses:
          200:
            description: List of asset instances successfully retrieved
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
                        description: Asset instance unique identifier
                        example: f79f1jf9-hj20-9110-f625-02908537h70
                      asset_id:
                        type: string
                        format: uuid
                        description: Parent asset identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      target_asset_id:
                        type: string
                        format: uuid
                        description: Target asset identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      number:
                        type: string
                        description: Instance number
                        example: "001"
                      description:
                        type: string
                        description: Instance description
                        example: "Main character instance"
        """
        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        return breakdown_service.get_asset_instances_for_asset(asset_id)

    @jwt_required()
    def post(self, asset_id):
        """
        Create asset instance
        ---
        description: Create a new asset instance inside a specific asset by instantiating another asset.
        tags:
          - Assets
        parameters:
          - in: path
            name: asset_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the parent asset
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - asset_to_instantiate_id
                properties:
                  asset_to_instantiate_id:
                    type: string
                    format: uuid
                    description: Unique identifier of the asset to instantiate
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  description:
                    type: string
                    description: Description for the asset instance
                    example: "Asset instance description"
        responses:
          201:
            description: Asset instance successfully created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Created asset instance unique identifier
                      example: f79f1jf9-hj20-9110-f625-02908537h70
                    asset_id:
                      type: string
                      format: uuid
                      description: Parent asset identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    target_asset_id:
                      type: string
                      format: uuid
                      description: Target asset identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    number:
                      type: string
                      description: Instance number
                      example: "001"
                    description:
                      type: string
                      description: Instance description
                      example: "Main character instance"
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
        """
        args = self.get_args(
            [
                ("asset_to_instantiate_id", None, True),
                ("description", None, False),
            ]
        )

        asset = assets_service.get_asset(asset_id)
        user_service.check_project_access(asset["project_id"])
        asset_instance = breakdown_service.add_asset_instance_to_asset(
            asset_id, args["asset_to_instantiate_id"], args["description"]
        )
        return asset_instance, 201


class BaseSetSharedAssetsResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, project_id=None, asset_type_id=None, asset_ids=None):
        args = self.get_args(
            [
                (
                    "is_shared",
                    True,
                    False,
                    inputs.boolean,
                ),
            ]
        )
        return assets_service.set_shared_assets(
            is_shared=args["is_shared"],
            project_id=project_id,
            asset_type_id=asset_type_id,
            asset_ids=asset_ids,
        )


class SetSharedProjectAssetsResource(BaseSetSharedAssetsResource):

    @jwt_required()
    def post(self, project_id):
        """
        Set project assets shared
        ---
        description: Share or unshare all assets for a specific project or a list of specific assets.
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
        requestBody:
          required: false
          content:
            application/json:
              schema:
                type: object
                properties:
                  is_shared:
                    type: boolean
                    description: Whether to share or unshare the assets
                    example: true
                  asset_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
                    description: Specific asset IDs to update.
                    example: ["a24a6ea4-ce75-4665-a070-57453082c25", "b35b7fb5-df86-5776-b181-68564193d36"]
        responses:
          200:
            description: Assets shared status successfully updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    updated_count:
                      type: integer
                      description: Number of assets updated
                      example: 5
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
        """
        args = self.get_args(
            [
                (
                    "asset_ids",
                    None,
                    False,
                    str,
                    "append",
                ),
            ]
        )
        user_service.check_manager_project_access(project_id)
        return super().post(project_id=project_id, asset_ids=args["asset_ids"])


class SetSharedProjectAssetTypeAssetsResource(BaseSetSharedAssetsResource):

    @jwt_required()
    def post(self, project_id, asset_type_id):
        """
        Set asset type assets shared
        ---
        description: Share or unshare all assets for a specific project and asset type.
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: path
            name: asset_type_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the asset type
        requestBody:
          required: false
          content:
            application/json:
              schema:
                type: object
                properties:
                  is_shared:
                    type: boolean
                    description: Whether to share or unshare the assets
                    example: true
        responses:
          200:
            description: Asset type assets shared status successfully updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    updated_count:
                      type: integer
                      description: Number of assets updated
                      example: 3
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    asset_type_id:
                      type: string
                      format: uuid
                      description: Asset type identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        user_service.check_manager_project_access(project_id)
        return super().post(project_id=project_id, asset_type_id=asset_type_id)


class SetSharedAssetsResource(BaseSetSharedAssetsResource):

    @jwt_required()
    def post(self):
        """
        Set assets shared
        ---
        description: Share or unshare a specific list of assets by their IDs.
        tags:
          - Assets
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - asset_ids
                properties:
                  asset_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
                    description: List of asset IDs to update
                    example: ["a24a6ea4-ce75-4665-a070-57453082c25", "b35b7fb5-df86-5776-b181-68564193d36"]
                  is_shared:
                    type: boolean
                    description: Whether to share or unshare the assets
                    example: true
        responses:
          200:
            description: Assets shared status successfully updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    updated_count:
                      type: integer
                      description: Number of assets updated
                      example: 2
                    asset_ids:
                      type: array
                      items:
                        type: string
                        format: uuid
                      description: List of updated asset IDs
                      example: ["a24a6ea4-ce75-4665-a070-57453082c25", "b35b7fb5-df86-5776-b181-68564193d36"]
        """
        args = self.get_args(
            [
                (
                    "asset_ids",
                    [],
                    True,
                    str,
                    "append",
                ),
            ]
        )
        asset_ids = args["asset_ids"]
        project_ids = set()
        for asset_id in asset_ids:
            project_ids.add(assets_service.get_asset(asset_id)["project_id"])
        for project_id in project_ids:
            user_service.check_manager_project_access(project_id)
        return super().post(asset_ids=asset_ids)


class ProjectAssetsSharedUsedResource(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Get shared assets used in project
        ---
        description: Retrieve all shared assets that are used in a specific project.
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
        responses:
          200:
            description: List of shared assets used in project successfully retrieved
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
                        example: "Character Name"
                      project_id:
                        type: string
                        format: uuid
                        description: Original project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_type_id:
                        type: string
                        format: uuid
                        description: Asset type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      is_shared:
                        type: boolean
                        description: Whether the asset is shared
                        example: true
        """
        user_service.check_project_access(project_id)
        return assets_service.get_shared_assets_used_in_project(project_id)


class ProjectEpisodeAssetsSharedUsedResource(Resource):

    @jwt_required()
    def get(self, project_id, episode_id):
        """
        Get shared assets used in episode
        ---
        description: Retrieve all shared assets that are used in a specific project episode.
        tags:
          - Assets
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: path
            name: episode_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the episode
        responses:
          200:
            description: List of shared assets used in episode successfully retrieved
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
                        example: "Character Name"
                      project_id:
                        type: string
                        format: uuid
                        description: Original project identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      entity_type_id:
                        type: string
                        format: uuid
                        description: Asset type identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      is_shared:
                        type: boolean
                        description: Whether the asset is shared
                        example: true
                      episode_id:
                        type: string
                        format: uuid
                        description: Episode identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
        """
        user_service.check_project_access(project_id)
        return assets_service.get_shared_assets_used_in_project(
            project_id, episode_id
        )
