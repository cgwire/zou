from flask import abort, request
from flask_restful import Resource, inputs

from zou.app.mixin import ArgsMixin
from zou.app.services import (
    assets_service,
    chats_service,
    entities_service,
    persons_service,
    projects_service,
    shots_service,
    time_spents_service,
    user_service,
)
from zou.app.utils import date_helpers
from zou.app.services.exception import WrongDateFormatException


class AssetTasksResource(Resource):

    def get(self, asset_id):
        """
        Get asset tasks
        ---
        description: Return tasks related to given asset for current user.
        tags:
        - User
        parameters:
          - in: path
            name: asset_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given asset for current user
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Asset not found
        """
        assets_service.get_asset(asset_id)
        return user_service.get_tasks_for_entity(asset_id)


class AssetTaskTypesResource(Resource):

    def get(self, asset_id):
        """
        Get asset task types
        ---
        tags:
        - User
        description: Return task types related to given asset for current user.
        parameters:
          - in: path
            name: asset_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Task types related to given asset for current user
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Asset not found
        """
        assets_service.get_asset(asset_id)
        return user_service.get_task_types_for_entity(asset_id)


class ShotTaskTypesResource(Resource):

    def get(self, shot_id):
        """
        Get shot tasks
        ---
        tags:
        - User
        description: Return tasks related to given shot for current user.
        parameters:
          - in: path
            name: shot_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given shot for current user
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Shot not found
        """
        shots_service.get_shot(shot_id)
        return user_service.get_task_types_for_entity(shot_id)


class SceneTaskTypesResource(Resource):
    """
    Return tasks related to given scene for current user.
    """

    def get(self, scene_id):
        """
        Get scene tasks
        ---
        tags:
        - User
        description: Return tasks related to given scene for current user.
        parameters:
          - in: path
            name: scene_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given scene for current user
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Scene not found
        """
        shots_service.get_scene(scene_id)
        return user_service.get_task_types_for_entity(scene_id)


class SequenceTaskTypesResource(Resource):

    def get(self, sequence_id):
        """
        Get sequence task types
        ---
        tags:
        - User
        description: Return task types related to given sequence for current user
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given sequence for current user
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Sequence not found
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_task_types_for_entity(sequence_id)


class AssetTypeAssetsResource(Resource):

    def get(self, project_id, asset_type_id):
        """
        Get project assets
        ---
        tags:
        - User
        description: Return assets of which type is given asset type and are listed in given project if user has access to this project.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: asset_type_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Assets of which type is given asset type and are listed in given project
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Project or asset type not found
        """
        projects_service.get_project(project_id)
        assets_service.get_asset_type(asset_type_id)
        return user_service.get_assets_for_asset_type(
            project_id, asset_type_id
        )


class OpenProjectsResource(Resource, ArgsMixin):

    def get(self):
        """
        Get open projects
        ---
        tags:
        - User
        description: Return open projects for which the user has at least one task assigned
        parameters:
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter projects by name
        responses:
            200:
              description: Open projects for which the user has at least one task assigned
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        name = self.get_text_parameter("name")
        return user_service.get_open_projects(name=name)


class ProjectSequencesResource(Resource):

    def get(self, project_id):
        """
        Get project sequences
        ---
        tags:
        - User
        description: Return sequences related to given project if the current user has access to it
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Sequences related to given project
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Project not found
        """
        projects_service.get_project(project_id)
        return user_service.get_sequences_for_project(project_id)


class ProjectEpisodesResource(Resource):

    def get(self, project_id):
        """
        Get project episodes
        ---
        tags:
        - User
        description: Return episodes related to given project if the current user has access to it.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Episodes related to given project
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Project not found
        """
        projects_service.get_project(project_id)
        return user_service.get_project_episodes(project_id)


class ProjectAssetTypesResource(Resource):

    def get(self, project_id):
        """
        Get project asset types
        ---
        tags:
        - User
        description: Return asset types related to given project if the current
          user has access to it.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Asset types related to given project
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Project not found
        """
        projects_service.get_project(project_id)
        return user_service.get_asset_types_for_project(project_id)


