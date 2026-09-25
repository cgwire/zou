from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app import db
from zou.app.models.project import Project
from zou.app.models.project import ProjectPersonLink
from zou.app.models.person import Person

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunProjectConnectionsResource(BaseImportShotgunResource):
    def __init__(self):
        BaseImportShotgunResource.__init__(self)

    @jwt_required()
    def post(self):
        """
        Import shotgun project connections
        ---
        description: Import Shotgun project-user connections. Send a list of
          Shotgun project connection entries in the JSON body. Returns
          projects with team members added.
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
                      description: Shotgun ID of the connection
                      example: 12345
                    project:
                      type: object
                      description: Project information
                      properties:
                        id:
                          type: integer
                          example: 11111
                    user:
                      type: object
                      description: User information
                      properties:
                        id:
                          type: integer
                          example: 22222
              example:
                - id: 12345
                  project:
                    id: 11111
                  user:
                    id: 22222
        responses:
          200:
            description: Project connections imported successfully
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
                      team:
                        type: array
                        description: Team member IDs
                        items:
                          type: string
                          format: uuid
                        example:
                          - b35b7fb5-df86-5776-b181-68564193d36
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
            description: Invalid request body or data format error
        """
        return super().post()

    def prepare_import(self):
        pass

    def extract_data(self, sg_project_user_connection):
        sg_project = sg_project_user_connection["project"]
        sg_user = sg_project_user_connection["user"]

        data = {
            "shotgun_id": sg_project_user_connection["id"],
            "project_shotgun_id": sg_project["id"],
            "person_shotgun_id": sg_user["id"],
        }
        return data

    def import_entry(self, data):
        project_person_link = ProjectPersonLink.query.filter(
            ProjectPersonLink.shotgun_id == data["shotgun_id"]
        ).first()

        if project_person_link is None:
            project = Project.get_by(shotgun_id=data["project_shotgun_id"])
            person = Person.get_by(shotgun_id=data["person_shotgun_id"])

            if project is not None and person is not None:
                project.team.append(person)
                project.save()
                # Record the Shotgun id on the link so the next import and
                # the removal route find it instead of duplicating it.
                link = ProjectPersonLink.query.filter_by(
                    project_id=project.id, person_id=person.id
                ).first()
                link.shotgun_id = data["shotgun_id"]
                db.session.commit()
                current_app.logger.info(
                    f"Project Person Link created: {project}"
                )
        else:
            project = Project.get(project_person_link.project_id)
            current_app.logger.info(
                f"Project Person Link already there: {project}"
            )

        return project


class ImportRemoveShotgunProjectConnectionResource(
    ImportRemoveShotgunBaseResource
):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, ProjectPersonLink)

    def get_instance(self, sg_model):
        # ProjectPersonLink is a bare link table without BaseMixin, so the
        # generic get_by lookup does not exist on it.
        return ProjectPersonLink.query.filter_by(
            shotgun_id=sg_model["id"]
        ).first()

    def delete_instance(self, instance):
        db.session.delete(instance)
        db.session.commit()
        return True

    @jwt_required()
    def post(self):
        """
        Remove shotgun project connection
        ---
        description: Remove a Shotgun project-user connection from the
          database. Provide the Shotgun entry ID in the JSON body.
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
                    description: Shotgun ID of the connection to remove
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
                      description: ID of the removed connection, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
