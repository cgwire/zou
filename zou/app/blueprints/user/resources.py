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
from zou.app import name_space_user, name_space_actions_user


@name_space_user.route('/assets/<asset_id>/tasks')
class AssetTasksResource(Resource):

    @jwt_required
    def get(self, asset_id):
        """
        Return tasks related to given asset for current user.
        """
        assets_service.get_asset(asset_id)
        return user_service.get_tasks_for_entity(asset_id)


@name_space_user.route('/assets/<asset_id>/task-types')
class AssetTaskTypesResource(Resource):

    @jwt_required
    def get(self, asset_id):
        """
        Return task types related to given asset for current user.
        """
        assets_service.get_asset(asset_id)
        return user_service.get_task_types_for_entity(asset_id)


@name_space_user.route('/shots/<shot_id>/task-types')
class ShotTaskTypesResource(Resource):

    @jwt_required
    def get(self, shot_id):
        """
        Return tasks related to given shot for current user.
        """
        shots_service.get_shot(shot_id)
        return user_service.get_task_types_for_entity(shot_id)


@name_space_user.route('/scenes/<scene_id>/task-types')
class SceneTaskTypesResource(Resource):

    @jwt_required
    def get(self, scene_id):
        """
        Return tasks related to given scene for current user.
        """
        shots_service.get_scene(scene_id)
        return user_service.get_task_types_for_entity(scene_id)


@name_space_user.route('/sequences/<sequence_id>/task-types')
class SequenceTaskTypesResource(Resource):

    @jwt_required
    def get(self, sequence_id):
        """
        Return task types related to given sequence for current user.
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_task_types_for_entity(sequence_id)


@name_space_user.route('/projects/<project_id>/asset-types/<asset_type_id>/assets')
class AssetTypeAssetsResource(Resource):

    @jwt_required
    def get(self, project_id, asset_type_id):
        """
        Return assets of which type is given asset type and are listed in given
        project if user has access to this project.
        """
        projects_service.get_project(project_id)
        assets_service.get_asset_type(asset_type_id)
        return user_service.get_assets_for_asset_type(
            project_id, asset_type_id
        )


@name_space_user.route('/projects/open')
class OpenProjectsResource(Resource):

    @jwt_required
    def get(self):
        """
        Return open projects for which the user has at least one task assigned.
        """
        name = request.args.get("name", None)
        return user_service.get_open_projects(name=name)


@name_space_user.route('/projects/<project_id>/sequences')
class ProjectSequencesResource(Resource):

    @jwt_required
    def get(self, project_id):
        """
        Return sequences related to given project if the current user has access to
        it.
        """
        projects_service.get_project(project_id)
        return user_service.get_sequences_for_project(project_id)


@name_space_user.route('/projects/<project_id>/episodes')
class ProjectEpisodesResource(Resource):

    @jwt_required
    def get(self, project_id):
        """
        Return episodes related to given project if the current user has access to
        it.
        """
        projects_service.get_project(project_id)
        return user_service.get_project_episodes(project_id)


@name_space_user.route('/projects/<project_id>/asset-types')
class ProjectAssetTypesResource(Resource):

    @jwt_required
    def get(self, project_id):
        """
        Return asset types related to given project if the current user has access
        to it.
        """
        projects_service.get_project(project_id)
        return user_service.get_asset_types_for_project(project_id)


@name_space_user.route('/sequences/<sequence_id>/shots')
class SequenceShotsResource(Resource):

    @jwt_required
    def get(self, sequence_id):
        """
        Return shots related to given sequence if the current user has access
        to it.
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_shots_for_sequence(sequence_id)


@name_space_user.route('/sequences/<sequence_id>/scenes')
class SequenceScenesResource(Resource):

    @jwt_required
    def get(self, sequence_id):
        """
        Return scenes related to given sequence if the current user has access
        to it.
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_scenes_for_sequence(sequence_id)


@name_space_user.route('/shots/<shot_id>/tasks')
class ShotTasksResource(Resource):

    @jwt_required
    def get(self, shot_id):
        """
        Return tasks related to given shot for current user.
        """
        shots_service.get_shot(shot_id)
        return user_service.get_tasks_for_entity(shot_id)


@name_space_user.route('/scenes/<scene_id>/tasks')
class SceneTasksResource(Resource):

    @jwt_required
    def get(self, scene_id):
        """
        Return tasks related to given scene for current user.
        """
        shots_service.get_scene(scene_id)
        return user_service.get_tasks_for_entity(scene_id)


@name_space_user.route('/sequences/<sequence_id>/tasks')
class SequenceTasksResource(Resource):

    @jwt_required
    def get(self, sequence_id):
        """
        Return tasks related to given sequence for current user.
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_tasks_for_entity(sequence_id)


@name_space_user.route('/tasks')
class TodosResource(Resource):

    @jwt_required
    def get(self):
        """
        Return tasks currently assigned to current user and of which status
        has is_done attribute set to false.
        """
        return user_service.get_todos()


@name_space_user.route('/done-tasks')
class DoneResource(Resource):

    @jwt_required
    def get(self):
        """
        Return tasks currently assigned to current user and of which status
        has is_done attribute set to true. It returns only tasks of open projects.
        """
        return user_service.get_done_tasks()