class SequenceShotsResource(Resource):

    def get(self, sequence_id):
        """
        Get sequence shots
        ---
        tags:
        - User
        description: Return shots related to given sequence if the current user has access to it.
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Shots related to given sequence
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Sequence not found
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_shots_for_sequence(sequence_id)


class SequenceScenesResource(Resource):

    def get(self, sequence_id):
        """
        Get sequence scenes
        ---
        tags:
        - User
        description: Return scenes related to given sequence if the current user has access to it.
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Scenes related to given sequence
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Sequence not found
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_scenes_for_sequence(sequence_id)


class ShotTasksResource(Resource):

    def get(self, shot_id):
        """
        Get shot tasks
        ---
        tags:
        - User
        description: Return tasks related to given shot for current user.
        parameters:
          - in: path
            name: shot_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given shot
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Shot not found
        """
        shots_service.get_shot(shot_id)
        return user_service.get_tasks_for_entity(shot_id)


class SceneTasksResource(Resource):

    def get(self, scene_id):
        """
        Get scene tasks
        ---
        tags:
        - User
        description: Return tasks related to given scene for current user.
        parameters:
          - in: path
            name: scene_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given scene
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Scene not found
        """
        shots_service.get_scene(scene_id)
        return user_service.get_tasks_for_entity(scene_id)


class SequenceTasksResource(Resource):

    def get(self, sequence_id):
        """
        Get sequence tasks
        ---
        tags:
        - User
        description: Return tasks related to given sequence for current user.
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks related to given sequence
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            404:
              description: Sequence not found
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_tasks_for_entity(sequence_id)


class TodosResource(Resource):
    """
    Return tasks currently assigned to current user and of which status
    has is_done attribute set to false.
    """

    def get(self):
        """
        Get my tasks
        ---
        tags:
        - User
        description: Return tasks currently assigned to current user and of which status has is_done attribute set to false.
        responses:
            200:
              description: Unfinished tasks currently assigned to current user
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        return user_service.get_todos()


class ToChecksResource(Resource):

    def get(self):
        """
        Get tasks requiring feedback
        ---
        tags:
        - User
        description: Return tasks requiring feedback for current user departments. If the user is not a supervisor, it returns an empty list
        responses:
            200:
              description: Tasks requiring feedback in current user departments
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        return user_service.get_tasks_to_check()


class DoneResource(Resource):

    def get(self):
        """
        Get done tasks
        ---
        tags:
        - User
        description: Return tasks currently assigned to current user and of which status has is_done attribute set to true. It returns only tasks of open projects.
        responses:
            200:
              description: Finished tasks currently assigned to current user
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        return user_service.get_done_tasks()


