import datetime


from flask import abort, request
from flask_restful import Resource, inputs
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
from zou.app.utils import events, query, permissions, date_helpers
from zou.app.mixin import ArgsMixin


class AddPreviewResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, task_id, comment_id):
        """
        Add task preview
        ---
        tags:
        - Tasks
        description: Add preview metadata to a task. The preview file is
          uploaded after. Revision is auto set to last + 1. It can also be set
          manually.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
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
                  revision:
                    type: integer
                    description: Revision number for the preview
                    example: 1
        responses:
            201:
              description: Preview metadata added to task
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      comment_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      revision:
                        type: integer
                        example: 3
                      person_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Bad request
        """
        args = self.get_args([("revision", 0, False, int)])

        user_service.check_task_action_access(task_id)

        person = persons_service.get_current_user()
        preview_file = tasks_service.add_preview_file_to_comment(
            comment_id, person["id"], task_id, args["revision"]
        )
        return preview_file, 201


class AddExtraPreviewResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, task_id, comment_id, preview_file_id):
        """
        Add preview to comment
        ---
        tags:
        - Tasks
        description: Add a preview to a comment by uploading a file in multipart
          form data.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            multipart/form-data:
              schema:
                type: object
                properties:
                  file:
                    type: string
                    format: binary
                    description: Preview file to upload
        responses:
            201:
              description: Preview added to comment
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      comment_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      revision:
                        type: integer
                        example: 2
                      person_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
            400:
              description: Bad request
        """
        user_service.check_task_action_access(task_id)
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
        Delete preview from comment
        ---
        tags:
        - Tasks
        description: Delete a preview from a comment. Use force query to delete
          even if there are dependencies.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: force
            required: false
            schema:
              type: boolean
              default: false
            description: Force deletion even if preview has dependencies
        responses:
            204:
              description: Preview deleted from comment
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        deletion_service.remove_preview_file_by_id(
            preview_file_id, force=self.get_force()
        )
        return "", 204


class TaskPreviewsResource(Resource):

    @jwt_required()
    def get(self, task_id):
        """
        Get task previews
        ---
        tags:
        - Tasks
        description: Return previews linked to a task.
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
              description: Previews linked to task
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        task_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        revision:
                          type: integer
                          example: 1
                        comment_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        person_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
                        created_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
        """
        user_service.check_task_access(task_id)
        return files_service.get_preview_files_for_task(task_id)


class TaskCommentsResource(Resource):

    @jwt_required()
    def get(self, task_id):
        """
        Get task comments
        ---
        tags:
        - Tasks
        description: Return comments linked to a task.
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
              description: Comments linked to task
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        object_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        person_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        text:
                          type: string
                          example: This task is progressing well
                        created_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
                        updated_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T11:00:00Z"
        """
        user_service.check_task_access(task_id)
        is_client = permissions.has_client_permissions()
        is_manager = permissions.has_manager_permissions()
        is_supervisor = permissions.has_supervisor_permissions()
        return tasks_service.get_comments(
            task_id, is_client, is_manager or is_supervisor
        )


class TaskCommentResource(Resource):

    @jwt_required()
    def get(self, task_id, comment_id):
        """
        Get comment
        ---
        tags:
        - Tasks
        description: Get a comment by id for a task.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Comment found and returned
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      object_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      person_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      text:
                        type: string
                        example: Review completed successfully
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
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
        Delete comment
        ---
        tags:
        - Tasks
        description: Delete a comment by id for a task.
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Comment deleted
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

    @jwt_required()
    def get(self, person_id):
        """
        Get person open tasks
        ---
        tags:
        - Tasks
        description: List tasks assigned to a person where the status is not
          done.
        parameters:
          - in: path
            name: person_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks assigned to user that are not done
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010 Animation
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
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

    @jwt_required()
    def get(self, person_id, task_type_id):
        """
        Get person tasks for type
        ---
        tags:
        - Tasks
        description: For all entities assigned to the person, return tasks for
          the given task type.
        parameters:
          - in: path
            name: person_id
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
              description: All tasks for the given task type
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Asset Modeling
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
        """
        user_service.check_person_is_not_bot(person_id)
        user = persons_service.get_current_user()
        if person_id != user["id"]:
            permissions.check_admin_permissions()
        return tasks_service.get_person_related_tasks(person_id, task_type_id)


