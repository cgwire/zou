import datetime


from flask import abort, request
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.services.exception import (
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
    user_service,
    concepts_service,
)
from zou.app.utils import events, query, permissions
from zou.app.mixin import ArgsMixin


class AddPreviewResource(Resource, ArgsMixin):
    @jwt_required()
    def post(self, task_id, comment_id):
        """
        Add preview metadata to given task. The preview file itself should be
        uploaded afterward.

        Revision is automatically set: it is equal to last revision + 1. It can
        be also set manually.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            schema:
                type: object
                properties:
                    revision:
                        type: integer
        responses:
            201:
                description: Preview metadata added to given task
        """
        args = self.get_args([("revision", 0, False, int)])

        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])

        tasks_service.clear_comment_cache(comment_id)
        comment = tasks_service.get_comment(comment_id)
        tasks_service.get_task_status(comment["task_status_id"])
        person = persons_service.get_current_user()
        preview_file = tasks_service.add_preview_file_to_comment(
            comment_id, person["id"], task_id, args["revision"]
        )
        return preview_file, 201


class AddExtraPreviewResource(Resource):
    """
    Add a preview to given comment.
    """

    @jwt_required()
    def post(self, task_id, comment_id, preview_file_id):
        """
        Add a preview to given comment.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: preview_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            type: file
            required: True
        responses:
            201:
                description: Preview added to given comment
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        tasks_service.get_comment(comment_id)

        person = persons_service.get_current_user()
        related_preview_file = files_service.get_preview_file(preview_file_id)

        preview_file = tasks_service.add_preview_file_to_comment(
            comment_id, person["id"], task_id, related_preview_file["revision"]
        )
        return preview_file, 201

    @jwt_required()
    def delete(self, task_id, comment_id, preview_file_id):
        """
        Delete preview from given comment.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: preview_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Preview deleted from given comment
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        deletion_service.remove_preview_file_by_id(preview_file_id)
        return "", 204


class TaskPreviewsResource(Resource):
    """
    Return previews linked to given task.
    """

    @jwt_required()
    def get(self, task_id):
        """
        Return previews linked to given task.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Previews linked to given task
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return files_service.get_preview_files_for_task(task_id)


class TaskCommentsResource(Resource):
    """
    Return comments linked to given task.
    """

    @jwt_required()
    def get(self, task_id):
        """
        Return comments linked to given task.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Comments linked to given task
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        is_client = permissions.has_client_permissions()
        is_manager = permissions.has_manager_permissions()
        is_supervisor = permissions.has_supervisor_permissions()
        return tasks_service.get_comments(
            task_id, is_client, is_manager or is_supervisor
        )


class TaskCommentResource(Resource):
    """
    Remove given comment and update linked task accordingly.
    """

    @jwt_required()
    def get(self, task_id, comment_id):
        """
        Get comment corresponding at given ID.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Comment corresponding at given ID
        """
        comment = tasks_service.get_comment(comment_id)
        user_service.check_comment_access(comment)
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
    def delete(self, task_id, comment_id):
        """
        Delete a comment corresponding at given ID.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Comment corresponding at given ID deleted
        """
        comment = tasks_service.get_comment(comment_id)
        task = tasks_service.get_task(comment["object_id"])
        if permissions.has_manager_permissions():
            user_service.check_project_access(task["project_id"])
        else:
            user_service.check_person_access(comment["person_id"])
        self.pre_delete(comment)
        deletion_service.remove_comment(comment_id)
        tasks_service.reset_task_data(comment["object_id"])
        tasks_service.clear_comment_cache(comment_id)
        self.post_delete(comment)
        return "", 204


class PersonTasksResource(Resource):
    """
    Return task assigned to given user of which status has is_done flag sets
    to false.
    """

    @jwt_required()
    def get(self, person_id):
        """
        Return task assigned to given user of which status has is_done flag sets to false.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks assigned to user that are not done
        """
        user_service.check_person_is_not_bot(person_id)
        if not permissions.has_admin_permissions():
            projects = user_service.related_projects()
        else:
            projects = projects_service.open_projects()
        if permissions.has_vendor_permissions():
            person = persons_service.get(person_id)
            if person["role"] == "vendor":
                return []
        elif permissions.has_client_permissions():
            return []
        return tasks_service.get_person_tasks(person_id, projects)