class FiltersResource(Resource, ArgsMixin):

    def get(self):
        """
        Get filters
        ---
        tags:
        - User
        description: Allow toretrieve filters for current user and only for open projects.
        responses:
            200:
              description: Filters for current user and only for open projects
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        return user_service.get_filters()

    def post(self):
        """
        Create filter.
        ---
        tags:
        - User
        description: Create filter for current user and only for open projects.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - query
                  - list_type
                  - project_id
                properties:
                  name:
                    type: string
                    example: Name of filter
                  query:
                    type: string
                    example: '{"project_id": "uuid"}'
                  list_type:
                    type: string
                    example: todo
                  entity_type:
                    type: string
                    example: Asset
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  is_shared:
                    type: boolean
                    default: false
                  search_filter_group_id:
                    type: string
                    format: uuid
                  department_id:
                    type: string
                    format: uuid
        responses:
            201:
              description: Filter for current user and only for open projects created
              content:
                application/json:
                  schema:
                    type: object
            400:
              description: Bad request
        """
        arguments = self.get_arguments()

        return (
            user_service.create_filter(
                arguments["list_type"],
                arguments["name"],
                arguments["query"],
                arguments["project_id"],
                arguments["entity_type"],
                arguments["is_shared"],
                arguments["search_filter_group_id"],
                department_id=arguments["department_id"],
            ),
            201,
        )

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "", True),
                ("query", "", True),
                ("list_type", "todo", True),
                ("project_id", None, False),
                ("entity_type", None, False),
                ("is_shared", False, False, inputs.boolean),
                ("search_filter_group_id", None, False),
                ("department_id", None, False),
            ]
        )


class FilterResource(Resource, ArgsMixin):

    def put(self, filter_id):
        """
        Update filter
        ---
        tags:
        - User
        description: Update given filter if it's owned by current user
        parameters:
          - in: path
            name: filter_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given filter with updated data.
        """
        data = self.get_args(
            [
                ("name", None, False),
                ("search_query", None, False),
                ("search_filter_group_id", None, False),
                ("is_shared", None, False, inputs.boolean),
                ("project_id", None, None),
                ("department_id", None, None),
            ]
        )
        data = self.clear_empty_fields(
            data, ignored_fields=["search_filter_group_id"]
        )
        user_filter = user_service.update_filter(filter_id, data)
        return user_filter, 200

    def delete(self, filter_id):
        """
        Delete filter.
        ---
        tags:
        - User
        description: Delete given filter if it's owned by current user
        parameters:
          - in: path
            name: filter_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Filter deleted successfully
            404:
              description: Filter not found
        """
        user_service.remove_filter(filter_id)
        return "", 204


class FilterGroupsResource(Resource, ArgsMixin):

    def get(self):
        """
        Get filter groups.
        ---
        tags:
        - User
        description: Retrieve filter groups for current user and only for open projects
        responses:
            200:
              description: Filter groups for current user and only for open projects
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        return user_service.get_filter_groups()

    def post(self):
        """
        Create filter group
        ---
        tags:
        - User
        description: Create filter group for current user and only for open projects.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - color
                  - list_type
                  - project_id
                properties:
                  name:
                    type: string
                    example: Name of filter group
                  color:
                    type: string
                    example: #FF0000
                  list_type:
                    type: string
                    example: todo
                  entity_type:
                    type: string
                    example: Asset
                  is_shared:
                    type: boolean
                    default: false
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  department_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Filter group for the current user and only for open projects created
              content:
                application/json:
                  schema:
                    type: object
            400:
              description: Bad request
        """
        arguments = self.get_arguments()
        return (
            user_service.create_filter_group(
                arguments["list_type"],
                arguments["name"],
                arguments["color"],
                arguments["project_id"],
                arguments["entity_type"],
                arguments["is_shared"],
                arguments["department_id"],
            ),
            201,
        )

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "", True),
                ("color", "", True),
                ("list_type", "todo", True),
                ("project_id", None, False),
                ("is_shared", False, False, inputs.boolean),
                ("entity_type", None, False),
                ("department_id", None, False),
            ]
        )


class FilterGroupResource(Resource, ArgsMixin):

    def get(self, search_filter_group_id):
        """
        Get filter group
        ---
        tags:
        - User
        description: Retrieve given filter group for the current user.
        responses:
            200:
                description: Filter groups for the current user and only for
                             open projects
        """
        return user_service.get_filter_group(search_filter_group_id)

    def put(self, filter_group_id):
        """
        Update filter group
        ---
        tags:
        - User
        description: Update given filter group if it's owned by the current user.
        parameters:
          - in: path
            name: filter_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: name
            type: string
            example: Name of the filter group
          - in: formData
            name: color
            type: string
            example: Color of the filter group
          - in: formData
            name: is_shared
            type: boolean
            example: True
          - in: formData
            name: project_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: department_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given filter group with updated data
        """
        data = self.get_args(
            [
                ("name", None, False),
                ("color", None, False),
                ("is_shared", None, False, inputs.boolean),
                ("project_id", None, None),
                ("department_id", None, None),
            ]
        )

        data = self.clear_empty_fields(data)
        user_filter = user_service.update_filter_group(filter_group_id, data)
        return user_filter, 200

    def delete(self, filter_group_id):
        """
        Delete filter group
        ---
        tags:
        - User
        description: Delete given filter group if it's owned by the current user.
        parameters:
          - in: path
            name: filter_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Empty response
        """
        user_service.remove_filter_group(filter_group_id)
        return "", 204


