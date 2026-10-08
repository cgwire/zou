from flasgger import swag_from
from flask import request, current_app
from flask_jwt_extended import jwt_required

from sqlalchemy.orm import aliased
from sqlalchemy.exc import IntegrityError

from zou.app.mixin import ArgsMixin
from zou.app.models.entity import Entity
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.task import Task

from zou.app.services import (
    permissions_service,
    user_service,
    tasks_service,
    deletion_service,
    entities_service,
    notifications_service,
    persons_service,
    entity_types_service,
    task_types_service,
)
from zou.app.utils import events, fields, permissions

from zou.app.exceptions import (
    WrongParameterException,
    WrongTaskTypeForEntityException,
)

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource


class TasksResource(BaseModelsResource, ArgsMixin):
    def __init__(self):
        BaseModelsResource.__init__(self, Task)

    def get_relations_eager_load(self):
        """
        Batch-load assignees when the client asks for relations. Replaces
        the previous lazy="selectin" default on Task.assignees so that Task
        loads that don't need assignees (~70-80% of them) pay nothing.
        """
        return [Task.assignees]

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from("openapi/TasksResource_get.yml")
    def get(self):
        """
        Get tasks
        """
        return super().get()

    def add_project_permission_filter(self, query):
        if permissions.has_vendor_permissions():
            query = query.filter(persons_service.build_assignee_filter())
        elif not permissions.has_admin_permissions():
            query = query.join(Project).filter(
                user_service.build_related_projects_filter()
            )
        return query

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
            # Bound as a raw value into the join below: the driver would
            # reject a malformed id on execution, as a 500.
            if not fields.is_valid_id(episode_id):
                raise WrongParameterException(
                    f"Invalid UUID format for episode_id: {episode_id}"
                )
            Sequence = aliased(Entity)
            query = (
                query.join(Entity, Task.entity_id == Entity.id)
                .join(Sequence, Entity.parent_id == Sequence.id)
                .filter(Sequence.parent_id == episode_id)
            )

        return query

    @jwt_required()
    @swag_from("openapi/TasksResource_post.yml")
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
            # task.name is NOT NULL; default it like create_task() does so a
            # client omitting it gets a task instead of an IntegrityError.
            data["name"] = data.get("name") or "main"
            is_assignees = "assignees" in data
            assignees = None
            if is_assignees and not isinstance(data["assignees"], list):
                raise WrongParameterException("assignees must be a list.")

            task_type = task_types_service.get_task_type(data["task_type_id"])
            entity = entities_service.get_entity(data["entity_id"])
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
                persons = Person.query.filter(Person.id.in_(assignees)).all()
                del data["assignees"]

            instance = self.model(**data)
            if assignees is not None:
                instance.assignees = persons
            instance.save()
            self.emit_create_event(instance.serialize())

            return (
                tasks_service.get_task(str(instance.id), relations=True),
                201,
            )

        except TypeError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": "Task already exists."}, 400


class TaskResource(BaseModelResource, ArgsMixin):
    def __init__(self):
        BaseModelResource.__init__(self, Task)

    def check_read_permissions(self, task):
        permissions_service.check_project_access(task["project_id"])
        permissions_service.check_entity_access(task["entity_id"])

    @jwt_required()
    @swag_from("openapi/TaskResource_get.yml")
    def get(self, instance_id):
        """
        Get task
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/TaskResource_put.yml")
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
            self._previous_assignees = {
                str(person.id) for person in self.instance.assignees
            }
        # Metadata values pile up in the JSONB bag: merge the incoming
        # dict instead of replacing the whole field, like entities do.
        if data.get("data"):
            data["data"] = {**(self.instance.data or {}), **data["data"]}
        return instance_dict

    def post_update(self, instance_dict, data):
        tasks_service.clear_task_cache(instance_dict["id"])
        # Assignees set through the generic update emit the same events and
        # assignation notifications as the assign/clear-assignation routes
        # so that listeners and assignees stay in sync.
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
    @swag_from("openapi/TaskResource_delete.yml")
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
            return {"message": str(exception)}, 400

        return "", 204
