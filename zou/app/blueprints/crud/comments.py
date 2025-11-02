from flask_jwt_extended import jwt_required


from zou.app.models.comment import Comment
from zou.app.models.attachment_file import AttachmentFile

from zou.app.services import (
    comments_service,
    deletion_service,
    notifications_service,
    persons_service,
    tasks_service,
    user_service,
    projects_service,
)
from zou.app.utils import events, permissions

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class CommentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Comment)

    @jwt_required()
    def get(self):
        """
        Get comments
        ---
        tags:
          - Crud
        description: Retrieve all comments. Supports filtering via query
          parameters and pagination.
        parameters:
          - in: query
            name: page
            required: false
            schema:
              type: integer
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
            example: 50
            description: Number of results per page
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Whether to include relations
        responses:
            200:
              description: Comments retrieved successfully
              content:
                application/json:
                  schema:
                    oneOf:
                      - type: array
                        items:
                          type: object
                      - type: object
                        properties:
                          data:
                            type: array
                            items:
                              type: object
                            example: []
                          total:
                            type: integer
                            example: 100
                          nb_pages:
                            type: integer
                            example: 2
                          limit:
                            type: integer
                            example: 50
                          offset:
                            type: integer
                            example: 0
                          page:
                            type: integer
                            example: 1
            400:
              description: Invalid filter format or query error
        """
        return super().get()

    @jwt_required()
    def post(self):
        """
        Create comment
        ---
        tags:
          - Crud
        description: Create a new comment with data provided in the request
          body. JSON format is expected.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - object_id
                  - person_id
                  - task_status_id
                properties:
                  object_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  person_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  task_status_id:
                    type: string
                    format: uuid
                    example: c24a6ea4-ce75-4665-a070-57453082c25
                  text:
                    type: string
                    example: Comment text
        responses:
            201:
              description: Comment created successfully
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
                      task_status_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      text:
                        type: string
                        example: Comment text
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().post()


class CommentResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Comment)
        self.protected_fields += ["mentions", "department_mentions"]

    @jwt_required()
    def get(self, instance_id):
        """
        Get comment
        ---
        tags:
          - Crud
        description: Retrieve a comment by its ID and return it as a JSON
          object. Supports including relations. Client users can only see
          their own comments or comments from other clients.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Comment retrieved successfully
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
                      task_status_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      text:
                        type: string
                        example: Comment text
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        return super().get(instance_id)

    @jwt_required()
    def put(self, instance_id):
        """
        Update comment
        ---
        tags:
          - Crud
        description: Update a comment with data provided in the request
          body. JSON format is expected. May update task status if
          task_status_id is changed.
        parameters:
          - in: path
            name: instance_id
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
                  text:
                    type: string
                    example: Updated comment text
                  task_status_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  pinned:
                    type: boolean
                    example: true
                  checklist:
                    type: array
                    items:
                      type: object
                    example: [{"text": "Item 1", "checked": false}]
        responses:
            200:
              description: Comment updated successfully
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
                      task_status_id:
                        type: string
                        format: uuid
                        example: d24a6ea4-ce75-4665-a070-57453082c25
                      text:
                        type: string
                        example: Updated comment text
                      pinned:
                        type: boolean
                        example: true
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().put(instance_id)

    def get_serialized_instance(self, instance_id, relations=True):
        return tasks_service.get_comment(instance_id, relations=relations)

    def clean_get_result(self, result):
        if permissions.has_client_permissions():
            person = persons_service.get_person(result["person_id"])
            if person["role"] != "client":
                result["text"] = ""
                result["attachment_files"] = []
                result["checklist"] = []
        attachment_files = []
        if (
            "attachment_files" in result
            and len(result["attachment_files"]) > 0
        ):
            for attachment_file_id in result["attachment_files"]:
                attachment_file = AttachmentFile.get(attachment_file_id)
                attachment_files.append(attachment_file.present())
            result["attachment_files"] = attachment_files
        return result

    def pre_update(self, instance_dict, data):
        self.task_status_change = False
        if instance_dict["task_status_id"] != data.get("task_status_id", None):
            self.task_status_change = True
            self.previous_task_status_id = instance_dict["task_status_id"]
        return data

    def post_update(self, instance_dict, data):
        comment = comments_service.reset_mentions(instance_dict)
        if self.task_status_change:
            task_id = comment["object_id"]
            task = tasks_service.reset_task_data(task_id)
            events.emit(
                "task:status-changed",
                {
                    "task_id": task_id,
                    "new_task_status_id": comment["task_status_id"],
                    "previous_task_status_id": self.previous_task_status_id,
                    "person_id": comment["person_id"],
                },
                project_id=task["project_id"],
            )

        tasks_service.clear_comment_cache(comment["id"])
        notifications_service.reset_notifications_for_mentions(comment)
        return comment

    def check_read_permissions(self, instance):
        return user_service.check_comment_access(instance["id"])

    def check_update_permissions(self, instance, data):
        if permissions.has_admin_permissions():
            return True
        else:
            task = tasks_service.get_task(
                instance["object_id"], relations=True
            )
            task_type = tasks_service.get_task_type(task["task_type_id"])
            project = projects_service.get_project(
                task["project_id"], relations=True
            )
            current_user = persons_service.get_current_user(relations=True)
            if current_user["id"] not in project["team"]:
                raise permissions.PermissionDenied

            if permissions.has_manager_permissions():
                return True

            change_pinned = (
                "pinned" in data.keys()
                and data["pinned"] != instance["pinned"]
            )
            change_checklist = (
                "checklist" in data.keys()
                and data["checklist"] != instance["checklist"]
            )
            is_supervisor = permissions.has_supervisor_permissions()
            is_supervisor_in_department = (
                current_user["departments"] == []
                or task_type["department_id"] in current_user["departments"]
            )
            is_assigned = current_user["id"] in task["assignees"]
            comment_from_current_user = (
                current_user["id"] == instance["person_id"]
            )

            if change_pinned and (
                not is_supervisor or not is_supervisor_in_department
            ):
                raise permissions.PermissionDenied

            if change_checklist and (
                not comment_from_current_user
                and (
                    (
                        is_supervisor
                        and not (is_supervisor_in_department or is_assigned)
                    )
                    or (not is_supervisor and not is_assigned)
                )
                and (
                    len(data["checklist"]) == len(instance["checklist"])
                    and all(
                        all(
                            (
                                k == "checked"
                                or data["checklist"][i].get(k) == c[k]
                            )
                            for k in c.keys()
                        )
                        for i, c in enumerate(instance["checklist"])
                    )
                )
            ):
                raise permissions.PermissionDenied

            if (
                not comment_from_current_user
                and len(set(data.keys()) - set(["pinned", "checklist"])) > 0
            ):
                raise permissions.PermissionDenied

            if (
                "person_id" in data.keys()
                and data["person_id"] != current_user["id"]
            ):
                raise permissions.PermissionDenied

            if (
                "object_id" in data.keys()
                and data["object_id"] != instance["object_id"]
            ):
                raise permissions.PermissionDenied

            if "task_status_id" in data.keys():
                user_service.check_task_status_access(data["task_status_id"])

            return True

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

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        data["editor_id"] = persons_service.get_current_user_raw().id
        return data

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete comment
        ---
        tags:
          - Crud
        description: Delete a comment by its ID. Returns empty response
          on success. Updates task status if comment had status change.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Comment deleted successfully
            400:
              description: Cannot delete comment or integrity error
        """
        comment = tasks_service.get_comment(instance_id)
        task = tasks_service.get_task(comment["object_id"])
        if permissions.has_manager_permissions():
            user_service.check_project_access(task["project_id"])
        else:
            user_service.check_person_access(comment["person_id"])
        self.pre_delete(comment)
        deletion_service.remove_comment(comment["id"])
        tasks_service.reset_task_data(comment["object_id"])
        tasks_service.clear_comment_cache(comment["id"])
        self.post_delete(comment)
        return "", 204
