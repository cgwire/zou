from sqlalchemy.exc import IntegrityError

from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.models.entity import Entity, EntityLink
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.mixin import ArgsMixin
from zou.app.utils import events, fields, permissions
from zou.app.services.exception import WrongParameterException
from zou.app.services import (
    entities_service,
    shots_service,
    tasks_service,
    user_service,
)


class BaseImportKitsuResource(Resource, ArgsMixin):
    def __init__(self, model):
        Resource.__init__(self)
        self.model = model

    @jwt_required()
    def post(self):
        """
        Import kitsu resource
        ---
        tags:
          - Import
        description: Import Kitsu resources. Send a list of Kitsu entries in
          the JSON body. Returns created or updated resources.
        requestBody:
          required: true
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
                      example: Resource name
                    project_id:
                      type: string
                      format: uuid
                      example: b24a6ea4-ce75-4665-a070-57453082c25
              example:
                - id: a24a6ea4-ce75-4665-a070-57453082c25
                  name: Example resource
                  project_id: b24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Resources imported successfully
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
                          example: Imported resource
                        created_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T10:30:00Z"
                        updated_at:
                          type: string
                          format: date-time
                          example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid request body or missing required fields
        """
        kitsu_entries = request.json
        if not isinstance(kitsu_entries, list):
            raise WrongParameterException("A list of entities is expected.")

        instances = []
        for entry in kitsu_entries:
            if self.check_access(entry):
                try:
                    (instance, is_updated) = self.model.create_from_import(
                        entry
                    )
                    if is_updated:
                        self.emit_event("update", entry)
                    else:
                        self.emit_event("new", entry)
                except IntegrityError as exc:
                    raise WrongParameterException(exc.orig)
                instances.append(instance)
        return fields.serialize_models(instances)

    def emit_event(self, event_type, entry):
        pass

    def check_access(self, entry):
        return permissions.has_admin_permissions()


class ImportKitsuCommentsResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Entity)
        user_service.check_project_manager_access()

    @jwt_required()
    def post(self):
        """
        Import kitsu comments
        ---
        description: Import Kitsu comments. Send a list of Kitsu comment
          entries in the JSON body. Returns created or updated comments
          linked to tasks.
        tags:
          - Import
        requestBody:
          required: true
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
                      description: Kitsu ID of the comment
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    object_id:
                      type: string
                      format: uuid
                      description: Task ID the comment is linked to
                      example: b24a6ea4-ce75-4665-a070-57453082c25
                    text:
                      type: string
                      description: Comment text
                      example: "This is a comment"
                    person_id:
                      type: string
                      format: uuid
                      description: Person who created the comment
                      example: c24a6ea4-ce75-4665-a070-57453082c25
              example:
                - id: a24a6ea4-ce75-4665-a070-57453082c25
                  object_id: b24a6ea4-ce75-4665-a070-57453082c25
                  text: "This is a comment"
                  person_id: c24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Comments imported successfully
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
                        description: Comment unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      text:
                        type: string
                        description: Comment text
                        example: "This is a comment"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Update timestamp
                        example: "2024-01-15T11:00:00Z"
          400:
            description: Invalid request body or missing required fields
        """
        return super().post()

    def check_access(self, entry):
        try:
            task = tasks_service.get_task(str(entry.object_id))
            project_id = task["project_id"]
            user_service.check_project_access(project_id)
        except BaseException:
            return False
        return True

    def emit_event(self, event_type, entry):
        task = tasks_service.get_task(str(entry.object_id))
        project_id = task["project_id"]
        events.emit(
            "comment:%s" % event_type,
            {"comment_id": entry.id},
            project_id=project_id,
        )


class ImportKitsuEntitiesResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Entity)

    @jwt_required()
    def post(self):
        """
        Import kitsu entities
        ---
        description: Import Kitsu entities (assets, shots, sequences, etc.).
          Send a list of Kitsu entity entries in the JSON body. Returns
          created or updated entities.
        tags:
          - Import
        requestBody:
          required: true
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
                      description: Kitsu ID of the entity
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Entity name
                      example: "Asset01"
                    project_id:
                      type: string
                      format: uuid
                      description: Project ID
                      example: b24a6ea4-ce75-4665-a070-57453082c25
                    entity_type_id:
                      type: string
                      format: uuid
                      description: Entity type ID
                      example: c24a6ea4-ce75-4665-a070-57453082c25
              example:
                - id: a24a6ea4-ce75-4665-a070-57453082c25
                  name: "Asset01"
                  project_id: b24a6ea4-ce75-4665-a070-57453082c25
                  entity_type_id: c24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Entities imported successfully
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
                        description: Entity unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Entity name
                        example: "Asset01"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Update timestamp
                        example: "2024-01-15T11:00:00Z"
          400:
            description: Invalid request body or missing required fields
        """
        return super().post()

    def check_access(self, entry):
        try:
            project_id = entry["project_id"]
            user_service.check_project_access(project_id)
        except BaseException:
            return False
        return True

    def emit_event(self, event_type, entry):
        project_id = entry["project_id"]
        name = shots_service.get_base_entity_type_name(entry)
        events.emit(
            "%s:%s" % (name.lower(), event_type),
            {"%s_id" % name: entry["id"]},
            project_id=project_id,
        )


class ImportKitsuProjectsResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Project)

    @jwt_required()
    def post(self):
        """
        Import kitsu projects
        ---
        description: Import Kitsu projects. Send a list of Kitsu project
          entries in the JSON body. Returns created or updated projects.
        tags:
          - Import
        requestBody:
          required: true
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
                      description: Kitsu ID of the project
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
                    production_type:
                      type: string
                      description: Production type
                      example: "tvshow"
              example:
                - id: a24a6ea4-ce75-4665-a070-57453082c25
                  name: "My Project"
                  production_type: "tvshow"
        responses:
          200:
            description: Projects imported successfully
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
                        description: Project unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Project name
                        example: "My Project"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Update timestamp
                        example: "2024-01-15T11:00:00Z"
          400:
            description: Invalid request body or missing required fields
        """
        return super().post()

    def emit_event(self, event_type, entry):
        events.emit("project:%s" % event_type, project_id=entry["id"])


class ImportKitsuTasksResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Task)

    @jwt_required()
    def post(self):
        """
        Import kitsu tasks
        ---
        description: Import Kitsu tasks. Send a list of Kitsu task entries in
          the JSON body. Returns created or updated tasks.
        tags:
          - Import
        requestBody:
          required: true
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
                      description: Kitsu ID of the task
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Task name
                      example: "Modeling"
                    project_id:
                      type: string
                      format: uuid
                      description: Project ID
                      example: b24a6ea4-ce75-4665-a070-57453082c25
                    entity_id:
                      type: string
                      format: uuid
                      description: Entity ID the task is linked to
                      example: c24a6ea4-ce75-4665-a070-57453082c25
                    task_type_id:
                      type: string
                      format: uuid
                      description: Task type ID
                      example: d24a6ea4-ce75-4665-a070-57453082c25
              example:
                - id: a24a6ea4-ce75-4665-a070-57453082c25
                  name: "Modeling"
                  project_id: b24a6ea4-ce75-4665-a070-57453082c25
                  entity_id: c24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id: d24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Tasks imported successfully
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
                        description: Task unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Task name
                        example: "Modeling"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Update timestamp
                        example: "2024-01-15T11:00:00Z"
          400:
            description: Invalid request body or missing required fields
        """
        return super().post()

    def check_access(self, entry):
        try:
            project_id = entry["project_id"]
            user_service.check_project_access(project_id)
        except BaseException:
            return False
        return True

    def emit_event(self, event_type, entry):
        events.emit("task:%s" % event_type, project_id=entry["project_id"])


class ImportKitsuEntityLinksResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, EntityLink)

    @jwt_required()
    def post(self):
        """
        Import kitsu entity links
        ---
        description: Import Kitsu entity links (casting links). Send a list
          of Kitsu entity link entries in the JSON body. Returns created or
          updated entity links.
        tags:
          - Import
        requestBody:
          required: true
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
                      description: Kitsu ID of the entity link
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    entity_in_id:
                      type: string
                      format: uuid
                      description: Source entity ID
                      example: b24a6ea4-ce75-4665-a070-57453082c25
                    entity_out_id:
                      type: string
                      format: uuid
                      description: Target entity ID
                      example: c24a6ea4-ce75-4665-a070-57453082c25
              example:
                - id: a24a6ea4-ce75-4665-a070-57453082c25
                  entity_in_id: b24a6ea4-ce75-4665-a070-57453082c25
                  entity_out_id: c24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Entity links imported successfully
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
                        description: Entity link unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      entity_in_id:
                        type: string
                        format: uuid
                        description: Source entity ID
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_out_id:
                        type: string
                        format: uuid
                        description: Target entity ID
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Update timestamp
                        example: "2024-01-15T11:00:00Z"
          400:
            description: Invalid request body or missing required fields
        """
        return super().post()

    def check_access(self, entry):
        try:
            entity = entities_service.get_entity(entry["entity_in_id"])
            project_id = entity["project_id"]
            user_service.check_project_access(project_id)
        except BaseException:
            return False
        return True

    def emit_event(self, event_type, entry):
        entity = entities_service.get_entity(entry["entity_in_id"])
        project_id = entity["project_id"]
        events.emit("entity-link:%s" % event_type, project_id=project_id)
