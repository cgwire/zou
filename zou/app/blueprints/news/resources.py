from flasgger import swag_from
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.services import (
    news_service,
    projects_service,
    permissions_service,
    user_service,
    persons_service,
)
from zou.app.exceptions import NewsNotFoundException
from zou.app.utils import fields, permissions


class NewsMixin(ArgsMixin):

    def get_news(self, project_ids=None):
        (
            only_preview,
            task_type_id,
            task_status_id,
            episode_id,
            person_id,
            page,
            limit,
            after,
            before,
        ) = self.get_arguments()

        current_user = persons_service.get_current_user_raw()

        after = self.parse_date_parameter(after)
        before = self.parse_date_parameter(before)
        filters = news_service.NewsFilters(
            project_ids=project_ids,
            only_preview=only_preview,
            task_type_id=task_type_id,
            task_status_id=task_status_id,
            episode_id=episode_id,
            author_id=person_id,
            after=after,
            before=before,
            current_user=current_user,
        )
        result = news_service.get_last_news_for_project(
            filters, page=page, limit=limit
        )
        stats = news_service.get_news_stats_for_project(filters)
        result["stats"] = stats
        return result

    def get_arguments(self):
        args = self.get_args(
            [
                (
                    "only_preview",
                    False,
                    False,
                    fields.boolean,
                ),
                "task_type_id",
                "task_status_id",
                "person_id",
                "project_id",
                "episode_id",
                {"name": "page", "default": 1, "type": int},
                {"name": "limit", "default": 50, "type": int},
                "after",
                "before",
            ],
        )
        return (
            args["only_preview"],
            args["task_type_id"],
            args["task_status_id"],
            args["episode_id"],
            args["person_id"],
            args["page"],
            args["limit"],
            args["after"],
            args["before"],
        )


class ProjectNewsResource(MethodView, NewsMixin, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProjectNewsResource_get.yml")
    def get(self, project_id):
        """
        Get project latest news
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        return self.get_news([project_id])


class NewsResource(MethodView, NewsMixin, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/NewsResource_get.yml")
    def get(self):
        """
        Get open projects news
        """
        open_project_ids = []
        if permissions.has_admin_permissions():
            open_project_ids = projects_service.open_project_ids()
        else:
            open_project_ids = user_service.get_open_project_ids()

        project_id = self.get_text_parameter("project_id")
        if project_id is not None and project_id in open_project_ids:
            open_project_ids = [project_id]

        return self.get_news(project_ids=open_project_ids)


class ProjectSingleNewsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProjectSingleNewsResource_get.yml")
    def get(self, project_id, news_id):
        """
        Get news item
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
        news = news_service.get_news(project_id, news_id)
        if len(news["data"]) > 0:
            return news["data"][0]
        else:
            raise NewsNotFoundException
