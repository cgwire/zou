from flasgger import swag_from
import datetime


from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.exceptions import (
    CommentNotFoundException,
    TaskNotFoundException,
    PersonNotFoundException,
    MalformedFileTreeException,
    WrongDateFormatException,
    WrongParameterException,
)
from zou.app.services import (
    assets_service,
    deletion_service,
    edits_service,
    entities_service,
    files_service,
    file_tree_service,
    notifications_service,
    persons_service,
    preview_files_service,
    projects_service,
    shots_service,
    tasks_service,
    permissions_service,
    user_service,
    concepts_service,
    entity_types_service,
    subscriptions_service,
    task_types_service,
    comments_service,
    schedule_service,
    time_spents_service,
    todos_service,
)
from zou.app.utils import (
    events,
    http_cache,
    query,
    permissions,
    date_helpers,
    validation,
    fields,
)
from zou.app.mixin import ArgsMixin
from zou.app.blueprints.tasks.schemas import (
    CommentPreviewSchema,
    SetTasksMainPreviewSchema,
    SetTasksPrioritySchema,
    ToReviewSchema,
    UnassignTasksSchema,
    AssignTasksSchema,
    AssignPersonSchema,
    TimeSpentSchema,
)


class AddPreviewResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/AddPreviewResource_post.yml")
    def post(self, task_id, comment_id):
        """
        Add task preview
        """
        body = validation.validate_request_body(CommentPreviewSchema)

        permissions_service.check_task_action_access(task_id)

        person = persons_service.get_current_user()
        preview_file = comments_service.add_preview_file_to_comment(
            comment_id, person["id"], task_id, body.revision
        )
        return preview_file, 201


class AddExtraPreviewResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/AddExtraPreviewResource_post.yml")
    def post(self, task_id, comment_id, preview_file_id):
        """
        Add preview to comment
        """
        permissions_service.check_task_action_access(task_id)
        comments_service.get_comment(comment_id)

        person = persons_service.get_current_user()
        related_preview_file = files_service.get_preview_file(preview_file_id)

        preview_file = comments_service.add_preview_file_to_comment(
            comment_id, person["id"], task_id, related_preview_file["revision"]
        )
        return preview_file, 201

    @jwt_required()
    @swag_from("openapi/AddExtraPreviewResource_delete.yml")
    def delete(self, task_id, comment_id, preview_file_id):
        """
        Delete preview from comment
        """
        self.check_id_parameter(task_id)
        self.check_id_parameter(comment_id)
        self.check_id_parameter(preview_file_id)
        task = tasks_service.get_task(task_id)
        permissions_service.check_project_access(task["project_id"])
        deletion_service.remove_preview_file_by_id(
            preview_file_id, force=self.get_force()
        )
        return "", 204


class TaskPreviewsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/TaskPreviewsResource_get.yml")
    def get(self, task_id):
        """
        Get task previews
        """
        permissions_service.check_task_access(task_id)
        return files_service.get_preview_files_for_task(task_id)


class TaskCommentsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/TaskCommentsResource_get.yml")
    def get(self, task_id):
        """
        Get task comments
        """
        permissions_service.check_task_access(task_id)
        is_client = permissions.has_client_permissions()
        is_manager = permissions.has_manager_permissions()
        is_supervisor = permissions.has_supervisor_permissions()
        return comments_service.get_comments(
            task_id, is_client, is_manager or is_supervisor
        )