class DesktopLoginLogsResource(Resource, ArgsMixin):

    def get(self):
        """
        Get desktop login logs
        ---
        tags:
        - User
        description: Retrieve desktop login logs.
        responses:
            200:
              description: Desktop login logs
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        current_user = persons_service.get_current_user()
        return persons_service.get_desktop_login_logs(current_user["id"])

    def post(self):
        """
        Create desktop login log
        ---
        tags:
        - User
        description: Create a desktop login log. The desktop login log can only be created by the current user.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  date:
                    type: string
                    format: date
                    example: "2022-07-12"
        responses:
            201:
              description: Desktop login log created
              content:
                application/json:
                  schema:
                    type: object
            400:
              description: Bad request
        """
        arguments = self.get_args(
            ["date", date_helpers.get_utc_now_datetime()]
        )
        current_user = persons_service.get_current_user()
        desktop_login_log = persons_service.create_desktop_login_logs(
            current_user["id"], arguments["date"]
        )
        return desktop_login_log, 201


class NotificationsResource(Resource, ArgsMixin):

    def get(self):
        """
        Get notifications
        ---
        tags:
          - User
        description: Return last 100 user notifications filtered by given parameters.
        parameters:
          - in: query
            name: after
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Filter notifications after this date
          - in: query
            name: before
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Filter notifications before this date
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task type ID
          - in: query
            name: task_status_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task status ID
          - in: query
            name: type
            required: false
            schema:
              type: string
            description: Filter by notification type
          - in: query
            name: read
            required: false
            schema:
              type: boolean
            description: Filter by read status
          - in: query
            name: watching
            required: false
            schema:
              type: boolean
            description: Filter by watching status
        responses:
            200:
              description: 100 last user notifications
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        (
            after,
            before,
            task_type_id,
            task_status_id,
            notification_type,
        ) = self.get_arguments()

        read = None
        if request.args.get("read", None) is not None:
            read = self.get_bool_parameter("read")
        watching = None
        if request.args.get("watching", None) is not None:
            watching = self.get_bool_parameter("watching")
        print("watching", watching)
        notifications = user_service.get_last_notifications(
            before=before,
            task_type_id=task_type_id,
            task_status_id=task_status_id,
            notification_type=notification_type,
            read=read,
            watching=watching,
        )
        return notifications

    def get_arguments(self):
        return (
            self.get_text_parameter("after"),
            self.get_text_parameter("before"),
            self.get_text_parameter("task_type_id"),
            self.get_text_parameter("task_status_id"),
            self.get_text_parameter("type"),
        )


class NotificationResource(Resource, ArgsMixin):

    def get(self, notification_id):
        """
        Get notification
        ---
        tags:
        - User
        description: Return notification matching given id, only if it's a notification that belongs to current user.
        parameters:
          - in: path
            name: notification_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Notification matching given ID
              content:
                application/json:
                  schema:
                    type: object
            404:
              description: Notification not found
        """
        return user_service.get_notification(notification_id)

    def put(self, notification_id):
        """
        Update notification
        ---
        tags:
        - User
        description: Change notification read status.
        parameters:
          - in: path
            name: notification_id
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
                  read:
                    type: boolean
                    description: Mark notification as read/unread
        responses:
            200:
              description: Updated notification
              content:
                application/json:
                  schema:
                    type: object
            404:
              description: Notification not found
        """
        data = self.get_args([("read", None, False, inputs.boolean)])
        return user_service.update_notification(notification_id, data["read"])


