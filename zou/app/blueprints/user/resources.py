from flasgger import swag_from
from flask import jsonify, request
from flask.views import MethodView

from zou.app.mixin import ArgsMixin
from zou.app.services import (
    assets_service,
    chats_service,
    entities_service,
    persons_service,
    projects_service,
    shots_service,
    time_spents_service,
    permissions_service,
    user_service,
    entity_types_service,
    search_filters_service,
    todos_service,
)
from zou.app.utils import date_helpers, validation
from zou.app.blueprints.user.schemas import (
    CreateSearchFilterSchema,
    UpdateSearchFilterSchema,
    CreateSearchFilterGroupSchema,
    UpdateSearchFilterGroupSchema,
    NotificationUpdateSchema,
    SubscribeTasksSchema,
)
from zou.app.exceptions import (
    WrongDateFormatException,
    WrongParameterException,
)


class AssetTasksResource(MethodView):

    @swag_from("openapi/AssetTasksResource_get.yml")
    def get(self, asset_id):
        """
        Get asset tasks
        """
        assets_service.get_asset(asset_id)
        return user_service.get_tasks_for_entity(asset_id)


class AssetTaskTypesResource(MethodView):

    @swag_from("openapi/AssetTaskTypesResource_get.yml")
    def get(self, asset_id):
        """
        Get asset task types
        """
        assets_service.get_asset(asset_id)
        return user_service.get_task_types_for_entity(asset_id)


class ShotTaskTypesResource(MethodView):

    @swag_from("openapi/ShotTaskTypesResource_get.yml")
    def get(self, shot_id):
        """
        Get shot task types
        """
        shots_service.get_shot(shot_id)
        return user_service.get_task_types_for_entity(shot_id)


class SceneTaskTypesResource(MethodView):
    """
    Return tasks related to given scene for current user.
    """

    @swag_from("openapi/SceneTaskTypesResource_get.yml")
    def get(self, scene_id):
        """
        Get scene task types
        """
        shots_service.get_scene(scene_id)
        return user_service.get_task_types_for_entity(scene_id)


