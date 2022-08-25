import datetime

from flask import request, abort
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin

from zou.app.services import (
    assets_service,
    persons_service,
    projects_service,
    shots_service,
    time_spents_service,
    user_service,
)

from zou.app.services.exception import WrongDateFormatException


class AssetTasksResource(Resource):
    """
    Return tasks related to given asset for current user.
    """

    @jwt_required
    def get(self, asset_id):
        """
        Return tasks related to given asset for current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks related to given asset for current user
        """
        assets_service.get_asset(asset_id)
        return user_service.get_tasks_for_entity(asset_id)


class AssetTaskTypesResource(Resource):
    """
    Return task types related to given asset for current user.
    """

    @jwt_required
    def get(self, asset_id):
        """
        Return task types related to given asset for current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: asset_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Task types related to given asset for current user
        """
        assets_service.get_asset(asset_id)
        return user_service.get_task_types_for_entity(asset_id)


class ShotTaskTypesResource(Resource):
    """
    Return tasks related to given shot for current user.
    """

    @jwt_required
    def get(self, shot_id):
        """
        Return tasks related to given shot for current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks related to given shot for current user
        """
        shots_service.get_shot(shot_id)
        return user_service.get_task_types_for_entity(shot_id)


class SceneTaskTypesResource(Resource):
    """
    Return tasks related to given scene for current user.
    """

    @jwt_required
    def get(self, scene_id):
        """
        Return tasks related to given scene for current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks related to given scene for current user
        """
        shots_service.get_scene(scene_id)
        return user_service.get_task_types_for_entity(scene_id)


class SequenceTaskTypesResource(Resource):
    """
    Return task types related to given sequence for current user.
    """

    @jwt_required
    def get(self, sequence_id):
        """
        Return tasks related to given sequence for current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks related to given sequence for current user
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_task_types_for_entity(sequence_id)


class AssetTypeAssetsResource(Resource):
    """
    Return assets of which type is given asset type and are listed in given
    project if user has access to this project.
    """

    @jwt_required
    def get(self, project_id, asset_type_id):
        """
        Return assets of which type is given asset type and are listed in given project if user has access to this project.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: asset_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Assets of which type is given asset type and are listed in given project
        """
        projects_service.get_project(project_id)
        assets_service.get_asset_type(asset_type_id)
        return user_service.get_assets_for_asset_type(
            project_id, asset_type_id
        )


class OpenProjectsResource(Resource):
    """
    Return open projects for which the user has at least one task assigned.
    """

    @jwt_required
    def get(self):
        """
        Return open projects for which the user has at least one task assigned.
        ---
        tags:
        - User
        responses:
            200:
                description: Open projects for which the user has at least one task assigned
        """
        name = request.args.get("name", None)
        return user_service.get_open_projects(name=name)


class ProjectSequencesResource(Resource):
    """
    Return sequences related to given project if the current user has access to it.
    """

    @jwt_required
    def get(self, project_id):
        """
        Return sequences related to given project if the current user has access to it.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Sequences related to given project
        """
        projects_service.get_project(project_id)
        return user_service.get_sequences_for_project(project_id)


class ProjectEpisodesResource(Resource):
    """
    Return episodes related to given project if the current user has access to
    it.
    """

    @jwt_required
    def get(self, project_id):
        """
        Return episodes related to given project if the current user has access to it.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Episodes related to given project
        """
        projects_service.get_project(project_id)
        return user_service.get_project_episodes(project_id)


class ProjectAssetTypesResource(Resource):
    """
    Return asset types related to given project if the current user has access to it.
    """

    @jwt_required
    def get(self, project_id):
        """
        Return asset types related to given project if the current user has access to it.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Asset types related to given project
        """
        projects_service.get_project(project_id)
        return user_service.get_asset_types_for_project(project_id)


class SequenceShotsResource(Resource):
    """
    Return shots related to given sequence if the current user has access
    to it.
    """

    @jwt_required
    def get(self, sequence_id):
        """
        Return shots related to given sequence if the current user has access to it.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Shots related to given sequence
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_shots_for_sequence(sequence_id)


class SequenceScenesResource(Resource):
    """
    Return scenes related to given sequence if the current user has access
    to it.
    """

    @jwt_required
    def get(self, sequence_id):
        """
        Return scenes related to given sequence if the current user has access to it.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Scenes related to given sequence
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_scenes_for_sequence(sequence_id)


class ShotTasksResource(Resource):
    """
    Return tasks related to given shot for current user.
    """

    @jwt_required
    def get(self, shot_id):
        """
        Return tasks related to given shot for current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: shot_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks related to given shot
        """
        shots_service.get_shot(shot_id)
        return user_service.get_tasks_for_entity(shot_id)


class SceneTasksResource(Resource):
    """
    Return tasks related to given scene for current user.
    """

    @jwt_required
    def get(self, scene_id):
        """
        Return tasks related to given scene for current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: scene_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks related to given scene
        """
        shots_service.get_scene(scene_id)
        return user_service.get_tasks_for_entity(scene_id)


class SequenceTasksResource(Resource):
    """
    Return tasks related to given sequence for current user.
    """

    @jwt_required
    def get(self, sequence_id):
        """
        Return tasks related to given sequence for current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks related to given sequence
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_tasks_for_entity(sequence_id)