class MarkAllNotificationsAsReadResource(Resource):

    def post(self):
        """
        Mark all notifications as read
        ---
        tags:
        - User
        description: Mark all notifications as read. It applies to all notifications of the current user.
        responses:
            200:
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      success:
                        type: boolean
                        example: true
        """
        user_service.mark_notifications_as_read()
        return {"success": True}


class HasTaskSubscribedResource(Resource):

    def get(self, task_id):
        """
        Check task subscription
        ---
        tags:
          - User
        description: Return true if current user has subscribed to given task.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: True if current user has subscribed to given task, False otherwise
              content:
                application/json:
                  schema:
                    type: boolean
            404:
              description: Task not found
        """
        return user_service.has_task_subscription(task_id)


class TaskSubscribeResource(Resource):

    def post(self, task_id):
        """
        Subscribe to task
        ---
        tags:
        - User
        description: Create a subscription entry. It applies to given task and current user. When a user
            subscribed, he gets notified everytime a comment is posted on the
            task. When a user subscribes, he gets notified everytime a comment
            is posted on the task.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Subscription entry created
              content:
                application/json:
                  schema:
                    type: object
            404:
              description: Task not found
        """
        return user_service.subscribe_to_task(task_id), 201


class TaskUnsubscribeResource(Resource):

    def delete(self, task_id):
        """
        Unsubscribe from task
        ---
        tags:
        - User
        description: Remove the subscription entry matching given task and current user. The user will no longer receive notifications for this task.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Subscription entry removed
            404:
              description: Task not found
        """
        user_service.unsubscribe_from_task(task_id)
        return "", 204


class HasSequenceSubscribedResource(Resource):

    def get(self, sequence_id, task_type_id):
        """
        Check sequence subscription
        ---
        tags:
        - User
        description: Return true if current user has subscribed to given sequence and task type.
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: True if current user has subscribed to given sequence and task type, False otherwise
              content:
                application/json:
                  schema:
                    type: boolean
            404:
              description: Sequence or task type not found
        """
        return user_service.has_sequence_subscription(
            sequence_id, task_type_id
        )


class SequenceSubscribeResource(Resource):

    def post(self, sequence_id, task_type_id):
        """
        Subscribe to sequence
        ---
        tags:
        - User
        description: Create a subscription entry for given sequence, task type and current user. When a user subscribes, he gets notified every time a comment is posted on tasks related to the sequence.
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Subscription entry created
              content:
                application/json:
                  schema:
                    type: object
            404:
              description: Sequence or task type not found
        """
        subscription = user_service.subscribe_to_sequence(
            sequence_id, task_type_id
        )
        return subscription, 201


class SequenceUnsubscribeResource(Resource):

    def delete(self, sequence_id, task_type_id):
        """
        Unsubscribe from sequence
        ---
        tags:
        - User
        description: Remove a subscription entry for given sequence, task type and current user.
        parameters:
          - in: path
            name: sequence_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Subscription entry removed
            404:
              description: Sequence or task type not found
        """
        user_service.unsubscribe_from_sequence(sequence_id, task_type_id)
        return "", 204


class SequenceSubscriptionsResource(Resource):

    def get(self, project_id, task_type_id):
        """
        Get sequence subscriptions
        ---
        tags:
        - User
        description: Return the list of sequence ids to which the current user has subscribed for given task type.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: List of sequence ids to which the current user has subscribed for given task type
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: string
                      format: uuid
            404:
              description: Project or task type not found
        """
        return user_service.get_sequence_subscriptions(
            project_id, task_type_id
        )