class SequenceTaskTypesResource(MethodView):

    @swag_from("openapi/SequenceTaskTypesResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence task types
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_task_types_for_entity(sequence_id)


class AssetTypeAssetsResource(MethodView):

    @swag_from("openapi/AssetTypeAssetsResource_get.yml")
    def get(self, project_id, asset_type_id):
        """
        Get project assets
        """
        projects_service.get_project(project_id)
        entity_types_service.get_asset_type(asset_type_id)
        return user_service.get_assets_for_asset_type(
            project_id, asset_type_id
        )


class OpenProjectsResource(MethodView, ArgsMixin):

    @swag_from("openapi/OpenProjectsResource_get.yml")
    def get(self):
        """
        Get open projects
        """
        name = self.get_text_parameter("name")
        return user_service.get_open_projects(name=name)


class ProjectSequencesResource(MethodView):

    @swag_from("openapi/ProjectSequencesResource_get.yml")
    def get(self, project_id):
        """
        Get project sequences
        """
        projects_service.get_project(project_id)
        return user_service.get_sequences_for_project(project_id)


class ProjectEpisodesResource(MethodView):

    @swag_from("openapi/ProjectEpisodesResource_get.yml")
    def get(self, project_id):
        """
        Get project episodes
        """
        projects_service.get_project(project_id)
        return user_service.get_project_episodes(project_id)


class ProjectAssetTypesResource(MethodView):

    @swag_from("openapi/ProjectAssetTypesResource_get.yml")
    def get(self, project_id):
        """
        Get project asset types
        """
        projects_service.get_project(project_id)
        return user_service.get_asset_types_for_project(project_id)


class SequenceShotsResource(MethodView):

    @swag_from("openapi/SequenceShotsResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence shots
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_shots_for_sequence(sequence_id)


class SequenceScenesResource(MethodView):

    @swag_from("openapi/SequenceScenesResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence scenes
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_scenes_for_sequence(sequence_id)


class ShotTasksResource(MethodView):

    @swag_from("openapi/ShotTasksResource_get.yml")
    def get(self, shot_id):
        """
        Get shot tasks
        """
        shots_service.get_shot(shot_id)
        return user_service.get_tasks_for_entity(shot_id)


class SceneTasksResource(MethodView):

    @swag_from("openapi/SceneTasksResource_get.yml")
    def get(self, scene_id):
        """
        Get scene tasks
        """
        shots_service.get_scene(scene_id)
        return user_service.get_tasks_for_entity(scene_id)


class SequenceTasksResource(MethodView):

    @swag_from("openapi/SequenceTasksResource_get.yml")
    def get(self, sequence_id):
        """
        Get sequence tasks
        """
        shots_service.get_sequence(sequence_id)
        return user_service.get_tasks_for_entity(sequence_id)


class TodosResource(MethodView):

    @swag_from("openapi/TodosResource_get.yml")
    def get(self):
        """
        Get my tasks
        """
        return todos_service.get_todos()


class ToChecksResource(MethodView, ArgsMixin):

    @swag_from("openapi/ToChecksResource_get.yml")
    def get(self):
        """
        Get tasks requiring feedback
        """
        args = self.get_args(
            [
                ("project_id", None, False, str),
                ("task_type_id", None, False, str),
                ("task_status_id", None, False, str),
                ("person_id", None, False, str),
                ("episode_id", None, False, str),
                ("due_date_since", None, False, str),
                ("due_date_until", None, False, str),
                ("order_by", None, False, str),
                ("page", None, False, int),
                ("limit", 100, False, int),
            ]
        )
        for field in (
            "project_id",
            "task_type_id",
            "task_status_id",
            "episode_id",
        ):
            if args[field] is not None:
                self.check_id_parameter(args[field])
        if args["person_id"] not in (None, "unassigned"):
            for person_id in args["person_id"].split(","):
                self.check_id_parameter(person_id)
        self.parse_date_parameter(args["due_date_since"])
        self.parse_date_parameter(args["due_date_until"])
        return todos_service.get_tasks_to_check(**args)


class ToChecksFilterValuesResource(MethodView):

    @swag_from("openapi/ToChecksFilterValuesResource_get.yml")
    def get(self):
        """
        Get filter values for tasks requiring feedback
        """
        return todos_service.get_tasks_to_check_filter_values()


class DoneResource(MethodView):

    @swag_from("openapi/DoneResource_get.yml")
    def get(self):
        """
        Get done tasks
        """
        return todos_service.get_done_tasks()


class FiltersResource(MethodView, ArgsMixin):

    @swag_from("openapi/FiltersResource_get.yml")
    def get(self):
        """
        Get filters
        """
        return search_filters_service.get_filters()

    @swag_from("openapi/FiltersResource_post.yml")
    def post(self):
        """
        Create filter
        """
        body = validation.validate_request_body(CreateSearchFilterSchema)

        return (
            search_filters_service.create_filter(
                body.list_type,
                body.name,
                body.query,
                body.project_id,
                body.entity_type,
                body.is_shared,
                body.search_filter_group_id,
                department_id=body.department_id,
            ),
            201,
        )


class FilterResource(MethodView, ArgsMixin):

    @swag_from("openapi/FilterResource_put.yml")
    def put(self, filter_id):
        """
        Update filter
        """
        body = validation.validate_request_body(UpdateSearchFilterSchema)
        data = body.model_dump(exclude_none=True)
        if "search_filter_group_id" in (body.model_fields_set or set()):
            data["search_filter_group_id"] = body.search_filter_group_id
        user_filter = search_filters_service.update_filter(filter_id, data)
        return user_filter, 200

    @swag_from("openapi/FilterResource_delete.yml")
    def delete(self, filter_id):
        """
        Delete filter
        """
        search_filters_service.remove_filter(filter_id)
        return "", 204


class FilterGroupsResource(MethodView, ArgsMixin):

    @swag_from("openapi/FilterGroupsResource_get.yml")
    def get(self):
        """
        Get filter groups
        """
        return search_filters_service.get_filter_groups()

    @swag_from("openapi/FilterGroupsResource_post.yml")
    def post(self):
        """
        Create filter group
        """
        body = validation.validate_request_body(CreateSearchFilterGroupSchema)
        return (
            search_filters_service.create_filter_group(
                body.list_type,
                body.name,
                body.color,
                body.project_id,
                body.entity_type,
                body.is_shared,
                body.department_id,
            ),
            201,
        )


class FilterGroupResource(MethodView, ArgsMixin):

    @swag_from("openapi/FilterGroupResource_get.yml")
    def get(self, filter_group_id):
        """
        Get filter group
        """
        return search_filters_service.get_filter_group(filter_group_id)

    @swag_from("openapi/FilterGroupResource_put.yml")
    def put(self, filter_group_id):
        """
        Update filter group
        """
        body = validation.validate_request_body(UpdateSearchFilterGroupSchema)
        data = body.model_dump(exclude_none=True)
        user_filter = search_filters_service.update_filter_group(
            filter_group_id, data
        )
        return user_filter, 200

    @swag_from("openapi/FilterGroupResource_delete.yml")
    def delete(self, filter_group_id):
        """
        Delete filter group
        """
        search_filters_service.remove_filter_group(filter_group_id)
        return "", 204


class DesktopLoginLogsResource(MethodView, ArgsMixin):

    @swag_from("openapi/DesktopLoginLogsResource_get.yml")
    def get(self):
        """
        Get desktop login logs
        """
        current_user = persons_service.get_current_user()
        return persons_service.get_desktop_login_logs(current_user["id"])

    @swag_from("openapi/DesktopLoginLogsResource_post.yml")
    def post(self):
        """
        Create desktop login log
        """
        arguments = self.get_args(
            [("date", date_helpers.get_utc_now_datetime())]
        )
        current_user = persons_service.get_current_user()
        desktop_login_log = persons_service.create_desktop_login_logs(
            current_user["id"], arguments["date"]
        )
        return desktop_login_log, 201


class NotificationsResource(MethodView, ArgsMixin):

    @swag_from("openapi/NotificationsResource_get.yml")
    def get(self):
        """
        Get notifications
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
        notifications = user_service.get_last_notifications(
            after=after,
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


class NotificationResource(MethodView, ArgsMixin):

    @swag_from("openapi/NotificationResource_get.yml")
    def get(self, notification_id):
        """
        Get notification
        """
        return user_service.get_notification(notification_id)

    @swag_from("openapi/NotificationResource_put.yml")
    def put(self, notification_id):
        """
        Update notification
        """
        body = validation.validate_request_body(NotificationUpdateSchema)
        return user_service.update_notification(notification_id, body.read)


class MarkAllNotificationsAsReadResource(MethodView):

    @swag_from("openapi/MarkAllNotificationsAsReadResource_post.yml")
    def post(self):
        """
        Mark all notifications as read
        """
        user_service.mark_notifications_as_read()
        return {"success": True}


class HasTaskSubscribedResource(MethodView):

    @swag_from("openapi/HasTaskSubscribedResource_get.yml")
    def get(self, task_id):
        """
        Check task subscription
        """
        return jsonify(user_service.has_task_subscription(task_id))


class TaskSubscribeResource(MethodView):

    @swag_from("openapi/TaskSubscribeResource_post.yml")
    def post(self, task_id):
        """
        Subscribe to task
        """
        return user_service.subscribe_to_task(task_id), 201


class TaskUnsubscribeResource(MethodView):

    @swag_from("openapi/TaskUnsubscribeResource_delete.yml")
    def delete(self, task_id):
        """
        Unsubscribe from task
        """
        user_service.unsubscribe_from_task(task_id)
        return "", 204


class TasksSubscribeResource(MethodView):

    @swag_from("openapi/TasksSubscribeResource_post.yml")
    def post(self):
        """
        Subscribe to several tasks
        """
        body = validation.validate_request_body(SubscribeTasksSchema)
        return [
            user_service.subscribe_to_task(task_id)
            for task_id in body.task_ids
        ], 201


class TasksUnsubscribeResource(MethodView):

    @swag_from("openapi/TasksUnsubscribeResource_post.yml")
    def post(self):
        """
        Unsubscribe from several tasks
        """
        body = validation.validate_request_body(SubscribeTasksSchema)
        for task_id in body.task_ids:
            user_service.unsubscribe_from_task(task_id)
        return body.task_ids, 200


class HasSequenceSubscribedResource(MethodView):

    @swag_from("openapi/HasSequenceSubscribedResource_get.yml")
    def get(self, sequence_id, task_type_id):
        """
        Check sequence subscription
        """
        return jsonify(
            user_service.has_sequence_subscription(sequence_id, task_type_id)
        )


class SequenceSubscribeResource(MethodView):

    @swag_from("openapi/SequenceSubscribeResource_post.yml")
    def post(self, sequence_id, task_type_id):
        """
        Subscribe to sequence
        """
        subscription = user_service.subscribe_to_sequence(
            sequence_id, task_type_id
        )
        return subscription, 201


class SequenceUnsubscribeResource(MethodView):

    @swag_from("openapi/SequenceUnsubscribeResource_delete.yml")
    def delete(self, sequence_id, task_type_id):
        """
        Unsubscribe from sequence
        """
        user_service.unsubscribe_from_sequence(sequence_id, task_type_id)
        return "", 204


class SequenceSubscriptionsResource(MethodView):

    @swag_from("openapi/SequenceSubscriptionsResource_get.yml")
    def get(self, project_id, task_type_id):
        """
        Get sequence subscriptions
        """
        return user_service.get_sequence_subscriptions(
            project_id, task_type_id
        )


class TimeSpentsResource(MethodView, ArgsMixin):
    """
    Get all time spents for the current user.
    Optionnaly can accept date range parameters.
    """

    @swag_from("openapi/TimeSpentsResource_get.yml")
    def get(self):
        """
        Get time spents
        """
        arguments = self.get_args(["start_date", "end_date"])
        start_date, end_date = arguments["start_date"], arguments["end_date"]
        current_user = persons_service.get_current_user()
        if not start_date and not end_date:
            return time_spents_service.get_time_spents(current_user["id"])

        if None in [start_date, end_date]:
            raise WrongParameterException(
                "If querying for a range of dates, both a `start_date` and"
                " an `end_date` must be given."
            )

        try:
            return time_spents_service.get_time_spents_range(
                current_user["id"], start_date, end_date
            )
        except WrongDateFormatException:
            raise WrongParameterException(
                f"Wrong date format for {start_date} and/or {end_date}"
            )


class DateTimeSpentsResource(MethodView):

    @swag_from("openapi/DateTimeSpentsResource_get.yml")
    def get(self, date):
        """
        Get time spents by date
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spents(
                current_user["id"], date
            )
        except WrongDateFormatException:
            raise WrongParameterException("Wrong date format.")


class TaskTimeSpentResource(MethodView):

    @swag_from("openapi/TaskTimeSpentResource_get.yml")
    def get(self, task_id, date):
        """
        Get task time spent
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_time_spent(
                current_user["id"], task_id, date
            )
        except WrongDateFormatException:
            raise WrongParameterException("Wrong date format.")


class DayOffResource(MethodView):

    @swag_from("openapi/DayOffResource_get.yml")
    def get(self, date):
        """
        Get day off
        """
        try:
            current_user = persons_service.get_current_user()
            return time_spents_service.get_day_off(current_user["id"], date)
        except WrongDateFormatException:
            raise WrongParameterException("Wrong date format.")


class ContextResource(MethodView):

    @swag_from("openapi/ContextResource_get.yml")
    def get(self):
        """
        Get context
        """
        return user_service.get_context()


class ClearAvatarResource(MethodView):

    @swag_from("openapi/ClearAvatarResource_delete.yml")
    def delete(self):
        """
        Clear avatar
        """
        user = persons_service.get_current_user()
        persons_service.clear_avatar(user["id"])
        return "", 204


class ChatsResource(MethodView):

    @swag_from("openapi/ChatsResource_get.yml")
    def get(self):
        """
        Get chats
        """
        user = persons_service.get_current_user()
        return chats_service.get_chats_for_person(user["id"])


class JoinChatResource(MethodView):

    @swag_from("openapi/JoinChatResource_post.yml")
    def post(self, entity_id):
        """
        Join chat
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])
        person = persons_service.get_current_user()
        return chats_service.join_chat(entity_id, person["id"])

    @swag_from("openapi/JoinChatResource_delete.yml")
    def delete(self, entity_id):
        """
        Leave chat
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])
        person = persons_service.get_current_user()
        chats_service.leave_chat(entity_id, person["id"])
        return "", 204
