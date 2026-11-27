from flask import current_app, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.blueprints.crud.base import (
    UNIQUE_VIOLATION_MESSAGE,
    BaseModelResource,
    BaseModelsResource,
    build_db_error_message,
)
from zou.app.exceptions import (
    WrongParameterException,
    WrongTaskTypeForEntityException,
)
from zou.app.mixin import ArgsMixin
from zou.app.models.task import Task
from zou.app.services import (
    deletion_service,
    entities_service,
    entity_types_service,
    notifications_service,
    permissions_service,
    persons_service,
    task_types_service,
    tasks_service,
    user_service,
)
from zou.app.utils import events, fields, permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/task.yml")


class TasksResource(BaseModelsResource, ArgsMixin):
    def __init__(self):
        BaseModelsResource.__init__(self, Task)

    def get_relations_eager_load(self):
        """
        Load the assignees in batch when the client asks for relations.
        By default, Task.assignees does not use selectin. Thus the Task loads
        that do not need assignees (about 70-80% of them) cost nothing.
        """
        return [Task.assignees]

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from(SPECS["TasksResource_get"])
    def get(self):
        """
        Get tasks
        """
        return super().get()

    def add_project_permission_filter(self, query):
        if not permissions.has_admin_permissions():
            # Each task uses the role of the user on its project.
            query = tasks_service.filter_tasks_by_projects(
                query,
                user_service.build_related_projects_filter(),
                user_service.get_project_ids_with_roles("vendor"),
            )
        return query

    def serialize_list(self, entries, relations=False):
        tasks = super().serialize_list(entries, relations=relations)
        client_project_ids = set(
            user_service.get_project_ids_with_roles("client")
        )
        if not client_project_ids:
            return tasks
        return [
            (
                entities_service.blank_task_for_client(task)
                if task["project_id"] in client_project_ids
                else task
            )
            for task in tasks
        ]

    def build_filters(self, options):
        (
            many_join_filter,
            in_filter,
            name_filter,
            criterions,
        ) = super().build_filters(options)
        if "episode_id" in criterions:
            del criterions["episode_id"]
        return (
            many_join_filter,
            in_filter,
            name_filter,
            criterions,
        )

    def apply_filters(self, query, options):
        query = super().apply_filters(query, options)

        episode_id = options.get("episode_id", None)
        if episode_id is not None:
            # The join below uses this raw value. On execution, the driver
            # would reject a malformed ID with a generic message.
            if not fields.is_valid_id(episode_id):
                raise WrongParameterException(
                    f"Invalid UUID format for episode_id: {episode_id}"
                )
            query = tasks_service.filter_tasks_by_episode(query, episode_id)

        return query

    @jwt_required()
    @swag_from(SPECS["TasksResource_post"])
    def post(self):
        """
        Create task
        """
        try:
            data = request.json
            if not isinstance(data, dict):
                raise WrongParameterException("A JSON object is expected.")
            for key in ("task_type_id", "entity_id"):
                if not fields.is_valid_id(data.get(key)):
                    raise WrongParameterException(
                        f"A valid {key} is required."
                    )
            # task.name is NOT NULL. Give it a default value, as create_task()
            # does. Thus, if a client does not send it, the client gets a task,
            # not an IntegrityError.
            data["name"] = data.get("name") or "main"
            is_assignees = "assignees" in data
            assignees = None
            if is_assignees and (
                not isinstance(data["assignees"], list)
                or not all(map(fields.is_valid_id, data["assignees"]))
            ):
                raise WrongParameterException(
                    "assignees must be a list of person IDs."
                )

            task_type = task_types_service.get_task_type(data["task_type_id"])
            entity = entities_service.get_entity(data["entity_id"])
            permissions_service.check_manager_project_access(
                entity["project_id"]
            )
            # Do not trust the project_id of the body: the task uses the
            # project of its entity.
            data["project_id"] = entity["project_id"]
            if task_type["for_entity"] == "Asset":
                if not entity_types_service.is_asset_dict(entity):
                    raise WrongTaskTypeForEntityException(
                        "Task type of the task does not match entity type."
                    )
            elif (
                entity_types_service.get_temporal_entity_type_by_name(
                    task_type["for_entity"]
                )["id"]
                != entity["entity_type_id"]
            ):
                raise WrongTaskTypeForEntityException(
                    "Task type of the task does not match entity type."
                )

            if is_assignees:
                assignees = data["assignees"]
                tasks_service.check_no_preview_assignee(assignees)
                del data["assignees"]

            instance = tasks_service.create_task_raw_from_data(data, assignees)
            self.emit_create_event(instance.serialize())

            return (
                tasks_service.get_task(str(instance.id), relations=True),
                201,
            )

        except TypeError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except (IntegrityError, StatementError) as exception:
            current_app.logger.error(str(exception), exc_info=1)
            message = build_db_error_message(exception)
            if message == UNIQUE_VIOLATION_MESSAGE:
                message = "Task already exists."
            return {"message": message}, 400


