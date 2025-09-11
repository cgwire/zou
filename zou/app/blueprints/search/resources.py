from flask_restful import Resource

from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions
from zou.app.services import index_service, projects_service, user_service


class SearchResource(Resource, ArgsMixin):
    @jwt_required()
    def post(self):
        """
        Search for resource
        ---
        tags:
        - Search
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - query
                properties:
                  query:
                    type: string
                    example: test will search for test
                    description: Search query string (minimum 3 characters)
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                    description: Filter search results by project ID
                  limit:
                    type: integer
                    default: 3
                    example: 3
                    description: Maximum number of results per index
                  offset:
                    type: integer
                    default: 0
                    example: 0
                    description: Number of results to skip
                  index_names:
                    type: array
                    items:
                      type: string
                      enum: ["assets", "shots", "persons"]
                    default: ["assets", "shots", "persons"]
                    example: ["assets"]
                    description: List of index names to search in
        responses:
            200:
              description: List of entities that contain the query
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      persons:
                        type: array
                        items:
                          type: object
                        description: List of matching persons
                      assets:
                        type: array
                        items:
                          type: object
                        description: List of matching assets
                      shots:
                        type: array
                        items:
                          type: object
                        description: List of matching shots
            400:
              description: Bad request
            403:
              description: Insufficient permissions
        """
        args = self.get_args(
            [
                ("query", "", True),
                ("project_id", None, False),
                ("limit", 3, False, int),
                ("offset", 0, False, int),
                (
                    "index_names",
                    ["assets", "shots", "persons"],
                    False,
                    str,
                    "append",
                ),
            ]
        )
        query = args["query"]
        limit = args["limit"]
        offset = args["offset"]
        project_id = args["project_id"]
        index_names = args["index_names"]
        results = {}
        if len(query) < 3:
            return results

        if permissions.has_admin_permissions():
            projects = projects_service.open_projects()
        else:
            projects = user_service.get_open_projects()
        project_ids = [project["id"] for project in projects]

        if project_id is not None and len(project_id) > 0:
            if project_id in project_ids:
                project_ids = [project_id]
            else:
                project_ids = []

        if "persons" in index_names:
            results["persons"] = index_service.search_persons(
                query, limit=limit, offset=offset
            )
        if "assets" in index_names:
            if (
                len(project_ids) == 0
                and not permissions.has_admin_permissions()
            ):
                results["assets"] = []
            else:
                results["assets"] = index_service.search_assets(
                    query, project_ids, limit=limit, offset=offset
                )
        if "shots" in index_names:
            if (
                len(project_ids) == 0
                and not permissions.has_admin_permissions()
            ):
                results["shots"] = []
            else:
                results["shots"] = index_service.search_shots(
                    query, project_ids, limit=limit, offset=offset
                )

        return results