class TaskCommentResource(MethodView):

    @jwt_required()
    @swag_from("openapi/TaskCommentResource_get.yml")
    def get(self, task_id, comment_id):
        """
        Get comment
        """
        comment = comments_service.get_comment(comment_id)
        if comment["object_id"] != task_id:
            raise CommentNotFoundException
        permissions_service.check_comment_access(
            comment["id"], comment=comment
        )
        return comment

    def pre_delete(self, comment):
        task = tasks_service.get_task(comment["object_id"])
        self.previous_task_status_id = task["task_status_id"]
        return comment

    def post_delete(self, comment):
        task = tasks_service.get_task(comment["object_id"])
        self.new_task_status_id = task["task_status_id"]
        if self.previous_task_status_id != self.new_task_status_id:
            events.emit(
                "task:status-changed",
                {
                    "task_id": task["id"],
                    "new_task_status_id": self.new_task_status_id,
                    "previous_task_status_id": self.previous_task_status_id,
                    "person_id": comment["person_id"],
                },
                project_id=task["project_id"],
            )
        return comment

    @jwt_required()
    @swag_from("openapi/TaskCommentResource_delete.yml")
    def delete(self, task_id, comment_id):
        """
        Delete comment
        """
        comment = comments_service.get_comment(comment_id)
        task = tasks_service.get_task(comment["object_id"])
        permissions_service.resolve_project_role(task["project_id"])
        if permissions.has_manager_permissions():
            permissions_service.check_project_access(task["project_id"])
        else:
            permissions_service.check_person_access(comment["person_id"])
        self.pre_delete(comment)
        deletion_service.remove_comment(comment_id)
        tasks_service.reset_task_data(comment["object_id"])
        comments_service.clear_comment_cache(comment_id)
        self.post_delete(comment)
        return "", 204


class PersonTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/PersonTasksResource_get.yml")
    def get(self, person_id):
        """
        Get person open tasks
        """
        permissions_service.check_person_is_not_bot(person_id)
        current_user = persons_service.get_current_user()
        if (
            person_id != current_user["id"]
            and permissions.has_vendor_permissions()
        ):
            raise permissions.PermissionDenied
        if not permissions.has_admin_permissions():
            projects = user_service.related_projects()
        else:
            projects = projects_service.open_projects()
        if permissions.has_vendor_permissions():
            person = persons_service.get_person(person_id)
            if person["role"] == "vendor":
                return []
        elif permissions.has_client_permissions():
            return []
        return todos_service.get_person_tasks(person_id, projects)


class PersonRelatedTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/PersonRelatedTasksResource_get.yml")
    def get(self, person_id, task_type_id):
        """
        Get person tasks for type
        """
        permissions_service.check_person_is_not_bot(person_id)
        current_user = persons_service.get_current_user()
        if (
            person_id != current_user["id"]
            and permissions.has_vendor_permissions()
        ):
            raise permissions.PermissionDenied
        return todos_service.get_person_related_tasks(person_id, task_type_id)


class PersonDoneTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/PersonDoneTasksResource_get.yml")
    def get(self, person_id):
        """
        Get person done tasks
        """
        permissions_service.check_person_is_not_bot(person_id)
        current_user = persons_service.get_current_user()
        if (
            person_id != current_user["id"]
            and permissions.has_vendor_permissions()
        ):
            raise permissions.PermissionDenied
        if not permissions.has_admin_permissions():
            projects = user_service.related_projects()
        else:
            projects = projects_service.open_projects()
        if permissions.has_vendor_permissions():
            person = persons_service.get_person(person_id)
            if person["role"] == "vendor":
                return []
        elif permissions.has_client_permissions():
            return []
        return todos_service.get_person_done_tasks(person_id, projects)


class CreateShotTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/CreateShotTasksResource_post.yml")
    def post(self, project_id, task_type_id):
        """
        Create shot tasks
        """
        permissions_service.check_manager_project_access(project_id)
        task_type = task_types_service.get_task_type(task_type_id)

        shot_ids = validation.validate_id_list(required=False)
        shots = []
        if isinstance(shot_ids, list) and len(shot_ids) > 0:
            for shot_id in shot_ids:
                shot = shots_service.get_shot(shot_id)
                if shot["project_id"] == project_id:
                    shots.append(shot)
        else:
            criterions = query.get_query_criterions_from_request(request)
            criterions["project_id"] = project_id
            shots = shots_service.get_shots(criterions)

        tasks = tasks_service.create_tasks(task_type, shots)
        return tasks, 201


class CreateConceptTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/CreateConceptTasksResource_post.yml")
    def post(self, project_id, task_type_id):
        """
        Create concept tasks
        """
        permissions_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        task_type = task_types_service.get_task_type(task_type_id)

        concept_ids = validation.validate_id_list(required=False)
        concepts = []
        if isinstance(concept_ids, list) and len(concept_ids) > 0:
            for concept_id in concept_ids:
                concept = concepts_service.get_concept(concept_id)
                if concept["project_id"] == project_id:
                    concepts.append(concept)
        else:
            criterions = query.get_query_criterions_from_request(request)
            criterions["project_id"] = project_id
            concepts = concepts_service.get_concepts(criterions)

        for concept in concepts:
            permissions_service.check_entity_access(concept["id"])

        tasks = tasks_service.create_tasks(task_type, concepts)
        return tasks, 201


class CreateEntityTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/CreateEntityTasksResource_post.yml")
    def post(self, project_id, entity_type, task_type_id):
        """
        Create entity tasks
        """
        permissions_service.check_manager_project_access(project_id)
        task_type = task_types_service.get_task_type(task_type_id)
        entity_type_dict = (
            entity_types_service.get_entity_type_by_name_or_not_found(
                entity_type.capitalize()
            )
        )

        entity_ids = validation.validate_id_list(required=False)
        entities = []
        if isinstance(entity_ids, list) and len(entity_ids) > 0:
            for entity_id in entity_ids:
                entity = entities_service.get_entity(entity_id)
                if entity["project_id"] == project_id:
                    entities.append(entity)
        else:
            criterions = query.get_query_criterions_from_request(request)
            episode_id = criterions.get("episode_id", None)
            entities = entities_service.get_entities_for_project(
                project_id, entity_type_dict["id"], episode_id=episode_id
            )

        tasks = tasks_service.create_tasks(task_type, entities)
        return tasks, 201


class CreateAssetTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/CreateAssetTasksResource_post.yml")
    def post(self, project_id, task_type_id):
        """
        Create asset tasks
        """
        permissions_service.check_manager_project_access(project_id)
        task_type = task_types_service.get_task_type(task_type_id)

        asset_ids = validation.validate_id_list(required=False)
        assets = []
        if isinstance(asset_ids, list) and len(asset_ids) > 0:
            for asset_id in asset_ids:
                asset = assets_service.get_asset(asset_id)
                if asset["project_id"] == project_id:
                    assets.append(asset)
        else:
            criterions = query.get_query_criterions_from_request(request)
            criterions["project_id"] = project_id
            assets = assets_service.get_assets(criterions)

        tasks = tasks_service.create_tasks(task_type, assets)
        return tasks, 201


class CreateEditTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/CreateEditTasksResource_post.yml")
    def post(self, project_id, task_type_id):
        """
        Create edit tasks
        """
        permissions_service.check_manager_project_access(project_id)
        task_type = task_types_service.get_task_type(task_type_id)

        edit_ids = validation.validate_id_list(required=False)
        edits = []
        if isinstance(edit_ids, list) and len(edit_ids) > 0:
            for edit_id in edit_ids:
                edit = edits_service.get_edit(edit_id)
                if edit["project_id"] == project_id:
                    edits.append(edit)
        else:
            criterions = query.get_query_criterions_from_request(request)
            criterions["project_id"] = project_id
            edits = edits_service.get_edits(criterions)

        tasks = tasks_service.create_tasks(task_type, edits)
        return tasks, 201


class ToReviewResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ToReviewResource_put.yml")
    def put(self, task_id):
        """
        Set task to review
        """
        body = validation.validate_request_body(ToReviewSchema)
        person_id = body.person_id
        comment = body.comment
        name = body.name
        revision = body.revision
        change_status = body.change_status

        try:
            task = tasks_service.get_task(task_id)
            permissions_service.check_project_access(task["project_id"])
            permissions_service.check_entity_access(task["entity_id"])

            if person_id is not None:
                person = persons_service.get_person(person_id)
            else:
                person = persons_service.get_current_user()

            preview_path = self.get_preview_path(task, name, revision)

            task = tasks_service.task_to_review(
                task_id, person, comment, preview_path, change_status
            )
        except PersonNotFoundException:
            return {"error": True, "message": "Cannot find given person."}, 400

        return task

    def get_preview_path(self, task, name, revision):
        try:
            folder_path = file_tree_service.get_working_folder_path(
                task, name=name, mode="preview", revision=revision
            )
            file_name = file_tree_service.get_working_file_name(
                task, name=name, mode="preview", revision=revision
            )
        except MalformedFileTreeException:  # No template for preview files.
            return {"folder_path": "", "file_name": ""}

        return {"folder_path": folder_path, "file_name": file_name}


class ClearAssignationResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ClearAssignationResource_put.yml")
    def put(self):
        """
        Clear task assignations
        """
        body = validation.validate_request_body(UnassignTasksSchema)

        tasks = []
        for task_id in body.task_ids:
            try:
                permissions_service.check_task_department_access_for_unassign(
                    task_id, body.person_id
                )
                tasks_service.clear_assignation(
                    task_id, person_id=body.person_id
                )
                tasks.append(task_id)
            except permissions.PermissionDenied:
                pass
            except TaskNotFoundException:
                pass

        return tasks


class SetTasksPriorityResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/SetTasksPriorityResource_put.yml")
    def put(self):
        """
        Set tasks priority
        """
        body = validation.validate_request_body(SetTasksPrioritySchema)

        data = {"priority": body.priority}
        tasks = []
        for task_id in body.task_ids:
            try:
                task = tasks_service.get_task(task_id)
                permissions_service.check_supervisor_task_access(task, data)
                tasks.append(tasks_service.update_task(task_id, dict(data)))
            except permissions.PermissionDenied:
                pass
            except TaskNotFoundException:
                pass

        return tasks


class TasksAssignResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/TasksAssignResource_put.yml")
    def put(self, person_id):
        """
        Assign tasks to person
        """
        body = validation.validate_request_body(AssignTasksSchema)

        tasks = []
        current_user = persons_service.get_current_user()
        for task_id in body.task_ids:
            try:
                project_id = tasks_service.get_task(task_id)["project_id"]
                permissions_service.check_person_is_not_bot(
                    person_id, project_id
                )
                permissions_service.check_task_department_access(
                    task_id, person_id
                )
                task = tasks_service.assign_task(
                    task_id, person_id, current_user["id"]
                )
                notifications_service.create_assignation_notification(
                    task_id, person_id
                )
                tasks.append(task)
            except TaskNotFoundException:
                pass
            except permissions.PermissionDenied:
                pass
            except PersonNotFoundException:
                return {"error": "Assignee doesn't exist in database."}, 400
        if len(tasks) > 0:
            projects_service.add_team_member(tasks[0]["project_id"], person_id)

        return tasks


class TaskAssignResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/TaskAssignResource_put.yml")
    def put(self, task_id):
        """
        Assign task to person
        """
        body = validation.validate_request_body(AssignPersonSchema)
        person_id = body.person_id
        current_user = persons_service.get_current_user()
        try:
            project_id = tasks_service.get_task(task_id)["project_id"]
            permissions_service.check_person_is_not_bot(person_id, project_id)
            permissions_service.check_task_department_access(
                task_id, person_id
            )
            task = tasks_service.assign_task(
                task_id, person_id, current_user["id"]
            )
            notifications_service.create_assignation_notification(
                task_id, person_id
            )
            projects_service.add_team_member(task["project_id"], person_id)
        except PersonNotFoundException:
            return {"error": "Assignee doesn't exist in database."}, 400

        return task


