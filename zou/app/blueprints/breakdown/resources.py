from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.services import (
    assets_service,
    breakdown_service,
    entities_service,
    projects_service,
    shots_service,
    user_service,
)

from zou.app.mixin import ArgsMixin


class CastingResource(Resource):
    @jwt_required()
    def get(self, project_id, entity_id):
        """
        Get entity casting
        ---
        description: Retrieve the casting information for a specific entity showing which assets are linked to it.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: path
            name: entity_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the entity
        responses:
          200:
            description: Entity casting information successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    entity_id:
                      type: string
                      format: uuid
                      description: Entity unique identifier
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
                          asset_id:
                            type: string
                            format: uuid
                            description: Asset identifier
                            example: c46c8gc6-eg97-6887-c292-79675204e47
                          asset_name:
                            type: string
                            description: Asset name
                            example: "Main Character"
        """
        user_service.check_project_access(project_id)
        return breakdown_service.get_casting(entity_id)

    @jwt_required()
    def put(self, project_id, entity_id):
        """
        Update entity casting
        ---
        description: Modify the casting relationships for a specific entity by updating which assets are linked to it.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: path
            name: entity_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the entity
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
                        asset_id:
                          type: string
                          format: uuid
                          description: Asset identifier to link
                          example: c46c8gc6-eg97-6887-c292-79675204e47
                        asset_name:
                          type: string
                          description: Asset name
                          example: "Main Character"
        responses:
          200:
            description: Entity casting successfully updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    entity_id:
                      type: string
                      format: uuid
                      description: Entity unique identifier
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
                          asset_id:
                            type: string
                            format: uuid
                            description: Asset identifier
                            example: c46c8gc6-eg97-6887-c292-79675204e47
                          asset_name:
                            type: string
                            description: Asset name
                            example: "Main Character"
        """
        casting = request.json
        user_service.check_manager_project_access(project_id)
        return breakdown_service.update_casting(entity_id, casting)