class PersonRelatedTasksResource(Resource):
    """
    For all entities assigned to given person (that have at least one task
    assigned to given person), returns all tasks for given task type.
    """

    @jwt_required()
    def get(self, person_id, task_type_id):
        """
        For all entities assigned to given person (that have at least one task assigned to given person), returns all tasks for given task type.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: person_id
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
                description: All Tasks for given task type
        """
        user_service.check_person_is_not_bot(person_id)
        user = persons_service.get_current_user()
        if person_id != user["id"]:
            permissions.check_admin_permissions()
        return tasks_service.get_person_related_tasks(person_id, task_type_id)


class PersonDoneTasksResource(Resource):
    """
    Return task assigned to given user of which status has is_done flag sets
    to true. It return only tasks related to open projects.
    """

    @jwt_required()
    def get(self, person_id):
        """
        Return task assigned to given user of which status has is_done flag sets to true.
        ---
        tags:
        - Tasks
        description: It return only tasks related to open projects.
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks assigned to user that are done
        """
        user_service.check_person_is_not_bot(person_id)
        if not permissions.has_admin_permissions():
            projects = user_service.related_projects()
        else:
            projects = projects_service.open_projects()
        if permissions.has_vendor_permissions():
            person = persons_service.get(person_id)
            if person["role"] == "vendor":
                return []
        elif permissions.has_client_permissions():
            return []
        return tasks_service.get_person_done_tasks(person_id, projects)


class CreateShotTasksResource(Resource):
    """
    Create a new task for given shot and task type.
    """

    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Create a new task for given shot and task type.
        ---
        tags:
        - Tasks
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
            201:
                description: New task for given shot and task type created
        """
        user_service.check_manager_project_access(project_id)
        task_type = tasks_service.get_task_type(task_type_id)

        shot_ids = request.json
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

        task_type = tasks_service.get_task_type(task_type_id)
        tasks = tasks_service.create_tasks(task_type, shots)
        return tasks, 201


class CreateConceptTasksResource(Resource):
    """
    Create a new task for given concept and task type.
    """

    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Create a new task for given concept and task type.
        ---
        tags:
        - Tasks
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
            201:
                description: New task for given concept and task type created
        """
        user_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        task_type = tasks_service.get_task_type(task_type_id)

        concept_ids = request.json
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
            user_service.check_entity_access(concept["id"])

        task_type = tasks_service.get_task_type(task_type_id)
        tasks = tasks_service.create_tasks(task_type, concepts)
        return tasks, 201


class CreateEntityTasksResource(Resource):
    @jwt_required()
    def post(self, project_id, entity_type, task_type_id):
        """
        Create a new task with given task type for each entity of given
        entity type.
        ---
        tags:
        - Tasks
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
          - in: path
            name: task_type_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: List of created tasks.
        """
        user_service.check_manager_project_access(project_id)
        task_type = tasks_service.get_task_type(task_type_id)
        entity_type_dict = (
            entities_service.get_entity_type_by_name_or_not_found(
                entity_type.capitalize()
            )
        )

        entity_ids = request.json
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


class CreateAssetTasksResource(Resource):
    """
    Create a new task for given asset and task type.
    """

    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Create a new task for given asset and task type.
        ---
        tags:
        - Tasks
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
            201:
                description: New task for given asset and task type created
        """
        user_service.check_manager_project_access(project_id)
        task_type = tasks_service.get_task_type(task_type_id)

        asset_ids = request.json
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


class CreateEditTasksResource(Resource):
    """
    Create a new task for given edit and task type.
    """

    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Create a new task for given edit and task type.
        ---
        tags:
        - Tasks
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
            201:
                description: New task for given edit and task type created
        """
        user_service.check_manager_project_access(project_id)
        task_type = tasks_service.get_task_type(task_type_id)

        edit_ids = request.json
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


