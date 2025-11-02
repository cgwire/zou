from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.preview_file import PreviewFile
from zou.app.models.person import Person


from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunVersionsResource(BaseImportShotgunResource):
    def __init__(self):
        BaseImportShotgunResource.__init__(self)

    @jwt_required()
    def post(self):
        """
        Import shotgun versions
        ---
        description: Import Shotgun versions (preview files). Send a list of
          Shotgun version entries in the JSON body. Only versions linked to
          tasks are imported. Returns created or updated preview files.
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
                      description: Shotgun ID of the version
                      example: 12345
                    code:
                      type: string
                      description: Version code
                      example: "v001"
                    description:
                      type: string
                      description: Version description
                      example: "First version"
                    sg_task:
                      type: object
                      description: Task information
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
                    sg_uploaded_movie:
                      type: object
                      description: Uploaded movie information
                      properties:
                        url:
                          type: string
                          example: "https://example.com/movie.mp4"
                        name:
                          type: string
                          example: "movie.mp4"
              example:
                - id: 12345
                  code: "v001"
                  description: "First version"
                  sg_task:
                    id: 11111
                  user:
                    id: 22222
                  sg_uploaded_movie:
                    url: "https://example.com/movie.mp4"
                    name: "movie.mp4"
        responses:
          200:
            description: Versions imported successfully
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
                        description: Preview file unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Preview file name
                        example: "v001"
                      description:
                        type: string
                        description: Preview file description
                        example: "First version"
                      source:
                        type: string
                        description: Source of the preview
                        example: "Shotgun"
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
        self.person_ids = Person.get_id_map()

    def filtered_entries(self):
        return (
            x for x in self.sg_entries if self.is_version_linked_to_task(x)
        )

    def is_version_linked_to_task(self, version):
        return version["sg_task"] is not None

    def extract_data(self, sg_version):
        data = {
            "name": sg_version["code"],
            "shotgun_id": sg_version["id"],
            "description": sg_version["description"],
            "source": "Shotgun",
        }

        if "user" in sg_version and sg_version["user"] is not None:
            data["person_id"] = self.person_ids.get(
                sg_version["user"]["id"], None
            )

        if sg_version["sg_task"] is not None:
            data["task_id"] = self.get_task_id(sg_version["sg_task"]["id"])

        if sg_version["sg_uploaded_movie"] is not None:
            data["uploaded_movie_url"] = sg_version["sg_uploaded_movie"]["url"]
            data["uploaded_movie_name"] = sg_version["sg_uploaded_movie"][
                "name"
            ]

        return data

    def import_entry(self, data):
        preview_file = PreviewFile.get_by(shotgun_id=data["shotgun_id"])
        if preview_file is None:
            preview_file = PreviewFile.get_by(
                name=data["name"], task_id=data["task_id"]
            )

        if preview_file is None:
            preview_file = PreviewFile(**data)
            preview_file.save()
            current_app.logger.info("PreviewFile created: %s" % preview_file)
        else:
            preview_file.update(data)
            current_app.logger.info("PreviewFile updated: %s" % preview_file)
        return preview_file


class ImportRemoveShotgunVersionResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, PreviewFile)

    @jwt_required()
    def post(self):
        """
        Remove shotgun version
        ---
        description: Remove a Shotgun version (preview file) from the
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
                    description: Shotgun ID of the version to remove
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
                      description: ID of the removed version, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
