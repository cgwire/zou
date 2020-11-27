from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.services import news_service, projects_service, user_service
from zou.app.services.exception import NewsNotFoundException


class ProjectNewsResource(Resource, ArgsMixin):
    @jwt_required
    def get(self, project_id):
        (
            only_preview,
            task_type_id,
            task_status_id,
            person_id,
            page,
            page_size,
            after,
            before
        ) = self.get_arguments()
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        after = self.parse_date_parameter(after)
        before = self.parse_date_parameter(before)
        result = news_service.get_last_news_for_project(
            project_id,
            only_preview=only_preview,
            task_type_id=task_type_id,
            task_status_id=task_status_id,
            author_id=person_id,
            page=page,
            page_size=page_size,
            after=after,
            before=before,
        )
        stats = news_service.get_news_stats_for_project(
            project_id,
            task_type_id=task_type_id,
            task_status_id=task_status_id,
            author_id=person_id,
            after=after,
            before=before,
        )
        result["stats"] = stats
        return result


    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument("only_preview", default=False, type=bool)
        parser.add_argument("task_type_id", default=None)
        parser.add_argument("task_status_id", default=None)
        parser.add_argument("person_id", default=None)
        parser.add_argument("page", default=1, type=int)
        parser.add_argument("page_size", default=50, type=int)
        parser.add_argument("after", default=None)
        parser.add_argument("before", default=None)
        args = parser.parse_args()

        return (
            args["only_preview"],
            args["task_type_id"],
            args["task_status_id"],
            args["person_id"],
            args["page"],
            args["page_size"],
            args["after"],
            args["before"],
        )


class ProjectSingleNewsResource(Resource):
    @jwt_required
    def get(self, project_id, news_id):
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        news = news_service.get_news(project_id, news_id)
        if len(news["data"]) > 0:
            return news["data"][0]
        else:
            raise NewsNotFoundException