class PersonDoneTasksResource(Resource):

    @jwt_required()
    def get(self, person_id):
        """
        Get person done tasks
        ---
        tags:
        - Tasks
        description: Return tasks assigned to the person that are done. Only
          tasks in open projects are returned.
        parameters:
          - in: path
            name: person_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Tasks assigned to user that are done
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: EP01 Layout
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
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

    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Create shot tasks
        ---
        tags:
        - Tasks
        description: Create tasks for shots. Provide a list of shot IDs in the
          JSON body, or omit for all shots in the project.
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
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: string
                  format: uuid
                description: List of shot IDs to create tasks for
              example: ["b24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
            201:
              description: Tasks created for shots
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010 Animation
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
            400:
              description: Bad request
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

    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Create concept tasks
        ---
        tags:
        - Tasks
        description: Create tasks for concepts. Provide a list of concept IDs in
          the JSON body, or omit for all concepts in the project.
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
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: string
                  format: uuid
                description: List of concept IDs to create tasks for
              example: ["b24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
            201:
              description: Tasks created for concepts
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Concept Modeling
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
            400:
              description: Bad request
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
        Create entity tasks
        ---
        tags:
        - Tasks
        description: Create tasks for entities of a given type. Provide entity
          IDs in the JSON body, or omit for all entities in the project.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: entity_type
            required: true
            schema:
              type: string
            example: Asset
            description: Entity type name (Asset, Sequence, etc.)
          - in: path
            name: task_type_id
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
                type: array
                items:
                  type: string
                  format: uuid
                description: List of entity IDs to create tasks for
              example: ["b24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
            201:
              description: Tasks created for entities
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Entity Task Name
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
            400:
              description: Bad request
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

    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Create asset tasks
        ---
        tags:
        - Tasks
        description: Create tasks for assets. Provide a list of asset IDs in
          the JSON body, or omit for all assets in the project.
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
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: string
                  format: uuid
                description: List of asset IDs to create tasks for
              example: ["b24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
            201:
              description: Tasks created for assets
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Asset Modeling
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
            400:
              description: Bad request
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

    @jwt_required()
    def post(self, project_id, task_type_id):
        """
        Create edit tasks
        ---
        tags:
        - Tasks
        description: Create tasks for edits. Provide a list of edit IDs in
          the JSON body, or omit for all edits in the project.
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
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: string
                  format: uuid
                description: List of edit IDs to create tasks for
              example: ["b24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
            201:
              description: Tasks created for edits
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: Edit Compositing
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
            400:
              description: Wrong criterions format
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

    @jwt_required()
    def put(self, task_id):
        """
        Set task to review
        ---
        tags:
        - Tasks
        description: Create a new preview file entry and set the path from the
          disk. Optionally change the task status.
        parameters:
          - in: path
            name: task_id
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
                  person_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  comment:
                    type: string
                    example: Please check this version
                  name:
                    type: string
                    example: main
                  revision:
                    type: integer
                    example: 1
                  change_status:
                    type: boolean
                    example: true
        responses:
            200:
                description: Task set to review and preview created
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010 Animation
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
            400:
                description: Invalid person or parameters
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
            user_service.check_entity_access(task["entity_id"])

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

    def get_arguments(self):
        args = self.get_args(
            [
                "person_id",
                ("comment", ""),
                ("name", "main"),
                {"name": "revision", "default": 1, "type": int},
                {
                    "name": "change_status",
                    "default": True,
                    "type": inputs.boolean,
                },
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

    @jwt_required()
    def put(self):
        """
        Clear task assignations
        ---
        tags:
        - Tasks
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_ids
                properties:
                  task_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
                    example: [
                      "a24a6ea4-ce75-4665-a070-57453082c25",
                      "b24a6ea4-ce75-4665-a070-57453082c25"
                    ]
                  person_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Assignations removed
                content:
                  application/json:
                    schema:
                      type: array
                      items:
                        type: string
                        format: uuid
                      example: ["a24a6ea4-ce75-4665-a070-57453082c25"]
        """
        (task_ids, person_id) = self.get_arguments()

        tasks = []
        for task_id in task_ids:
            try:
                user_service.check_task_department_access_for_unassign(
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

    @jwt_required()
    def put(self, person_id):
        """
        Assign tasks to person
        ---
        tags:
        - Tasks
        description: Assign a list of tasks to a person. Unknown task ids are
          ignored.
        parameters:
          - in: path
            name: person_id
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
                required:
                  - task_ids
                properties:
                  task_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
                    example: [
                      "a24a6ea4-ce75-4665-a070-57453082c25",
                      "b24a6ea4-ce75-4665-a070-57453082c25"
                    ]
        responses:
            200:
                description: Tasks assigned to person
                content:
                  application/json:
                    schema:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010 Animation
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
                          project_id:
                            type: string
                            format: uuid
                            example: e24a6ea4-ce75-4665-a070-57453082c25
                          assignees:
                            type: array
                            items:
                              type: string
                              format: uuid
                            example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
            400:
                description: Assignee does not exist
        """
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
                user_service.check_person_is_not_bot(person_id)
                user_service.check_task_department_access(task_id, person_id)
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


class TaskAssignResource(Resource, ArgsMixin):

    @jwt_required()
    def put(self, task_id):
        """
        Assign task to person
        ---
        tags:
        - Tasks
        parameters:
          - in: path
            name: task_id
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
                required:
                  - person_id
                properties:
                  person_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Task assigned to person
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010 Animation
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
                        assignees:
                          type: array
                          items:
                            type: string
                            format: uuid
                          example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
            400:
                description: Assignee does not exist
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
        current_user = persons_service.get_current_user()
        try:
            user_service.check_person_is_not_bot(person_id)
            user_service.check_task_department_access(task_id, person_id)
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


class TaskFullResource(Resource):

    @jwt_required()
    def get(self, task_id):
        """
        Get task full
        ---
        description: Return a task with many information. Includes full details
          for assignees, task type, and task status.
        tags:
        - Tasks
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
                description: Task with full information
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010 Animation
                        task_type_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        task_status_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        project_id:
                          type: string
                          format: uuid
                          example: e24a6ea4-ce75-4665-a070-57453082c25
                        assignees:
                          type: array
                          items:
                            type: object
                            properties:
                              id:
                                type: string
                                format: uuid
                                example: f24a6ea4-ce75-4665-a070-57453082c25
                              first_name:
                                type: string
                                example: John
                              last_name:
                                type: string
                                example: Doe
                        task_type:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              example: b24a6ea4-ce75-4665-a070-57453082c25
                            name:
                              type: string
                              example: Animation
                        task_status:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              example: c24a6ea4-ce75-4665-a070-57453082c25
                            name:
                              type: string
                              example: In Progress
        """
        task = tasks_service.get_full_task(
            task_id, persons_service.get_current_user()["id"]
        )
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return task


class TaskForEntityResource(Resource):

    @jwt_required()
    def get(self, entity_id, task_type_id):
        """
        Get tasks for entity and type
        ---
        tags:
        - Tasks
        description: Return tasks related to the entity (asset, episode,
          sequence, shot, or scene) for a task type.
        parameters:
          - in: path
            name: entity_id
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
                description: Tasks related to the entity and task type
                content:
                  application/json:
                    schema:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          name:
                            type: string
                            example: SH010 Animation
                          task_type_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          task_status_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          entity_id:
                            type: string
                            format: uuid
                            example: d24a6ea4-ce75-4665-a070-57453082c25
                          project_id:
                            type: string
                            format: uuid
                            example: e24a6ea4-ce75-4665-a070-57453082c25
                          assignees:
                            type: array
                            items:
                              type: string
                              format: uuid
                            example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return tasks_service.get_tasks_for_entity_and_task_type(
            entity_id, task_type_id
        )


class SetTimeSpentResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, task_id, date, person_id):
        """
        Set time spent
        ---
        tags:
        - Tasks
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
          - in: path
            name: person_id
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
                  duration:
                    type: number
                    example: 120
        responses:
            201:
                description: Time spent set for the person on the task and day
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        task_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        person_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        date:
                          type: string
                          format: date
                          example: "2022-07-12"
                        duration:
                          type: number
                          example: 120
                        created_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
            400:
                description: Invalid parameters
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
                date_helpers.get_date_from_string(date),
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
        Delete time spent
        ---
        tags:
        - Tasks
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
          - in: path
            name: person_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Time spent removed for the person on the task
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        task_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        person_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        date:
                          type: string
                          format: date
                          example: "2022-07-12"
                        duration:
                          type: number
                          example: 0
                        created_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
            400:
                description: Invalid parameters
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

    @jwt_required()
    def post(self, task_id, date, person_id):
        """
        Add time spent
        ---
        tags:
        - Tasks
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
          - in: path
            name: person_id
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
                  duration:
                    type: number
                    example: 30
        responses:
            201:
                description: Timeframe added to time spent
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        task_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        person_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        date:
                          type: string
                          format: date
                          example: "2022-07-12"
                        duration:
                          type: number
                          example: 150
                        created_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
            400:
                description: Invalid parameters
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

    @jwt_required()
    def get(self, task_id):
        """
        Get task time spent
        ---
        tags:
        - Tasks
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
                description: Time spent on the task
                content:
                  application/json:
                    schema:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          task_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          person_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          date:
                            type: string
                            format: date
                            example: "2022-07-12"
                          duration:
                            type: number
                            example: 120
                          created_at:
                            type: string
                            format: date-time
                            example: "2024-01-15T10:30:00Z"
        """
        user_service.check_task_access(task_id)
        return tasks_service.get_time_spents(task_id)


class GetTimeSpentDateResource(Resource):

    @jwt_required()
    def get(self, task_id, date):
        """
        Get task time spent for date
        ---
        tags:
        - Tasks
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
                description: Time spent on the task for the date
                content:
                  application/json:
                    schema:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          task_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          person_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          date:
                            type: string
                            format: date
                            example: "2022-07-12"
                          duration:
                            type: number
                            example: 120
                          created_at:
                            type: string
                            format: date-time
                            example: "2024-01-15T10:30:00Z"
        """
        try:
            user_service.check_task_access(task_id)
            return tasks_service.get_time_spents(task_id, date)
        except WrongDateFormatException:
            abort(404)


class DeleteAllTasksForTaskTypeResource(Resource):

    @jwt_required()
    def delete(self, project_id, task_type_id):
        """
        Delete tasks for type
        ---
        tags:
        - Tasks
        description: Delete all tasks for a task type in a project. Useful when
          tasks were created by mistake at project start.
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

    @jwt_required()
    def post(self, project_id):
        """
        Delete tasks batch
        ---
        tags:
        - Tasks
        description: Delete tasks given by id list. Useful for batch deletions.
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
                description: Tasks matching id list given in parameter deleted
                content:
                  application/json:
                    schema:
                      type: array
                      items:
                        type: string
                        format: uuid
                      example: ["a24a6ea4-ce75-4665-a070-57453082c25"]
        """
        user_service.check_manager_project_access(project_id)
        task_ids = request.json
        task_ids = deletion_service.remove_tasks(project_id, task_ids)
        for task_id in task_ids:
            tasks_service.clear_task_cache(task_id)
        return task_ids, 200


class ProjectSubscriptionsResource(Resource):

    @jwt_required()
    @permissions.require_admin
    def get(self, project_id):
        """
        Get project subscriptions
        ---
        tags:
        - Tasks
        description: Retrieve all subscriptions to tasks related to a project.
          Useful for sync.
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
                description: All subcriptions to tasks related to given project
                content:
                  application/json:
                    schema:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          person_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          task_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          created_at:
                            type: string
                            format: date-time
                            example: "2024-01-15T10:30:00Z"
        """
        projects_service.get_project(project_id)
        return notifications_service.get_subscriptions_for_project(project_id)


class ProjectNotificationsResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def get(self, project_id):
        """
        Get project notifications
        ---
        tags:
        - Tasks
        description: Retrieve notifications for tasks related to a project.
          Useful for sync.
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
                description: All notifications to tasks related to given project
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
                                example: a24a6ea4-ce75-4665-a070-57453082c25
                              person_id:
                                type: string
                                format: uuid
                                example: b24a6ea4-ce75-4665-a070-57453082c25
                              task_id:
                                type: string
                                format: uuid
                                example: c24a6ea4-ce75-4665-a070-57453082c25
                              comment_id:
                                type: string
                                format: uuid
                                example: d24a6ea4-ce75-4665-a070-57453082c25
                              notification_type:
                                type: string
                                example: assignment
                              created_at:
                                type: string
                                format: date-time
                                example: "2024-01-15T10:30:00Z"
                              updated_at:
                                type: string
                                format: date-time
                                example: "2024-01-15T11:00:00Z"
                        limit:
                          type: integer
                          example: 100
                        page:
                          type: integer
                          example: 1
                        is_more:
                          type: boolean
                          example: true
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        return notifications_service.get_notifications_for_project(
            project_id, page
        )


class ProjectTasksResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Get project tasks
        ---
        tags:
        - Tasks
        description: Retrieve tasks related to a project. Useful for sync.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: page
            required: False
            type: integer
            example: 1
          - in: query
            name: task_type_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: episode_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All tasks related to given project
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
                                example: a24a6ea4-ce75-4665-a070-57453082c25
                              name:
                                type: string
                                example: SH010 Animation
                              task_type_id:
                                type: string
                                format: uuid
                                example: b24a6ea4-ce75-4665-a070-57453082c25
                              task_status_id:
                                type: string
                                format: uuid
                                example: c24a6ea4-ce75-4665-a070-57453082c25
                              entity_id:
                                type: string
                                format: uuid
                                example: d24a6ea4-ce75-4665-a070-57453082c25
                              project_id:
                                type: string
                                format: uuid
                                example: e24a6ea4-ce75-4665-a070-57453082c25
                              assignees:
                                type: array
                                items:
                                  type: string
                                  format: uuid
                                example: ["f24a6ea4-ce75-4665-a070-57453082c25"]
                        limit:
                          type: integer
                          example: 100
                        page:
                          type: integer
                          example: 1
                        is_more:
                          type: boolean
                          example: true
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        task_type_id = self.get_task_type_id()
        episode_id = self.get_episode_id()
        return tasks_service.get_tasks_for_project(
            project_id, page, task_type_id=task_type_id, episode_id=episode_id
        )


class ProjectCommentsResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Get project comments
        ---
        tags:
        - Tasks
        description: Retrieve comments for tasks related to a project. Useful
          for sync.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: limit
            type: integer
            default: 100
            example: 100
        responses:
            200:
                description: All comments to tasks related to given project
                content:
                  application/json:
                    schema:
                      type: array
                      items:
                        type: object
                        properties:
                          id:
                            type: string
                            format: uuid
                            example: a24a6ea4-ce75-4665-a070-57453082c25
                          object_id:
                            type: string
                            format: uuid
                            example: b24a6ea4-ce75-4665-a070-57453082c25
                          person_id:
                            type: string
                            format: uuid
                            example: c24a6ea4-ce75-4665-a070-57453082c25
                          text:
                            type: string
                            example: This task looks good
                          created_at:
                            type: string
                            format: date-time
                            example: "2024-01-15T10:30:00Z"
                          updated_at:
                            type: string
                            format: date-time
                            example: "2024-01-15T11:00:00Z"
        """
        projects_service.get_project(project_id)
        user_service.check_project_access(project_id)
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        page = self.get_page()
        limit = self.get_limit()
        return tasks_service.get_comments_for_project(project_id, page, limit)


class ProjectPreviewFilesResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def get(self, project_id):
        """
        Get project preview files
        ---
        tags:
        - Tasks
        description: Retrieve all preview files that are linked to a specific
          project. This includes images, videos, and other preview media
          associated with the project.
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
                description: Preview files related to given project
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
                                example: a24a6ea4-ce75-4665-a070-57453082c25
                              task_id:
                                type: string
                                format: uuid
                                example: b24a6ea4-ce75-4665-a070-57453082c25
                              comment_id:
                                type: string
                                format: uuid
                                example: c24a6ea4-ce75-4665-a070-57453082c25
                              revision:
                                type: integer
                                example: 1
                              person_id:
                                type: string
                                format: uuid
                                example: e24a6ea4-ce75-4665-a070-57453082c25
                              created_at:
                                type: string
                                format: date-time
                                example: "2024-01-15T10:30:00Z"
                        limit:
                          type: integer
                          example: 100
                        page:
                          type: integer
                          example: 1
                        is_more:
                          type: boolean
                          example: true
        """
        projects_service.get_project(project_id)
        page = self.get_page()
        return files_service.get_preview_files_for_project(project_id, page)


class SetTaskMainPreviewResource(Resource):
    @jwt_required()
    def put(self, task_id):
        """
        Set main preview from task
        ---
        tags:
          - Tasks
        description: Set the last preview of a task as the main preview of the
          related entity.
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
                description: Preview set as main preview
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          example: SH010
                        project_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        preview_file_id:
                          type: string
                          format: uuid
                          example: c24a6ea4-ce75-4665-a070-57453082c25
                        entity_type_id:
                          type: string
                          format: uuid
                          example: d24a6ea4-ce75-4665-a070-57453082c25
                        created_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
                        updated_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T11:00:00Z"
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        preview_file = preview_files_service.get_last_preview_file_for_task(
            task_id
        )
        if preview_file is not None:
            entity = entities_service.update_entity_preview(
                task["entity_id"], preview_file["id"]
            )
        return entity


class PersonsTasksDatesResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def get(self):
        """
        Get persons tasks dates
        ---
        tags:
        - Tasks
        description: For each active person, return the first start date of all
          tasks assigned to them and the last end date. Useful for schedule
          planning.
        parameters:
          - in: query
            name: project_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter by project ID
        responses:
            200:
              description: First start date and last end date for tasks per
                person
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        person_id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        first_start_date:
                          type: string
                          format: date
                          example: "2024-01-15"
                        last_end_date:
                          type: string
                          format: date
                          example: "2024-03-21"
        """
        permissions.check_admin_permissions()
        args = self.get_args([("project_id", None, False, str)])
        return tasks_service.get_persons_tasks_dates(
            project_id=args["project_id"]
        )


class OpenTasksResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self):
        """
        Get open tasks
        ---
        tags:
        - Tasks
        description: Return tasks for open projects with optional filters and
          pagination. Includes statistics.
        parameters:
          - in: query
            name: project_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter tasks on given project ID
          - in: query
            name: task_status_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter tasks on given task status ID
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter tasks on given task type ID
          - in: query
            name: person_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter tasks on given person ID
          - in: query
            name: start_date
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Filter tasks posterior to given start date
          - in: query
            name: due_date
            required: false
            schema:
              type: string
              format: date
            example: "2022-07-12"
            description: Filter tasks anterior to given due date
          - in: query
            name: priority
            required: false
            schema:
              type: integer
            example: 3
            description: Filter tasks on given priority
          - in: query
            name: page
            required: false
            schema:
              type: integer
              default: 1
            example: 1
            description: Page number
          - in: query
            name: limit
            required: false
            schema:
              type: integer
              default: 100
            example: 100
            description: Number of tasks per page

        responses:
            200:
              description: List of tasks with pagination and statistics
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      data:
                        type: array
                        items:
                          type: object
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
            400:
              description: Bad request
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
            studio_id=args["studio_id"],
            department_id=args["department_id"],
            start_date=args["start_date"],
            due_date=args["due_date"],
            priority=args["priority"],
            page=args["page"],
            limit=args["limit"],
        )


class OpenTasksStatsResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self):
        """
        Get open tasks stats
        ---
        tags:
        - Tasks
        description: Return totals and aggregates by status and task type per
          project for open projects.
        responses:
            200:
              description: A dict by project with results for each task type and
                status pair
              content:
                application/json:
                  schema:
                    type: object
                    additionalProperties:
                      type: object
                      properties:
                        total:
                          type: integer
                        done:
                          type: integer
                        estimation:
                          type: integer
                        duration:
                          type: integer
            400:
              description: Bad request
        """
        return tasks_service.get_open_tasks_stats()
