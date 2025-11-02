from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus

from zou.app.services import file_tree_service, projects_service

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)

from zou.app.services.exception import WrongFileTreeFileException


class ImportShotgunProjectsResource(BaseImportShotgunResource):
    def __init__(self):
        BaseImportShotgunResource.__init__(self)

    @jwt_required()
    def post(self):
        """
        Import shotgun projects
        ---
        description: Import Shotgun projects. Send a list of Shotgun project
          entries in the JSON body. Returns created or updated projects with
          custom fields preserved.
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
                      description: Shotgun ID of the project
                      example: 12345
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
                    sg_status:
                      type: string
                      description: Project status
                      example: "Active"
              example:
                - id: 12345
                  name: "My Project"
                  sg_status: "Active"
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
                      data:
                        type: object
                        description: Custom project data
                        example: {}
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
        self.project_status_names = self.extract_status_names(self.sg_entries)
        projects_service.save_project_status(self.project_status_names)
        self.project_status_map = ProjectStatus.get_id_map(field="name")

    def extract_status_names(self, sg_projects):
        return {x["sg_status"] for x in sg_projects}

    def extract_data(self, sg_project):
        sg_project_status = sg_project["sg_status"]
        custom_fields = self.extract_custom_data(sg_project)
        project_status_id = self.project_status_map.get(
            sg_project_status, None
        )

        data = {
            "project_status_id": project_status_id,
            "name": sg_project["name"],
            "shotgun_id": sg_project["id"],
            "data": {},
        }

        data["data"] = custom_fields
        return data

    def is_custom_field(self, name):
        non_custom_fields = ["sg_status"]
        return name[:3] == "sg_" and name not in non_custom_fields

    def import_entry(self, data):
        project = Project.get_by(shotgun_id=data["shotgun_id"])

        if project is None:
            project = Project(**data)

            tree_name = current_app.config["DEFAULT_FILE_TREE"]
            try:
                project.file_tree = file_tree_service.get_tree_from_file(
                    tree_name
                )
            except WrongFileTreeFileException:
                current_app.logger.error(
                    "Can't find default file to set project file tree. Set "
                    "an empty file tree instead."
                )
                project.file_tree = {}

            project.save()
            current_app.logger.info("Project created: %s" % project)

        else:
            project.update(data)
            current_app.logger.info("Project updated: %s" % project)

        return project


class ImportRemoveShotgunProjectResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, Project)

    @jwt_required()
    def post(self):
        """
        Remove shotgun project
        ---
        description: Remove a Shotgun project from the database. Provide the
          Shotgun entry ID in the JSON body.
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
                    description: Shotgun ID of the project to remove
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
                      description: ID of the removed project, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