class TodosResource(Resource):
    """
    Return tasks currently assigned to current user and of which status
    has is_done attribute set to false.
    """

    @jwt_required
    def get(self):
        """
        Return tasks currently assigned to current user and of which status has is_done attribute set to false.
        ---
        tags:
        - User
        responses:
            200:
                description: Unfinished tasks currently assigned to current user
        """
        return user_service.get_todos()


class DoneResource(Resource):
    """
    Return tasks currently assigned to current user and of which status
    has is_done attribute set to true. It returns only tasks of open projects.
    """

    @jwt_required
    def get(self):
        """
        Return tasks currently assigned to current user and of which status has is_done attribute set to true.
        ---
        tags:
        - User
        description: It returns only tasks of open projects.
        responses:
            200:
                description: Finished tasks currently assigned to current user
        """
        return user_service.get_done_tasks()


class FiltersResource(Resource, ArgsMixin):
    """
    Allow to create and retrieve filters for current user and only for
    open projects.
    """

    @jwt_required
    def get(self):
        """
        Retrieve filters for current user and only for open projects.
        ---
        tags:
        - User
        responses:
            200:
                description: Filters for current user and only for open projects
        """
        return user_service.get_filters()

    @jwt_required
    def post(self):
        """
        Create filter for current user and only for open projects.
        ---
        tags:
        - User
        parameters:
          - in: formData
            name: name
            required: True
            type: string
            x-example: Name of filter
          - in: formData
            name: query
            required: True
            type: string
          - in: formData
            name: list_type
            required: True
            type: string
          - in: formData
            name: entity_type
            required: False
            type: string
          - in: formData
            name: project_id
            required: True
            type: string
            format: UUID
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Filter for current user and only for open projects created
        """
        arguments = self.get_arguments()

        return (
            user_service.create_filter(
                arguments["list_type"],
                arguments["name"],
                arguments["query"],
                arguments["project_id"],
                arguments["entity_type"],
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
            ]
        )


class FilterResource(Resource, ArgsMixin):
    """
    Allow to remove or update given filter if it's owned by current user.
    """

    @jwt_required
    def put(self, filter_id):
        """
        Update given filter if it's owned by current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: filter_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given filter updated
        """
        data = self.get_args(
            [
                ("name", None, False),
                ("search_query", None, False),
            ]
        )
        data = self.clear_empty_fields(data)
        user_filter = user_service.update_filter(filter_id, data)
        return user_filter, 200

    @jwt_required
    def delete(self, filter_id):
        """
        Delete given filter if it's owned by current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: filter_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Given filter deleted
        """
        user_service.remove_filter(filter_id)
        return "", 204


class DesktopLoginLogsResource(Resource):
    """
    Allow to create and retrieve desktop login logs. Desktop login logs can only
    be created by current user.
    """

    @jwt_required
    def get(self):
        """
        Retrieve desktop login logs.
        ---
        tags:
        - User
        responses:
            200:
                description: Desktop login logs
        """
        current_user = persons_service.get_current_user()
        return persons_service.get_desktop_login_logs(current_user["id"])

    @jwt_required
    def post(self):
        """
        Create desktop login logs.
        ---
        tags:
        - User
        description: Desktop login logs can only be created by current user.
        parameters:
          - in: formData
            name: date
            type: string
            format: date
            x-example: "2022-07-12"
        responses:
            201:
                description: Desktop login logs created
        """
        arguments = self.get_arguments()
        current_user = persons_service.get_current_user()
        desktop_login_log = persons_service.create_desktop_login_logs(
            current_user["id"], arguments["date"]
        )
        return desktop_login_log, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument("date", default=datetime.datetime.now())
        return parser.parse_args()


class NotificationsResource(Resource, ArgsMixin):
    @jwt_required
    def get(self):
        """
        Return last 100 user notifications filtered by given parameters.
        ---
        tags:
          - User
        parameters:
          - in: formData
            name: after
            type: string
            format: date
            x-example: "2022-07-12"
          - in: formData
            name: before
            type: string
            format: date
            x-example: "2022-07-12"
        responses:
            200:
                description: 100 last user notifications
        """
        (
            after,
            before,
            task_type_id,
            task_status_id,
            notification_type,
        ) = self.get_arguments()
        notifications = user_service.get_last_notifications(
            before=before,
            task_type_id=task_type_id,
            task_status_id=task_status_id,
            notification_type=notification_type,
        )
        user_service.mark_notifications_as_read()
        return notifications

    def get_arguments(self):
        return (
            self.get_text_parameter("after"),
            self.get_text_parameter("before"),
            self.get_text_parameter("task_type_id"),
            self.get_text_parameter("task_status_id"),
            self.get_text_parameter("type"),
        )