@name_space_user.route('/filters')
class FiltersResource(Resource, ArgsMixin):
    

    @jwt_required
    def get(self):
        """
        Allow to retrieve filters for current user and only for open projects.
        """
        return user_service.get_filters()

    @jwt_required
    def post(self):
        """
        Allow to create filters for current user and only for
        open projects.
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


@name_space_user.route('/filters/<filter_id>')
class FilterResource(Resource, ArgsMixin):

    @jwt_required
    def put(self, filter_id):
        """
        Allow to update given filter if its owned by current user.
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
        Allow to remove given filter if its owned by current user.
        """
        user_service.remove_filter(filter_id)
        return "", 204


@name_space_user.route('/desktop-login-logs')
class DesktopLoginLogsResource(Resource):

    @jwt_required
    def get(self):
        """
        Allow to retrieve desktop login logs.
        """
        current_user = persons_service.get_current_user()
        return persons_service.get_desktop_login_logs(current_user["id"])

    @jwt_required
    def post(self):
        """
        Allow to create desktop login logs. Desktop login logs can only
        be created by current user.
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


@name_space_user.route('/notifications')
class NotificationsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self):
        """
        Return last 100 user notifications.
        """
        (after, before) = self.get_arguments()
        notifications = user_service.get_last_notifications(
            after=after, before=before
        )
        user_service.mark_notifications_as_read()
        return notifications

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument("after", default=None)
        parser.add_argument("before", default=None)
        args = parser.parse_args()

        return (
            args["after"],
            args["before"],
        )


@name_space_user.route('/notifications/<notification_id>')
class NotificationResource(Resource):

    @jwt_required
    def get(self, notification_id):
        """
        Return notification matching given id, only if it's a notification that
        belongs to current user.
        """
        return user_service.get_notification(notification_id)


@name_space_user.route('/tasks/<task_id>/subscribed')
class HasTaskSubscribedResource(Resource):

    @jwt_required
    def get(self, task_id):
        """
        Return true if current user has subscribed to given task.
        """
        return user_service.has_task_subscription(task_id)


@name_space_actions_user.route('/tasks/<task_id>/subscribe')
class TaskSubscribeResource(Resource):

    @jwt_required
    def post(self, task_id):
        """
        Create a subscription entry for given task and current user. When an user
        subscribe it gets notification everytime a comment is posted on the task.
        """
        return user_service.subscribe_to_task(task_id), 201


@name_space_actions_user.route('/tasks/<task_id>/unsubscribe')
class TaskUnsubscribeResource(Resource):

    @jwt_required
    def delete(self, task_id):
        """
        Remove the subscription entry matching given task and current user.
        The user will no longer receive notifications for this task.
        """
        user_service.unsubscribe_from_task(task_id)
        return "", 204


@name_space_user.route('/entities/<entity_id>/task-types/<task_type_id>/subscribed')
class HasSequenceSubscribedResource(Resource):

    @jwt_required
    def get(self, sequence_id, task_type_id):
        """
        Return true if current user has subscribed to given sequence and task type.
        """
        return user_service.has_sequence_subscription(
            sequence_id, task_type_id
        )


@name_space_actions_user.route('/sequences/<sequence_id>/task-types/<task_type_id>/subscribe')
class SequenceSubscribeResource(Resource):

    @jwt_required
    def post(self, sequence_id, task_type_id):
        """
        Create a subscription entry for given sequence and current user. When an
        subscribe it gets notification everytime a comment is posted on tasks
        related to the sequence.
        """
        subscription = user_service.subscribe_to_sequence(
            sequence_id, task_type_id
        )
        return subscription, 201


@name_space_actions_user.route('/sequences/<sequence_id>/task-types/<task_type_id>/unsubscribe')
class SequenceUnsubscribeResource(Resource):

    @jwt_required
    def delete(self, sequence_id, task_type_id):
        """
        Create a subscription entry for given sequence, task type and current user.
        """
        user_service.unsubscribe_from_sequence(sequence_id, task_type_id)
        return "", 204


@name_space_user.route('/projects/<project_id>/task-types/<task_type_id>/sequence-subscriptions')
class SequenceSubscriptionsResource(Resource):

    @jwt_required
    def get(self, project_id, task_type_id):
        """
        Return list of sequence ids to which the current user has subscribed
        for given task type
        """
        return user_service.get_sequence_subscriptions(
            project_id, task_type_id
        )


@name_space_user.route('/time-spents/<date>')
class TimeSpentsResource(Resource):

    @jwt_required
    def get(self, date):
        """
        Get time spents on for current user and given date.
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spents(
                current_user["id"], date
            )
        except WrongDateFormatException:
            abort(404)


@name_space_user.route('/tasks/<task_id>/time-spents/<date>')
class TaskTimeSpentResource(Resource):

    @jwt_required
    def get(self, task_id, date):
        """
        Get time spents on for current user and given date.
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spent(
                current_user["id"], task_id, date
            )
        except WrongDateFormatException:
            abort(404)


@name_space_user.route('/day-offs/<date>')
class DayOffResource(Resource):

    @jwt_required
    def get(self, date):
        """
        Get day off object for current user and given date.
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_day_off(current_user["id"], date)
        except WrongDateFormatException:
            abort(404)


@name_space_user.route('/context')
class ContextResource(Resource):

    @jwt_required
    def get(self):
        """
        Return context required to run properly a full app connected to
        the API (like the Kitsu web client).
        """
        return user_service.get_context()
