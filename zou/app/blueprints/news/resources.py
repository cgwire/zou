from flask_restful import Resource, inputs
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.services import (
    news_service,
    projects_service,
    user_service,
    persons_service,
)
from zou.app.services.exception import NewsNotFoundException
from zou.app.utils import permissions


class NewsMixin(ArgsMixin):

    def get_news(self, project_ids=[]):
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
        result = news_service.get_last_news_for_project(
            project_ids=project_ids,
            only_preview=only_preview,
            task_type_id=task_type_id,
            task_status_id=task_status_id,
            episode_id=episode_id,
            author_id=person_id,
            page=page,
            limit=limit,
            after=after,
            before=before,
            current_user=current_user,
        )
        stats = news_service.get_news_stats_for_project(
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
        result["stats"] = stats
        return result

    def get_arguments(self):
        args = self.get_args(
            [
                (
                    "only_preview",
                    False,
                    False,
                    inputs.boolean,
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


class ProjectNewsResource(Resource, NewsMixin, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all news related to a given project
        ---
        tags:
          - News
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: before
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
          - in: query
            name: after
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
          - in: query
            name: page
            required: false
            schema:
              type: integer
              default: 1
            example: 1
          - in: query
            name: limit
            required: false
            schema:
              type: integer
              default: 50
            example: 50
          - in: query
            name: person_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_status_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: only_preview
            required: false
            schema:
              type: boolean
              default: false
            example: false
        responses:
          '200':
            description: All news related to given project
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    data:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                          title:
                            type: string
                          content:
                            type: string
                          created_at:
                            type: string
                            format: date-time
                          author_id:
                            type: string
                            format: uuid
                    stats:
                      type: object
                      properties:
                        total:
                          type: integer
          '404':
            description: Project not found
        """
        return self.get_news([project_id])


class NewsResource(Resource, NewsMixin, ArgsMixin):

    @jwt_required()
    def get(self):
        """
        Retrieve all news from user's open projects
        ---
        tags:
          - News
        parameters:
          - in: query
            name: project_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: before
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
          - in: query
            name: after
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
          - in: query
            name: page
            required: false
            schema:
              type: integer
              default: 1
            example: 1
          - in: query
            name: limit
            required: false
            schema:
              type: integer
              default: 50
            example: 50
          - in: query
            name: person_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_status_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: only_preview
            required: false
            schema:
              type: boolean
              default: false
            example: false
        responses:
          '200':
            description: All news from user's open projects
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    data:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                          title:
                            type: string
                          content:
                            type: string
                          created_at:
                            type: string
                            format: date-time
                          author_id:
                            type: string
                            format: uuid
                          project_id:
                            type: string
                            format: uuid
                    stats:
                      type: object
                      properties:
                        total:
                          type: integer
        """
        open_project_ids = []
        if permissions.has_admin_permissions():
            open_project_ids = projects_service.open_project_ids()
        else:
            open_project_ids = user_service.get_open_project_ids()
        return self.get_news(project_ids=open_project_ids)


class ProjectSingleNewsResource(Resource):

    @jwt_required()
    def get(self, project_id, news_id):
        """
        Retrieve a single given news related to a given project
        ---
        tags:
          - News
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: news_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: Single given news related to given project
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                    title:
                      type: string
                    content:
                      type: string
                    created_at:
                      type: string
                      format: date-time
                    author_id:
                      type: string
                      format: uuid
                    project_id:
                      type: string
                      format: uuid
          '404':
            description: News or project not found
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        news = news_service.get_news(project_id, news_id)
        if len(news["data"]) > 0:
            return news["data"][0]
        else:
            raise NewsNotFoundException
