from flask_jwt_extended import jwt_required

from zou.app.models.playlist import Playlist
from zou.app.services import user_service, playlists_service

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.utils import fields


class PlaylistsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Playlist)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    def get(self):
        """
        Get playlists
        ---
        tags:
          - Crud
        description: Retrieve all playlists. Supports filtering via query
          parameters and pagination.
        parameters:
          - in: query
            name: page
            required: false
            schema:
              type: integer
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
            example: 50
            description: Number of results per page
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Whether to include relations
        responses:
            200:
              description: Playlists retrieved successfully
              content:
                application/json:
                  schema:
                    oneOf:
                      - type: array
                        items:
                          type: object
                      - type: object
                        properties:
                          data:
                            type: array
                            items:
                              type: object
                            example: []
                          total:
                            type: integer
                            example: 100
                          nb_pages:
                            type: integer
                            example: 2
                          limit:
                            type: integer
                            example: 50
                          offset:
                            type: integer
                            example: 0
                          page:
                            type: integer
                            example: 1
            400:
              description: Invalid filter format or query error
        """
        return super().get()

    @jwt_required()
    def post(self):
        """
        Create playlist
        ---
        tags:
          - Crud
        description: Create a new playlist with data provided in the
          request body. JSON format is expected. Requires supervisor
          access to the project.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - project_id
                properties:
                  name:
                    type: string
                    example: Playlist Name
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  episode_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id:
                    type: string
                    format: uuid
                    example: c24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Playlist created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Playlist Name
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      episode_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      task_type_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().post()

    def check_create_permissions(self, playlist):
        user_service.check_supervisor_project_access(playlist["project_id"])

    def update_data(self, data):
        data = super().update_data(data)
        if "episode_id" in data and data["episode_id"] in ["all", "main"]:
            data["episode_id"] = None
        if "task_type_id" in data and not fields.is_valid_id(
            data["task_type_id"]
        ):
            data["task_type_id"] = None
        return data


class PlaylistResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Playlist)

    def check_read_permissions(self, playlist):
        user_service.check_project_access(playlist["project_id"])
        user_service.block_access_to_vendor()

    @jwt_required()
    def get(self, instance_id):
        """
        Get playlist
        ---
        tags:
          - Crud
        description: Retrieve a playlist by its ID and return it as a JSON
          object. Supports including relations. Requires project access.
          Vendor access is blocked.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Playlist retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Playlist Name
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      episode_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      task_type_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      shots:
                        type: array
                        items:
                          type: object
                        example: []
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        return super().get(instance_id)

    @jwt_required()
    def put(self, instance_id):
        """
        Update playlist
        ---
        tags:
          - Crud
        description: Update a playlist with data provided in the request
          body. JSON format is expected. Requires project access. Vendor
          access is blocked.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    example: Updated Playlist Name
                  shots:
                    type: array
                    items:
                      type: object
                      properties:
                        entity_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        preview_file_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                    example: []
        responses:
            200:
              description: Playlist updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Updated Playlist Name
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      shots:
                        type: array
                        items:
                          type: object
                        example: []
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().put(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete playlist
        ---
        tags:
          - Crud
        description: Delete a playlist by its ID. Returns empty response
          on success.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Playlist deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        playlists_service.remove_playlist(instance_id)
        return "", 204

    def check_update_permissions(self, playlist, data):
        user_service.check_project_access(playlist["project_id"])
        user_service.block_access_to_vendor()

    def pre_update(self, instance_dict, data):
        if "shots" in data:
            shots = [
                {
                    "entity_id": shot.get("entity_id", shot.get("id", "")),
                    "preview_file_id": shot["preview_file_id"],
                }
                for shot in data["shots"]
                if "preview_file_id" in shot
            ]
            data["shots"] = shots
        return data