class TaskFullResource(MethodView):

    @jwt_required()
    @swag_from("openapi/TaskFullResource_get.yml")
    def get(self, task_id):
        """
        Get task full
        """
        task = tasks_service.get_full_task(
            task_id, persons_service.get_current_user()["id"]
        )
        permissions_service.check_project_access(task["project_id"])
        permissions_service.check_entity_access(task["entity_id"])
        return task


class TaskForEntityResource(MethodView):

    @jwt_required()
    @swag_from("openapi/TaskForEntityResource_get.yml")
    def get(self, entity_id, task_type_id):
        """
        Get tasks for entity and type
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        return tasks_service.get_tasks_for_entity_and_task_type(
            entity_id, task_type_id
        )


class SetTimeSpentResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/SetTimeSpentResource_post.yml")
    def post(self, task_id, date, person_id):
        """
        Set time spent
        """
        project_id = tasks_service.get_task(task_id)["project_id"]
        permissions_service.check_person_is_not_bot(person_id, project_id)
        body = validation.validate_request_body(TimeSpentSchema)
        try:
            permissions_service.check_time_spent_access(task_id, person_id)
            time_spent = time_spents_service.create_or_update_time_spent(
                task_id,
                person_id,
                date_helpers.get_date_from_string(date),
                body.duration,
            )
            return time_spent, 201
        except ValueError:
            raise WrongParameterException("Invalid date format.")
        except WrongDateFormatException:
            raise WrongParameterException("Wrong date format.")

    @jwt_required()
    @swag_from("openapi/SetTimeSpentResource_delete.yml")
    def delete(self, task_id, date, person_id):
        """
        Delete time spent
        """
        permissions_service.check_person_is_not_bot(person_id)
        try:
            permissions_service.check_time_spent_access(task_id, person_id)
            time_spent = time_spents_service.delete_time_spent(
                task_id,
                person_id,
                datetime.datetime.strptime(date, "%Y-%m-%d"),
            )
            return time_spent, 201
        except ValueError:
            raise WrongParameterException("Invalid date format.")
        except WrongDateFormatException:
            raise WrongParameterException("Wrong date format.")


class AddTimeSpentResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/AddTimeSpentResource_post.yml")
    def post(self, task_id, date, person_id):
        """
        Add time spent
        """
        project_id = tasks_service.get_task(task_id)["project_id"]
        permissions_service.check_person_is_not_bot(person_id, project_id)
        body = validation.validate_request_body(TimeSpentSchema)
        try:
            permissions_service.check_time_spent_access(task_id, person_id)
            time_spent = time_spents_service.create_or_update_time_spent(
                task_id,
                person_id,
                date_helpers.get_date_from_string(date),
                body.duration,
                add=True,
            )
            return time_spent, 201
        except ValueError:
            raise WrongParameterException("Invalid date format.")
        except WrongDateFormatException:
            raise WrongParameterException("Wrong date format.")


class GetTimeSpentResource(MethodView):

    @jwt_required()
    @swag_from("openapi/GetTimeSpentResource_get.yml")
    def get(self, task_id):
        """
        Get task time spent
        """
        permissions_service.check_task_access(task_id)
        return time_spents_service.get_time_spents_for_task(task_id)


class GetTimeSpentDateResource(MethodView):

    @jwt_required()
    @swag_from("openapi/GetTimeSpentDateResource_get.yml")
    def get(self, task_id, date):
        """
        Get task time spent for date
        """
        try:
            permissions_service.check_task_access(task_id)
            return time_spents_service.get_time_spents_for_task(task_id, date)
        except WrongDateFormatException:
            raise WrongParameterException("Wrong date format.")


class DeleteAllTasksForTaskTypeResource(MethodView):

    @jwt_required()
    @swag_from("openapi/DeleteAllTasksForTaskTypeResource_delete.yml")
    def delete(self, project_id, task_type_id):
        """
        Delete tasks for type
        """
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        task_ids = deletion_service.remove_tasks_for_project_and_task_type(
            project_id, task_type_id
        )
        for task_id in task_ids:
            tasks_service.clear_task_cache(task_id)
        return "", 204


class DeleteTasksResource(MethodView):

    @jwt_required()
    @swag_from("openapi/DeleteTasksResource_post.yml")
    def post(self, project_id):
        """
        Delete tasks batch
        """
        permissions_service.check_manager_project_access(project_id)
        task_ids = validation.validate_id_list()
        task_ids = deletion_service.remove_tasks(project_id, task_ids)
        for task_id in task_ids:
            tasks_service.clear_task_cache(task_id)
        return task_ids, 200


class ProjectSubscriptionsResource(MethodView):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/ProjectSubscriptionsResource_get.yml")
    def get(self, project_id):
        """
        Get project subscriptions
        """
        projects_service.get_project(project_id)
        return subscriptions_service.get_subscriptions_for_project(project_id)


class ProjectNotificationsResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/ProjectNotificationsResource_get.yml")
    def get(self, project_id):
        """
        Get project notifications
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        return notifications_service.get_notifications_for_project(
            project_id, page
        )


class ProjectTasksResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProjectTasksResource_get.yml")
    def get(self, project_id):
        """
        Get project tasks
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        # The validator hashes everything that shapes the response: the
        # tasks freshness signal, plus the caller and its effective role
        # so a role change or an account switch on the same browser
        # never validates a payload shaped for someone else.
        current_user = persons_service.get_current_user()
        etag = http_cache.build_etag(
            tasks_service.get_project_tasks_fingerprint(project_id),
            current_user["id"],
            permissions.get_effective_role(),
        )
        if http_cache.is_fresh(etag):
            return http_cache.not_modified(etag)
        page = self.get_page()
        task_type_id = self.get_task_type_id()
        episode_id = self.get_episode_id()
        return http_cache.json_response(
            todos_service.get_tasks_for_project(
                project_id,
                page,
                task_type_id=task_type_id,
                episode_id=episode_id,
            ),
            etag,
        )


class ProjectCommentsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProjectCommentsResource_get.yml")
    def get(self, project_id):
        """
        Get project comments
        """
        projects_service.get_project(project_id)
        permissions_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        page = self.get_page()
        limit = self.get_limit()
        return comments_service.get_comments_for_project(
            project_id, page, limit
        )


class ProjectPreviewFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/ProjectPreviewFilesResource_get.yml")
    def get(self, project_id):
        """
        Get project preview files
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        return files_service.get_preview_files_for_project(project_id, page)


class SetTaskMainPreviewResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SetTaskMainPreviewResource_put.yml")
    def put(self, task_id):
        """
        Set main preview from task
        """
        task = tasks_service.get_task(task_id)
        permissions_service.check_project_access(task["project_id"])
        permissions_service.check_entity_access(task["entity_id"])
        # Clients review content but must not redefine how an entity is
        # illustrated.
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        preview_file = preview_files_service.get_last_preview_file_for_task(
            task_id
        )
        if preview_file is None:
            raise WrongParameterException(
                "This task has no preview file to set as the main preview."
            )
        return entities_service.update_entity_preview(
            task["entity_id"], preview_file["id"]
        )


class SetTasksMainPreviewResource(MethodView):
    @jwt_required()
    @swag_from("openapi/SetTasksMainPreviewResource_put.yml")
    def put(self):
        """
        Set main preview from several tasks
        """
        body = validation.validate_request_body(SetTasksMainPreviewSchema)
        entities = []
        for task_id in body.task_ids:
            task = tasks_service.get_task(task_id)
            permissions_service.check_project_access(task["project_id"])
            permissions_service.check_entity_access(task["entity_id"])
            # Clients review content but must not redefine how an entity is
            # illustrated. The test comes after check_project_access, which
            # resolves the project role: before it, it reads the global one
            # and a client on this production goes through. The single task
            # route already orders it this way.
            if permissions.has_client_permissions():
                raise permissions.PermissionDenied
            preview_file = (
                preview_files_service.get_last_preview_file_for_task(task_id)
            )
            if preview_file is not None:
                entities.append(
                    entities_service.update_entity_preview(
                        task["entity_id"], preview_file["id"]
                    )
                )
        return entities


class PersonsTasksDatesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/PersonsTasksDatesResource_get.yml")
    def get(self):
        """
        Get persons tasks dates
        """
        # Normalise the `project_id` filter once, before branching on the
        # caller's role. An empty or whitespace-only `?project_id=` is treated
        # as an absent filter; any other non-UUID value is rejected with a 400
        # rather than reaching the query as an invalid UUID (which used to 500
        # for admins and 404 for managers).
        project_id = (self.get_project_id() or "").strip() or None
        if project_id is not None and not fields.is_valid_id(project_id):
            raise WrongParameterException("Invalid project_id.")
        project_ids = None
        busy_project_ids = None
        if not permissions.has_admin_permissions():
            # Supervisors reach the team schedule page too: like managers,
            # they only see the projects of their own teams.
            permissions.check_at_least_supervisor_permissions()
            if project_id is not None:
                if not permissions_service.check_belong_to_project(project_id):
                    raise permissions.PermissionDenied
            else:
                project_ids = user_service.get_open_project_ids()
                # The other open productions come back as anonymous busy
                # periods: date pairs only, so the schedule can show a
                # person is taken without naming the production or the
                # task.
                own_project_ids = set(project_ids)
                busy_project_ids = [
                    open_project_id
                    for open_project_id in projects_service.open_project_ids()
                    if open_project_id not in own_project_ids
                ]
        return schedule_service.get_persons_tasks_dates(
            project_id=project_id,
            project_ids=project_ids,
            busy_project_ids=busy_project_ids,
        )


def check_open_tasks_filter_args(resource, args):
    """
    Reject malformed open tasks filter values with a 400 before they
    reach the SQL layer as invalid UUID or date binds.
    """
    for field in (
        "project_id",
        "task_type_id",
        "task_status_id",
        "studio_id",
        "department_id",
    ):
        if args[field] is not None:
            resource.check_id_parameter(args[field])
    if args["person_id"] not in (None, "unassigned"):
        for person_id in args["person_id"].split(","):
            resource.check_id_parameter(person_id)
    resource.parse_date_parameter(args["start_date"])
    resource.parse_date_parameter(args["due_date"])


class OpenTasksResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/OpenTasksResource_get.yml")
    def get(self):
        """
        Get open tasks
        """
        args = self.get_args(
            [
                ("task_type_id", None, False, str),
                ("project_id", None, False, str),
                ("person_id", None, False, str),
                ("task_status_id", None, False, str),
                ("studio_id", None, False, str),
                ("department_id", None, False, str),
                ("start_date", None, False, str),
                ("due_date", None, False, str),
                ("priority", None, False, int),
                ("group_by", None, False, str),
                ("page", None, False, int),
                ("limit", 100, False, int),
            ]
        )
        check_open_tasks_filter_args(self, args)
        return todos_service.get_open_tasks(
            tasks_service.OpenTasksFilters.from_args(args),
            page=args["page"],
            limit=args["limit"],
        )


class OpenTasksStatsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/OpenTasksStatsResource_get.yml")
    def get(self):
        """
        Get open tasks stats
        """
        return todos_service.get_open_tasks_stats()


class OpenTasksBurndownResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/OpenTasksBurndownResource_get.yml")
    def get(self):
        """
        Get open tasks burndown
        """
        args = self.get_args(
            [
                ("task_type_id", None, False, str),
                ("project_id", None, False, str),
                ("person_id", None, False, str),
                ("task_status_id", None, False, str),
                ("studio_id", None, False, str),
                ("department_id", None, False, str),
                ("start_date", None, False, str),
                ("due_date", None, False, str),
                ("priority", None, False, int),
            ]
        )
        check_open_tasks_filter_args(self, args)
        return todos_service.get_open_tasks_burndown(
            tasks_service.OpenTasksFilters.from_args(args)
        )