class EpisodesCastingResource(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Get episodes casting
        ---
        description: Retrieve the casting information for all episodes in a specific project.
        tags:
          - Breakdown
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
            description: Episodes casting information successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      episode_id:
                        type: string
                        format: uuid
                        description: Episode unique identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      episode_name:
                        type: string
                        description: Episode name
                        example: "Episode 01"
                      casting:
                        type: array
                        items:
                          type: object
                          properties:
                            asset_id:
                              type: string
                              format: uuid
                              description: Asset identifier
                              example: c46c8gc6-eg97-6887-c292-79675204e47
                            asset_name:
                              type: string
                              description: Asset name
                              example: "Main Character"
        """
        user_service.check_project_access(project_id)
        return breakdown_service.get_production_episodes_casting(project_id)


class EpisodeSequenceAllCastingResource(Resource):
    @jwt_required()
    def get(self, project_id, episode_id):
        """
        Get episode shots casting
        ---
        description: Retrieve the casting information for all shots from a specific episode.
        tags:
          - Breakdown
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
            example: d57d9hd7-fh08-7998-d403-80786315f58
            description: Unique identifier of the episode
        responses:
          200:
            description: Episode shots casting information successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      shot_id:
                        type: string
                        format: uuid
                        description: Shot unique identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      shot_name:
                        type: string
                        description: Shot name
                        example: "SH001"
                      casting:
                        type: array
                        items:
                          type: object
                          properties:
                            asset_id:
                              type: string
                              format: uuid
                              description: Asset identifier
                              example: c46c8gc6-eg97-6887-c292-79675204e47
                            asset_name:
                              type: string
                              description: Asset name
                              example: "Main Character"
        """
        user_service.check_project_access(project_id)
        return breakdown_service.get_all_sequences_casting(
            project_id, episode_id=episode_id
        )


class SequenceAllCastingResource(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Get project shots casting
        ---
        description: Retrieve the casting information for all shots from all sequences in a specific project.
        tags:
          - Breakdown
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
            description: Project shots casting information successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      shot_id:
                        type: string
                        format: uuid
                        description: Shot unique identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      shot_name:
                        type: string
                        description: Shot name
                        example: "SH001"
                      sequence_id:
                        type: string
                        format: uuid
                        description: Sequence identifier
                        example: f79f1jf9-hj20-9110-f625-02908537h70
                      sequence_name:
                        type: string
                        description: Sequence name
                        example: "SEQ01"
                      casting:
                        type: array
                        items:
                          type: object
                          properties:
                            asset_id:
                              type: string
                              format: uuid
                              description: Asset identifier
                              example: c46c8gc6-eg97-6887-c292-79675204e47
                            asset_name:
                              type: string
                              description: Asset name
                              example: "Main Character"
        """
        user_service.check_project_access(project_id)
        return breakdown_service.get_all_sequences_casting(project_id)


class SequenceCastingResource(Resource):
    @jwt_required()
    def get(self, project_id, sequence_id):
        """
        Get sequence shots casting
        ---
        description: Retrieve the casting information for all shots from a specific sequence.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: path
            name: sequence_id
            required: true
            type: string
            format: uuid
            example: f79f1jf9-hj20-9110-f625-02908537h70
            description: Unique identifier of the sequence
        responses:
          200:
            description: Sequence shots casting information successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      shot_id:
                        type: string
                        format: uuid
                        description: Shot unique identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      shot_name:
                        type: string
                        description: Shot name
                        example: "SH001"
                      sequence_id:
                        type: string
                        format: uuid
                        description: Sequence identifier
                        example: f79f1jf9-hj20-9110-f625-02908537h70
                      casting:
                        type: array
                        items:
                          type: object
                          properties:
                            asset_id:
                              type: string
                              format: uuid
                              description: Asset identifier
                              example: c46c8gc6-eg97-6887-c292-79675204e47
                            asset_name:
                              type: string
                              description: Asset name
                              example: "Main Character"
        """
        user_service.check_project_access(project_id)
        shots_service.get_sequence(sequence_id)
        return breakdown_service.get_sequence_casting(sequence_id)


class AssetTypeCastingResource(Resource):
    @jwt_required()
    def get(self, project_id, asset_type_id):
        """
        Get asset type casting
        ---
        description: Retrieve the casting information for all assets of a specific asset type in a project.
        tags:
          - Breakdown
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
            example: g80g2kg0-ik31-0221-g736-13019648i81
            description: Unique identifier of the asset type
        responses:
          200:
            description: Asset type casting information successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      asset_id:
                        type: string
                        format: uuid
                        description: Asset unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      asset_name:
                        type: string
                        description: Asset name
                        example: "Main Character"
                      asset_type_id:
                        type: string
                        format: uuid
                        description: Asset type identifier
                        example: g80g2kg0-ik31-0221-g736-13019648i81
                      casting:
                        type: array
                        items:
                          type: object
                          properties:
                            entity_id:
                              type: string
                              format: uuid
                              description: Entity identifier
                              example: e68e0ie8-gi19-8009-e514-91897426g69
                            entity_name:
                              type: string
                              description: Entity name
                              example: "SH001"
                            entity_type:
                              type: string
                              description: Entity type (shot/sequence)
                              example: "shot"
        """
        user_service.check_project_access(project_id)
        assets_service.get_asset_type(asset_type_id)
        return breakdown_service.get_asset_type_casting(
            project_id, asset_type_id
        )


class ShotAssetInstancesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, shot_id):
        """
        Get shot asset instances
        ---
        description: Retrieve all asset instances that are linked to a specific shot.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: shot_id
            required: true
            type: string
            format: uuid
            example: e68e0ie8-gi19-8009-e514-91897426g69
            description: Unique identifier of the shot
        responses:
          200:
            description: Shot asset instances successfully retrieved
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
                        example: h91h3lh1-jl42-1332-h847-24120759j92
                      asset_id:
                        type: string
                        format: uuid
                        description: Asset identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      shot_id:
                        type: string
                        format: uuid
                        description: Shot identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      number:
                        type: string
                        description: Instance number
                        example: "001"
                      description:
                        type: string
                        description: Instance description
                        example: "Main character instance"
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        return breakdown_service.get_asset_instances_for_shot(shot_id)

    @jwt_required()
    def post(self, shot_id):
        """
        Add shot asset instance
        ---
        description: Add an asset instance to a specific shot.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: shot_id
            required: true
            type: string
            format: uuid
            example: e68e0ie8-gi19-8009-e514-91897426g69
            description: Unique identifier of the shot
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - asset_instance_id
                properties:
                  asset_instance_id:
                    type: string
                    format: uuid
                    description: Asset instance identifier to add
                    example: h91h3lh1-jl42-1332-h847-24120759j92
        responses:
          201:
            description: Asset instance successfully added to shot
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Shot unique identifier
                      example: e68e0ie8-gi19-8009-e514-91897426g69
                    name:
                      type: string
                      description: Shot name
                      example: "SH001"
                    asset_instances:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            description: Asset instance unique identifier
                            example: h91h3lh1-jl42-1332-h847-24120759j92
                          asset_id:
                            type: string
                            format: uuid
                            description: Asset identifier
                            example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        args = self.get_args([("asset_instance_id", None, True)])

        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        shot = breakdown_service.add_asset_instance_to_shot(
            shot_id, args["asset_instance_id"]
        )
        return shot, 201


