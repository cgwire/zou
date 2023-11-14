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
        parameters:
          - in: formData
            name: query
            required: True
            type: string
            x-example: test will search for test
          - in: formData
            name: limit
            required: False
            type: integer
            default: 3
            x-example: 3
          - in: formData
            name: index_names
            required: False
            type: list of strings
            default: ["assets", "shots", "persons"]
            x-example: ["assets"]
        responses:
            200:
                description: List of entities that contain the query
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
            results["assets"] = index_service.search_assets(
                query, project_ids, limit=limit, offset=offset
            )
        if "shots" in index_names:
            results["shots"] = index_service.search_shots(
                query, project_ids, limit=limit, offset=offset
            )

        return results
