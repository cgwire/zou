import datetime

from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.task import Task
from zou.app.models.comment import Comment
from zou.app.models.person import Person

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunNotesResource(BaseImportShotgunResource):
    @jwt_required()
    def post(self):
        """
        Import shotgun notes
        ---
        description: Import Shotgun notes (comments) linked to tasks. Send a
          list of Shotgun note entries in the JSON body. Only notes linked to
          tasks are imported. Returns created or updated comments.
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
                      type: integer
                      description: Shotgun ID of the note
                      example: 12345
                    content:
                      type: string
                      description: Note content
                      example: "This is a comment"
                    tasks:
                      type: array
                      description: Linked tasks
                      items:
                        type: object
                        properties:
                          id:
                            type: integer
                            example: 67890
                    user:
                      type: object
                      description: User who created the note
                      properties:
                        id:
                          type: integer
                          example: 11111
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2024-01-15T10:30:00Z"
              example:
                - id: 12345
                  content: "This is a comment"
                  tasks:
                    - id: 67890
                  user:
                    id: 11111
                  created_at: "2024-01-15T10:30:00Z"
        responses:
          200:
            description: Notes imported successfully
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
          400:
            description: Invalid request body or data format error
        """
        return super().post()

    def prepare_import(self):
        self.person_ids = Person.get_id_map()

    def filtered_entries(self):
        return (x for x in self.sg_entries if self.is_note_linked_to_task(x))

    def is_note_linked_to_task(self, sg_note):
        if len(sg_note["tasks"]) == 0:
            return False

        task = Task.get_by(shotgun_id=sg_note["tasks"][0]["id"])
        return task is not None

    def extract_data(self, sg_note):
        task = Task.get_by(shotgun_id=sg_note["tasks"][0]["id"])
        person_id = self.person_ids.get(sg_note["user"]["id"], None)
        date = datetime.datetime.strptime(
            sg_note["created_at"][:19], "%Y-%m-%dT%H:%M:%S"
        )

        return {
            "text": sg_note["content"],
            "shotgun_id": sg_note["id"],
            "object_id": task.id,
            "object_type": "Task",
            "person_id": person_id,
            "created_at": date,
        }

    def import_entry(self, data):
        comment = Comment.get_by(shotgun_id=data["shotgun_id"])
        if comment is None:
            comment = Comment(**data)
            comment.save()
            current_app.logger.info("Comment created: %s" % comment)

        else:
            comment.update(data)
            current_app.logger.info("Comment updated: %s" % comment)
        return comment


class ImportRemoveShotgunNoteResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, Comment)

    @jwt_required()
    def post(self):
        """
        Remove shotgun note
        ---
        description: Remove a Shotgun note (comment) from the database.
          Provide the Shotgun entry ID in the JSON body.
        tags:
          - Import
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - id
                properties:
                  id:
                    type: integer
                    description: Shotgun ID of the note to remove
                    example: 12345
              example:
                id: 12345
        responses:
          200:
            description: Removal result returned
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: boolean
                      description: Whether the removal was successful
                      example: true
                    removed_instance_id:
                      type: string
                      format: uuid
                      description: ID of the removed note, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
