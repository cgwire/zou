from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions
from zou.app.services import (
    index_service,
    projects_service,
    user_service
)


class SearchResource(Resource, ArgsMixin):

    @jwt_required
    def post(self):
        args = self.get_args([("query", "", True)])
        query = args.get("query")
        if len(query) < 3:
            return {
                "assets": []
            }

        if permissions.has_admin_permissions():
            projects = projects_service.open_projects()
        else:
            projects = user_service.get_open_projects()
        open_project_ids = [project["id"] for project in projects]

        return {
            "assets": index_service.search_assets(query, open_project_ids)
        }