class TaskResource(BaseModelResource, ArgsMixin):
    def __init__(self):
        BaseModelResource.__init__(self, Task)

    def check_read_permissions(self, task):
        permissions_service.check_project_access(task["project_id"])
        permissions_service.check_entity_access(task["entity_id"])

    def clean_get_result(self, task):
        # This runs after the read check found the role on the project.
        if permissions.has_client_permissions():
            return entities_service.blank_task_for_client(task)
        return task

    @jwt_required()
    @swag_from(SPECS["TaskResource_get"])
    def get(self, instance_id):
        """
        Get task
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["TaskResource_put"])
    def put(self, instance_id):
        """
        Update task
        """
        return super().put(instance_id)

    def check_update_permissions(self, task, data):
        permissions_service.check_supervisor_task_access(task, data)

    def check_delete_permissions(self, task):
        permissions_service.check_manager_project_access(task["project_id"])

    def pre_update(self, instance_dict, data):
        if "assignees" in data:
            tasks_service.check_no_preview_assignee(data["assignees"])
            self._previous_assignees = {
                str(person.id) for person in self.instance.assignees
            }
        # Metadata values accumulate in the JSONB field. Merge the incoming
        # dict, as entities do. Do not replace the full field.
        if data.get("data"):
            data["data"] = {**(self.instance.data or {}), **data["data"]}
        return instance_dict

    def post_update(self, instance_dict, data):
        tasks_service.clear_task_cache(instance_dict["id"])
        # If the generic update sets assignees, it emits the same events and
        # assignation notifications as the assign/clear-assignation routes.
        # Thus listeners and assignees stay in sync.
        if "assignees" in data:
            new_assignees = {
                str(person.id) for person in self.instance.assignees
            }
            previous_assignees = getattr(self, "_previous_assignees", set())
            project_id = instance_dict["project_id"]
            current_user_id = persons_service.get_current_user()["id"]
            for person_id in new_assignees - previous_assignees:
                events.emit(
                    "task:assign",
                    {"task_id": instance_dict["id"], "person_id": person_id},
                    project_id=project_id,
                )
                notifications_service.create_assignation_notification(
                    instance_dict["id"], person_id, current_user_id
                )
            for person_id in previous_assignees - new_assignees:
                events.emit(
                    "task:unassign",
                    {"task_id": instance_dict["id"], "person_id": person_id},
                    project_id=project_id,
                )
        return instance_dict

    @jwt_required()
    @swag_from(SPECS["TaskResource_delete"])
    def delete(self, instance_id):
        """
        Delete task
        """
        force = self.get_force()

        instance = self.get_model_or_404(instance_id)

        try:
            instance_dict = instance.serialize()
            self.check_delete_permissions(instance_dict)
            deletion_service.remove_task(instance_id, force=force)
            tasks_service.clear_task_cache(instance_id)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": build_db_error_message(exception)}, 400

        return "", 204