class RemoveShotAssetInstanceResource(Resource, ArgsMixin):
    @jwt_required()
    def delete(self, shot_id, asset_instance_id):
        """
        Remove shot asset instance
        ---
        description: Remove an asset instance from a specific shot.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: shot_id
            required: true
            type: string
            format: uuid
            example: e68e0ie8-gi19-8009-e514-91897426g69
            description: Unique identifier of the shot
          - in: path
            name: asset_instance_id
            required: true
            type: string
            format: uuid
            example: h91h3lh1-jl42-1332-h847-24120759j92
            description: Unique identifier of the asset instance
        responses:
          204:
            description: Asset instance successfully removed from shot
        """
        shot = shots_service.get_shot(shot_id)
        user_service.check_project_access(shot["project_id"])
        shot = breakdown_service.remove_asset_instance_for_shot(
            shot_id, asset_instance_id
        )
        return "", 204


class SceneAssetInstancesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, scene_id):
        """
        Get scene asset instances
        ---
        description: Retrieve all asset instances that are linked to a specific scene.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: scene_id
            required: true
            type: string
            format: uuid
            example: i02i4mi2-km53-2443-i958-35231870k03
            description: Unique identifier of the scene
        responses:
          200:
            description: Scene asset instances successfully retrieved
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
                        example: j13j5nj3-ln64-3554-j069-46342981l14
                      asset_id:
                        type: string
                        format: uuid
                        description: Asset identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      scene_id:
                        type: string
                        format: uuid
                        description: Scene identifier
                        example: i02i4mi2-km53-2443-i958-35231870k03
                      number:
                        type: string
                        description: Instance number
                        example: "001"
                      description:
                        type: string
                        description: Instance description
                        example: "Main character instance"
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        return breakdown_service.get_asset_instances_for_scene(scene_id)

    @jwt_required()
    def post(self, scene_id):
        """
        Create scene asset instance
        ---
        description: Create an asset instance on a specific scene.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: scene_id
            required: true
            type: string
            format: uuid
            example: i02i4mi2-km53-2443-i958-35231870k03
            description: Unique identifier of the scene
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - asset_id
                properties:
                  asset_id:
                    type: string
                    format: uuid
                    description: Asset identifier to create instance from
                    example: c46c8gc6-eg97-6887-c292-79675204e47
                  description:
                    type: string
                    description: Instance description
                    example: "Main character instance"
        responses:
          201:
            description: Asset instance successfully created on scene
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Asset instance unique identifier
                      example: j13j5nj3-ln64-3554-j069-46342981l14
                    asset_id:
                      type: string
                      format: uuid
                      description: Asset identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    scene_id:
                      type: string
                      format: uuid
                      description: Scene identifier
                      example: i02i4mi2-km53-2443-i958-35231870k03
                    number:
                      type: string
                      description: Instance number
                      example: "001"
                    description:
                      type: string
                      description: Instance description
                      example: "Main character instance"
        """
        args = self.get_args(
            [("asset_id", None, True), ("description", None, False)]
        )

        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        asset_instance = breakdown_service.add_asset_instance_to_scene(
            scene_id, args["asset_id"], args["description"]
        )
        return asset_instance, 201


class SceneCameraInstancesResource(Resource):
    @jwt_required()
    def get(self, scene_id):
        """
        Get scene camera instances
        ---
        description: Retrieve all camera instances that are linked to a specific scene.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: scene_id
            required: true
            type: string
            format: uuid
            example: i02i4mi2-km53-2443-i958-35231870k03
            description: Unique identifier of the scene
        responses:
          200:
            description: Scene camera instances successfully retrieved
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
                        description: Camera instance unique identifier
                        example: k24k6ok4-mo75-4665-k180-57453082m25
                      camera_id:
                        type: string
                        format: uuid
                        description: Camera identifier
                        example: l35l7pl5-np86-5776-l291-68564193n36
                      scene_id:
                        type: string
                        format: uuid
                        description: Scene identifier
                        example: i02i4mi2-km53-2443-i958-35231870k03
                      number:
                        type: string
                        description: Instance number
                        example: "001"
                      description:
                        type: string
                        description: Instance description
                        example: "Main camera instance"
        """
        scene = shots_service.get_scene(scene_id)
        user_service.check_project_access(scene["project_id"])
        return breakdown_service.get_camera_instances_for_scene(scene_id)


class ProjectEntityLinksResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, project_id):
        """
        Get project entity links
        ---
        description: Retrieve all entity links related to a specific project. Results can be paginated using page and limit query parameters. If you prefer a more accurate pagination, you can use cursor_created_at to get the next page. It's mainly used for synchronisation purpose.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: query
            name: page
            required: false
            type: integer
            example: 2
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            type: integer
            example: 100
            description: Number of items per page
          - in: query
            name: cursor_created_at
            required: false
            type: string
            format: date-time
            example: "2020-01-01T00:00:00"
            description: Cursor for pagination based on creation date
        responses:
          200:
            description: Project entity links successfully retrieved
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
                        description: Entity link unique identifier
                        example: m46m8qm6-oq97-6887-m403-80786315o47
                      entity_in_id:
                        type: string
                        format: uuid
                        description: Source entity identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      entity_out_id:
                        type: string
                        format: uuid
                        description: Target entity identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2020-01-01T00:00:00"
        """
        user_service.check_manager_project_access(project_id)
        projects_service.get_project(project_id)
        page = self.get_page()
        limit = self.get_limit()
        cursor_created_at = self.get_text_parameter("cursor_created_at")
        return entities_service.get_entity_links_for_project(
            project_id,
            page=page,
            limit=limit,
            cursor_created_at=cursor_created_at,
        )


class ProjectEntityLinkResource(Resource):
    @jwt_required()
    def delete(self, project_id, entity_link_id):
        """
        Delete entity link
        ---
        description: Delete a specific entity link. It's mainly used for synchronisation purpose.
        tags:
          - Breakdown
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
          - in: path
            name: entity_link_id
            required: true
            type: string
            format: uuid
            example: m46m8qm6-oq97-6887-m403-80786315o47
            description: Unique identifier of the entity link
        responses:
          200:
            description: Entity link successfully deleted
        """
        user_service.check_manager_project_access(project_id)
        return entities_service.remove_entity_link(entity_link_id)
