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

    def emit_event(self, event_type, entry):
        events.emit("project:%s" % event_type, project_id=entry["id"])


class ImportKitsuTasksResource(BaseImportKitsuResource):
    def __init__(self):
        BaseImportKitsuResource.__init__(self, Task)

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