class NotificationResource(Resource):
    """
    Return notification matching given id, only if it's a notification that
    belongs to current user.
    """

    @jwt_required
    def get(self, notification_id):
        """
        Return notification matching given id, only if it's a notification that belongs to current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: notification_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25

        responses:
            200:
                description: Notification matching given ID
        """
        return user_service.get_notification(notification_id)


class HasTaskSubscribedResource(Resource):
    """
    Return true if current user has subscribed to given task.
    """

    @jwt_required
    def get(self, task_id):
        """
        Return true if current user has subscribed to given task.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: True if current user has subscribed to given task, False otherwise
        """
        return user_service.has_task_subscription(task_id)


class TaskSubscribeResource(Resource):
    """
    Create a subscription entry for given task and current user.
    When a user subscribes, he gets notified everytime a comment is posted on the task.
    """

    @jwt_required
    def post(self, task_id):
        """
        Create a subscription entry for given task and current user.
        ---
        tags:
        - User
        description: When a user subscribes, he gets notified everytime a comment is posted on the task.
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Subscription entry created
        """
        return user_service.subscribe_to_task(task_id), 201


class TaskUnsubscribeResource(Resource):
    """
    Remove the subscription entry matching given task and current user.
    The user will no longer receive notifications for this task.
    """

    @jwt_required
    def delete(self, task_id):
        """
        Remove the subscription entry matching given task and current user.
        ---
        tags:
        - User
        description: The user will no longer receive notifications for this task.
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Subscription entry removed
        """
        user_service.unsubscribe_from_task(task_id)
        return "", 204


class HasSequenceSubscribedResource(Resource):
    """
    Return true if current user has subscribed to given sequence and task type.
    """

    @jwt_required
    def get(self, sequence_id, task_type_id):
        """
        Return true if current user has subscribed to given sequence and task type.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: True if current user has subscribed to given sequence and task type, False otherwise
        """
        return user_service.has_sequence_subscription(
            sequence_id, task_type_id
        )


class SequenceSubscribeResource(Resource):
    """
    Create a subscription entry for given sequence, task type and current user.
    When a user subscribes, he gets notified every time a comment is posted on tasks related to the sequence.
    """

    @jwt_required
    def post(self, sequence_id, task_type_id):
        """
        Create a subscription entry for given sequence, task type and current user.
        ---
        tags:
        - User
        description: When a user subscribes, he gets notified every time a comment is posted on tasks related to the sequence.
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Subscription entry created
        """
        subscription = user_service.subscribe_to_sequence(
            sequence_id, task_type_id
        )
        return subscription, 201


class SequenceUnsubscribeResource(Resource):
    """
    Remove a subscription entry for given sequence, task type and current user.
    """

    @jwt_required
    def delete(self, sequence_id, task_type_id):
        """
        Remove a subscription entry for given sequence, tasl type and current user.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: sequence_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Subscription entry removed
        """
        user_service.unsubscribe_from_sequence(sequence_id, task_type_id)
        return "", 204


class SequenceSubscriptionsResource(Resource):
    """
    Return the list of sequence ids to which the current user has subscribed for given task type.
    """

    @jwt_required
    def get(self, project_id, task_type_id):
        """
        Return the list of sequence ids to which the current user has subscribed for given task type.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: task_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description:  List of sequence ids to which the current user has subscribed for given task type
        """
        return user_service.get_sequence_subscriptions(
            project_id, task_type_id
        )


class TimeSpentsResource(Resource):
    """
    Get time spents on for current user and given date.
    """

    @jwt_required
    def get(self, date):
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spents(
                current_user["id"], date
            )
        except WrongDateFormatException:
            abort(404)


class TaskTimeSpentResource(Resource):
    """
    Get time spents for current user and given date.
    """

    @jwt_required
    def get(self, task_id, date):
        """
        Get time spents for current user and given date.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: date
            required: True
            type: string
            format: date
            x-example: "2022-07-12"
        responses:
            200:
                description:  Time spents for current user and given date
            404:
                description: Wrong date format
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spent(
                current_user["id"], task_id, date
            )
        except WrongDateFormatException:
            abort(404)


class DayOffResource(Resource):
    """
    Get day off object for current user and given date.
    """

    @jwt_required
    def get(self, date):
        """
        Get day off object for current user and given date.
        ---
        tags:
        - User
        parameters:
          - in: path
            name: date
            required: True
            type: string
            format: date
            x-example: "2022-07-12"
        responses:
            200:
                description:  Day off object for current user and given date
            404:
                description: Wrong date format
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_day_off(current_user["id"], date)
        except WrongDateFormatException:
            abort(404)


class ContextResource(Resource):
    @jwt_required
    def get(self):
        """
        Return context required to properly run a full app connected to the API
        (like the Kitsu web client).
        ---
        tags:
          - User
        responses:
            200:
                description: Context to properly run a full app connected to the API
        """
        return user_service.get_context()


class ClearAvatarResource(Resource):
    @jwt_required
    def delete(self):
        """
        Set `has_avatar` flag to False for current user and remove its avatar
        file.
        ---
        tags:
          - User
        responses:
            204:
                description: Avatar file deleted
        """
        user = persons_service.get_current_user()
        persons_service.clear_avatar(user["id"])
        return "", 204