class ToReviewResource(Resource, ArgsMixin):
    """
    Change a task status to "to review". It creates a new preview file entry
    and set path from the hard disk.
    """

    @jwt_required()
    def put(self, task_id):
        """
        Change a task status to "to review".
        ---
        tags:
        - Tasks
        description: It creates a new preview file entry and set path from the hard disk.
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: Task
            description: person ID, name, comment, revision and change status of task
            schema:
                type: object
                properties:
                    person_id:
                        type: string
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                    comment:
                        type: string
                    name:
                        type: string
                    revision:
                        type: integer
                    change_status:
                        type: boolean
        responses:
            200:
                description: Task status changed to "to review"
            400:
                description: Given person not found
        """
        (
            person_id,
            comment,
            name,
            revision,
            change_status,
        ) = self.get_arguments()

        try:
            task = tasks_service.get_task(task_id)
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["project_id"])

            if person_id is not None:
                person = persons_service.get_person(person_id)
            else:
                person = persons_service.get_current_user()

            preview_path = self.get_preview_path(task, name, revision)

            task = tasks_service.task_to_review(
                task["id"], person, comment, preview_path, change_status
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

    def get_arguments(self):
        args = self.get_args(
            [
                "person_id",
                ("comment", ""),
                ("name", "main"),
                {"name": "revision", "default": 1, "type": int},
                {"name": "change_status", "default": True, "type": bool},
            ]
        )

        return (
            args["person_id"],
            args["comment"],
            args["name"],
            args["revision"],
            args["change_status"],
        )


class ClearAssignationResource(Resource, ArgsMixin):
    """
    Remove all assignations set to given task.
    """

    @jwt_required()
    def put(self):
        """
        Remove all assignations set to given task.
        ---
        tags:
        - Tasks
        parameters:
          - in: body
            name: Task
            description: List of tasks ID and person ID
            schema:
                type: object
                required:
                  - task_ids
                properties:
                    task_ids:
                        type: string
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                    person_id:
                        type: string
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All assignations removed
        """
        (task_ids, person_id) = self.get_arguments()

        tasks = []
        for task_id in task_ids:
            try:
                user_service.check_task_departement_access_for_unassign(
                    task_id, person_id
                )
                tasks_service.clear_assignation(task_id, person_id=person_id)
                tasks.append(task_id)
            except permissions.PermissionDenied:
                pass
            except TaskNotFoundException:
                pass

        return tasks

    def get_arguments(self):
        args = self.get_args(
            [
                {
                    "name": "task_ids",
                    "help": "Tasks list required.",
                    "required": True,
                    "action": "append",
                },
                "person_id",
            ]
        )

        return args["task_ids"], args["person_id"]


class TasksAssignResource(Resource, ArgsMixin):
    """
    Assign given task lists to given person. If a given task ID is wrong,
    it ignores it.
    """

    @jwt_required()
    def put(self, person_id):
        """
        Assign given task lists to given person.
        ---
        tags:
        - Tasks
        description: If a given task ID is wrong, it ignores it.
        parameters:
          - in: path
            name: person_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
            required: True
          - in: body
            name: Task
            description: List of tasks ID
            schema:
                type: object
                required:
                  - task_ids
                properties:
                    task_ids:
                        type: string
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given tasks lists assigned to given person
        """
        user_service.check_person_is_not_bot(person_id)
        args = self.get_args(
            [
                {
                    "name": "task_ids",
                    "help": "Tasks list required.",
                    "required": True,
                    "action": "append",
                },
            ]
        )

        tasks = []
        current_user = persons_service.get_current_user()
        for task_id in args["task_ids"]:
            try:
                user_service.check_task_departement_access(task_id, person_id)
                task = self.assign_task(task_id, person_id, current_user["id"])
                notifications_service.create_assignation_notification(
                    task_id, person_id, current_user["id"]
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

    def assign_task(self, task_id, person_id, assigner_id):
        return tasks_service.assign_task(task_id, person_id, assigner_id)


class TaskAssignResource(Resource, ArgsMixin):
    """
    Assign given task to given person.
    """

    @jwt_required()
    def put(self, task_id):
        """
        Assign given task list to given person.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: Person
            description: Person ID
            schema:
                type: object
                required:
                  - person_id
                properties:
                    person_id:
                        type: string
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given task assigned to given person
            400:
                description: Assignee non-existent in database
        """
        args = self.get_args(
            [
                {
                    "name": "person_id",
                    "help": "Assignee ID required.",
                    "required": True,
                },
            ]
        )
        person_id = args["person_id"]
        try:
            user_service.check_person_is_not_bot(person_id)
            task = tasks_service.get_task(task_id)
            user_service.check_task_departement_access(task_id, person_id)
            self.assign_task(task_id, person_id)
            notifications_service.create_assignation_notification(
                task_id, person_id
            )
            projects_service.add_team_member(task["project_id"], person_id)
        except PersonNotFoundException:
            return {"error": "Assignee doesn't exist in database."}, 400

        return task

    def assign_task(self, task_id, person_id):
        return tasks_service.assign_task(task_id, person_id)


class TaskFullResource(Resource):
    """
    Return a task with many information: full details for assignees, full
    details for task type, full details for task status, etc.
    """

    @jwt_required()
    def get(self, task_id):
        """
        Return a task with many information.
        ---
        description: Full details for assignees, full details for task type, full details for task status, etc.
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Task with many information
        """
        task = tasks_service.get_full_task(
            task_id, persons_service.get_current_user()["id"]
        )
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return task


class TaskForEntityResource(Resource):
    """
    Return tasks related to given entity asset, episode, sequence, shot or
    scene.
    """

    @jwt_required()
    def get(self, entity_id, task_type_id):
        """
        Return tasks related to given entity asset, episode, sequence, shot or scene.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: entity_id
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
                description: Tasks related to given entity asset, episode, sequence, shot or scene
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return tasks_service.get_tasks_for_entity_and_task_type(
            entity_id, task_type_id
        )


class SetTimeSpentResource(Resource, ArgsMixin):
    """
    Set time spent by a person on a task for a given day.
    """

    @jwt_required()
    def post(self, task_id, date, person_id):
        """
        Set time spent by a person on a task for a given day.
        ---
        tags:
        - Tasks
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
          - in: path
            name: person_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: Duration
            schema:
                type: object
                properties:
                    duration:
                        type: float
        responses:
            201:
                description: Time spent by given person on given task for given day is set
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        args = self.get_args([("duration", 0, True, int)])
        try:
            if args["duration"] <= 0:
                raise WrongParameterException("Duration must be positive")
            user_service.check_time_spent_access(task_id, person_id)
            time_spent = tasks_service.create_or_update_time_spent(
                task_id,
                person_id,
                datetime.datetime.strptime(date, "%Y-%m-%d"),
                args["duration"],
            )
            return time_spent, 201
        except ValueError:
            abort(404)
        except WrongDateFormatException:
            abort(404)

    @jwt_required()
    def delete(self, task_id, date, person_id):
        """
        Delete time spent by a person on a task for a given day.
        ---
        tags:
        - Tasks
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
          - in: path
            name: person_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Time spent by given person on given task for given day is removed
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        try:
            user_service.check_time_spent_access(task_id, person_id)
            time_spent = tasks_service.delete_time_spent(
                task_id,
                person_id,
                datetime.datetime.strptime(date, "%Y-%m-%d"),
            )
            return time_spent, 201
        except ValueError:
            abort(404)
        except WrongDateFormatException:
            abort(404)


class AddTimeSpentResource(Resource, ArgsMixin):
    """
    Add given timeframe to time spent by a person on a task for a given day.
    """

    @jwt_required()
    def post(self, task_id, date, person_id):
        """
        Add given timeframe to time spent by a person on a task for a given day.
        ---
        tags:
        - Tasks
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
          - in: path
            name: person_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: Duration
            schema:
                type: object
                properties:
                    duration:
                        type: float
        responses:
            201:
                description: Given timeframe added to time spent by given person on given task for given day
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        args = self.get_args([("duration", 0, True, int)])
        try:
            if args["duration"] <= 0:
                raise WrongParameterException("Duration must be positive")
            user_service.check_time_spent_access(task_id, person_id)
            time_spent = tasks_service.create_or_update_time_spent(
                task_id, person_id, date, args["duration"], add=True
            )
            return time_spent, 201
        except ValueError:
            abort(404)
        except WrongDateFormatException:
            abort(404)


class GetTimeSpentResource(Resource):
    """
    Get time spent on a given task.
    """

    @jwt_required()
    def get(self, task_id):
        """
        Get time spent on a given task.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Time spent on given task
            404:
                description: Wrong date format
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return tasks_service.get_time_spents(task_id)


class GetTimeSpentDateResource(Resource):
    """
    Get time spent on a given task and date.
    """

    @jwt_required()
    def get(self, task_id, date):
        """
        Get time spent on a given task and date.
        ---
        tags:
        - Tasks
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
                description: Time spent on given task and date
            404:
                description: Wrong date format
        """
        try:
            task = tasks_service.get_task(task_id)
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["entity_id"])
            return tasks_service.get_time_spents(task_id, date)
        except WrongDateFormatException:
            abort(404)


class DeleteAllTasksForTaskTypeResource(Resource):
    """
    Delete all tasks for a given task type and project. It's mainly used
    when tasks are created by mistake at the beginning of the project.
    """

    @jwt_required()
    def delete(self, project_id, task_type_id):
        """
        Delete all tasks for a given task type and project.
        ---
        tags:
        - Tasks
        description: It's mainly used when tasks are created by mistake at the beginning of the project.
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
            204:
                description: All tasks for given task type and project deleted
        """
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        task_ids = deletion_service.remove_tasks_for_project_and_task_type(
            project_id, task_type_id
        )
        for task_id in task_ids:
            tasks_service.clear_task_cache(task_id)
        return "", 204


class DeleteTasksResource(Resource):
    """
    Delete tasks matching id list given in parameter. See it as a way to batch
    delete tasks.
    """

    @jwt_required()
    def post(self, project_id):
        """
        Delete tasks matching id list given in parameter.
        ---
        tags:
        - Tasks
        description: See it as a way to batch delete tasks.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Tasks matching id list given in parameter deleted
        """
        user_service.check_manager_project_access(project_id)
        task_ids = request.json
        task_ids = deletion_service.remove_tasks(project_id, task_ids)
        for task_id in task_ids:
            tasks_service.clear_task_cache(task_id)
        return task_ids, 200


class ProjectSubscriptionsResource(Resource):
    """
    Retrieve all subcriptions to tasks related to given project.
    It's mainly used for synchronisation purpose.
    """

    @jwt_required()
    @permissions.require_admin
    def get(self, project_id):
        """
        Retrieve all subcriptions to tasks related to given project.
        ---
        tags:
        - Tasks
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All subcriptions to tasks related to given project
        """
        projects_service.get_project(project_id)
        return notifications_service.get_subscriptions_for_project(project_id)


class ProjectNotificationsResource(Resource, ArgsMixin):
    """
    Retrieve all notifications related to given project.
    It's mainly used for synchronisation purpose.
    """

    @jwt_required()
    @permissions.require_admin
    def get(self, project_id):
        """
        Retrieve all notifications to tasks related to given project.
        ---
        tags:
        - Tasks
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All notifications to tasks related to given project
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        return notifications_service.get_notifications_for_project(
            project_id, page
        )


class ProjectTasksResource(Resource, ArgsMixin):
    """
    Retrieve all tasks related to given project.
    It's mainly used for synchronisation purpose.
    """

    @jwt_required()
    @permissions.require_admin
    def get(self, project_id):
        """
        Retrieve all tasks related to given project.
        ---
        tags:
        - Tasks
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given project
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        return tasks_service.get_tasks_for_project(project_id, page)


class ProjectCommentsResource(Resource, ArgsMixin):
    """
    Retrieve all comments to tasks related to given project.
    It's mainly used for synchronisation purpose.
    """

    @jwt_required()
    @permissions.require_admin
    def get(self, project_id):
        """
        Retrieve all comments to tasks related to given project.
        ---
        tags:
        - Tasks
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All comments to tasks related to given project
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        return tasks_service.get_comments_for_project(project_id, page)


class ProjectPreviewFilesResource(Resource, ArgsMixin):
    """
    Preview files related to a given project.
    """

    @jwt_required()
    @permissions.require_admin
    def get(self, project_id):
        """
        Preview files related to a given project.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Preview files related to given project
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        return files_service.get_preview_files_for_project(project_id, page)


class SetTaskMainPreviewResource(Resource):
    @jwt_required()
    def put(self, task_id):
        """
        Set last preview from given task as main preview of the related entity.
        This preview will be used as thumbnail to illustrate the entity.
        ---
        tags:
          - Task
        description: This preview will be used to illustrate the entity.
        parameters:
          - in: path
            name: preview_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given preview set as main preview
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        preview_file = preview_files_service.get_last_preview_file_for_task(
            task_id
        )
        entity = entities_service.get_entity(task["entity_id"])
        if preview_file is not None:
            entities_service.update_entity_preview(
                task["entity_id"], preview_file["id"]
            )
            assets_service.clear_asset_cache(entity["id"])
            shots_service.clear_shot_cache(entity["id"])
            edits_service.clear_edit_cache(entity["id"])
            shots_service.clear_episode_cache(entity["id"])
            shots_service.clear_sequence_cache(entity["id"])
        return entity


class PersonsTasksDatesResource(Resource):
    @jwt_required()
    @permissions.require_admin
    def get(self):
        """
        For schedule usages, for each active person, it returns the first start
        date of all tasks of assigned to this person and the last end date.
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: For each person, the first start date of all tasks of assigned to this person and the last end date.
        """
        permissions.check_admin_permissions()
        return tasks_service.get_persons_tasks_dates()


class OpenTasksResource(Resource, ArgsMixin):
    """
    Return all tasks related to open projects.
    """

    @jwt_required()
    def get(self):
        """
        Return all tasks related to open projects.
        ---
        tags:
        - Tasks
        parameters:
          - in: query
            name: project_id
            description: Filter tasks on given project ID
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_status_id
            description: Filter tasks on given task status ID
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_type_id
            description: Filter tasks on given task type ID ID
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: person_id
            description: Filter tasks on given person ID
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: start_date
            description: Filter tasks posterior to given start date
            type: string
            format: date
            x-example: "2022-07-12"
          - in: query
            name: due_date
            description: Filter tasks anterior to given due date
            type: string
            format: date
            x-example: "2022-07-12"
          - in: query
            name: priority
            description: Filter tasks on given priority
            type: integer
            x-example: "3"
          - in: query
            name: page
            description: Page number
            type: integer
            x-example: 1
            default: 1
          - in: query
            name: limit
            description: Number of tasks per page
            type: integer
            x-example: 100
            default: 100

        responses:
            200:
                schema:
                    type: object
                    properties:
                        data:
                            type: array
                            description: List of tasks
                        stats:
                            type: object
                            properties:
                                total:
                                    type: integer
                                    description: Total number of tasks
                                total_duration:
                                    type: integer
                                    description: Total duration of tasks in minutes
                                total_estimation:
                                    type: integer
                                    description: Total estimation of tasks in minutes
                                status:
                                    type: object
                                    description: Number of tasks per status
                        limit:
                            type: integer
                            description: Number of tasks per page
                        page:
                            type: integer
                            description: Page number
                        is_more:
                            type: boolean
                            description: True if there are more tasks to retrieve
        """
        args = self.get_args(
            [
                ("task_type_id", None, False, str),
                ("project_id", None, False, str),
                ("person_id", None, False, str),
                ("task_status_id", None, False, str),
                ("start_date", None, False, str),
                ("due_date", None, False, str),
                ("priority", None, False, str),
                ("group_by", None, False, str),
                ("page", None, False, int),
                ("limit", 100, False, int),
            ]
        )
        return tasks_service.get_open_tasks(
            task_type_id=args["task_type_id"],
            project_id=args["project_id"],
            person_id=args["person_id"],
            task_status_id=args["task_status_id"],
            start_date=args["start_date"],
            due_date=args["due_date"],
            priority=args["priority"],
            page=args["page"],
            limit=args["limit"],
        )