class TimeSpentsResource(Resource):
    """
    Get all time spents for the current user.
    Optionnaly can accept date range parameters.
    """

    def get(self):
        """
        Get time spents
        ---
        tags:
        - User
        description: Get all time spents for the current user. Optionally can accept date range parameters.
        parameters:
          - in: query
            name: start_date
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Start date for filtering time spents
          - in: query
            name: end_date
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: End date for filtering time spents
        responses:
            200:
              description: All time spents for the current user
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
            400:
              description: Wrong date format
        """
        arguments = self.get_args(["start_date", "end_date"])
        start_date, end_date = arguments["start_date"], arguments["end_date"]
        current_user = persons_service.get_current_user()
        if not start_date and not end_date:
            return time_spents_service.get_time_spents(current_user["id"])

        if None in [start_date, end_date]:
            abort(
                400,
                "If querying for a range of dates, both a `start_date` and"
                " an `end_date` must be given.",
            )

        try:
            return time_spents_service.get_time_spents_range(
                current_user["id"], start_date, end_date
            )
        except WrongDateFormatException:
            abort(
                400,
                f"Wrong date format for {start_date} and/or {end_date}",
            )


class DateTimeSpentsResource(Resource):

    def get(self, date):
        """
        Get time spents by date.
        ---
        tags:
        - User
        description: Get time spents on for current user and given date.
        parameters:
          - in: path
            name: date
            required: true
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Date to get time spents for
        responses:
            200:
              description: Time spents on for current user and given date
              content:
                application/json:
                  schema:
                    type: object
            400:
              description: Wrong date format
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spents(
                current_user["id"], date
            )
        except WrongDateFormatException:
            abort(400)


class TaskTimeSpentResource(Resource):

    def get(self, task_id, date):
        """
        Get task time spent.
        ---
        tags:
        - User
        description: Get time spents for current user and given date.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: date
            required: true
            schema:
              type: string
              format: date
            example: "2022-07-12"
        responses:
            200:
              description: Time spents for current user and given date
              content:
                application/json:
                  schema:
                    type: object
            404:
              description: Wrong date format or task not found
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spent(
                current_user["id"], task_id, date
            )
        except WrongDateFormatException:
            abort(404)


class DayOffResource(Resource):

    def get(self, date):
        """
        Get day off
        ---
        tags:
        - User
        description: Get day off object for current user and given date.
        parameters:
          - in: path
            name: date
            required: true
            schema:
              type: string
              format: date
            example: "2022-07-12"
        responses:
            200:
              description: Day off object for current user and given date
              content:
                application/json:
                  schema:
                    type: object
            404:
              description: Wrong date format
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_day_off(current_user["id"], date)
        except WrongDateFormatException:
            abort(404)


class ContextResource(Resource):

    def get(self):
        """
        Get context
        ---
        tags:
          - User
        description: Return context required to properly run a full app connected to the API (like the Kitsu web client)
        responses:
            200:
              description: Context to properly run a full app connected to the API
              content:
                application/json:
                  schema:
                    type: object
        """
        return user_service.get_context()


class ClearAvatarResource(Resource):

    def delete(self):
        """
        Clear avatar
        ---
        tags:
          - User
        description: Set has_avatar flag to False for current user and remove its avatar file.
        responses:
            204:
              description: Avatar file deleted
            404:
              description: User not found
        """
        user = persons_service.get_current_user()
        persons_service.clear_avatar(user["id"])
        return "", 204


class ChatsResource(Resource):

    def get(self):
        """
        Get chats
        ---
        tags:
            - User
        description: Return chats where user is participant
        responses:
            200:
              description: Chats where user is participant
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
        """
        user = persons_service.get_current_user()
        return chats_service.get_chats_for_person(user["id"])


class JoinChatResource(Resource):

    def post(self, entity_id):
        """
        Join chat
        ---
        tags:
          - User
        description: Join chat for given entity (be listed as participant).
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Chat joined
              content:
                application/json:
                  schema:
                    type: object
            404:
              description: Entity not found
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        person = persons_service.get_current_user()
        return chats_service.join_chat(entity_id, person["id"])

    def delete(self, entity_id):
        """
        Leave chat
        ---
        tags:
         - User
        description: Leave chat for given entity (be removed from participants).
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Chat left successfully
            404:
              description: Entity not found
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        person = persons_service.get_current_user()
        chats_service.leave_chat(entity_id, person["id"])
        return "", 204
