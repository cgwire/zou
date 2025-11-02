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
        Get project latest news
        ---
        description: Get the 50 latest news object (activity feed) for a project
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
            description: Unique identifier of the project
          - in: query
            name: before
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Filter news before this date
          - in: query
            name: after
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Filter news after this date
          - in: query
            name: page
            required: false
            schema:
              type: integer
              default: 1
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
              default: 50
            example: 50
            description: Number of news items per page
          - in: query
            name: person_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter news by specific team member
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter news by task type
          - in: query
            name: task_status_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter news by task status
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter news by specific episode
          - in: query
            name: only_preview
            required: false
            schema:
              type: boolean
              default: false
            example: false
            description: Show only news related to preview uploads
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
                            description: Unique news item identifier
                          title:
                            type: string
                            description: News item title
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
        Get open projects news
        ---
        description: Returns the latest news and activity feed from all 
          projects the user has access to.
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
            description: Filter news by specific project
          - in: query
            name: before
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Filter news before this date
          - in: query
            name: after
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Filter news after this date
          - in: query
            name: page
            required: false
            schema:
              type: integer
              default: 1
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
              default: 50
            example: 50
            description: Number of news items per page
          - in: query
            name: person_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter news by specific team member
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter news by task type
          - in: query
            name: task_status_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter news by task status
          - in: query
            name: episode_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter news by specific episode
          - in: query
            name: only_preview
            required: false
            schema:
              type: boolean
              default: false
            example: false
            description: Show only news related to preview uploads
        responses:
          '200':
            description: News feed successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    data:
                      type: array
                      items:
                        type: object
                      description: Array of news items
                    stats:
                      type: object
                      description: News statistics
                    total:
                      type: integer
                      description: Total number of news items
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
        Get news item
        ---
        description: Retrieves detailed information about a specific news item 
          from a givenproject.
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
            description: Unique identifier of the project
          - in: path
            name: news_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the news item
        responses:
          '200':
            description: News item successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Unique news item identifier
                    title:
                      type: string
                      description: News item title
                    content:
                      type: string
                      description: News item content
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                    author_id:
                      type: string
                      format: uuid
                      description: Author's user ID
                    project_id:
                      type: string
                      format: uuid
                      description: Project identifier
          404:
            description: News item or project not found
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        user_service.block_access_to_vendor()
        news = news_service.get_news(project_id, news_id)
        if len(news["data"]) > 0:
            return news["data"][0]
        else:
            raise NewsNotFoundException
