import os

from flask import request, abort, current_app
from flask import send_file as flask_send_file
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from flask_fs.errors import FileNotFound
from zou.app import config

from zou.app.mixin import ArgsMixin
from zou.app.utils import fs, date_helpers
from zou.app.stores import file_store
from zou.app.services import (
    file_tree_service,
    files_service,
    persons_service,
    projects_service,
    assets_service,
    tasks_service,
    entities_service,
    user_service,
)

from zou.app.services.exception import (
    WorkingFileNotFoundException,
    OutputTypeNotFoundException,
    PersonNotFoundException,
    WrongFileTreeFileException,
    MalformedFileTreeException,
    EntryAlreadyExistsException,
)


def send_storage_file(
    working_file_id,
    as_attachment=False,
    max_age=config.CLIENT_CACHE_MAX_AGE,
    last_modified=None,
):
    """
    Send file from storage. If it's not a local storage, cache the file in
    a temporary folder before sending it. It accepts conditional headers.
    """
    prefix = "working"
    extension = "tmp"
    get_local_path = file_store.get_local_file_path
    open_file = file_store.open_file
    mimetype = "application/octet-stream"

    file_path = fs.get_file_path_and_file(
        config, get_local_path, open_file, prefix, working_file_id, extension
    )

    download_name = ""
    if as_attachment:
        download_name = working_file_id

    try:
        return flask_send_file(
            file_path,
            conditional=True,
            mimetype=mimetype,
            as_attachment=as_attachment,
            download_name=download_name,
            max_age=max_age,
            last_modified=last_modified,
        )
    except IOError as e:
        current_app.logger.error(e)
        return (
            {
                "error": True,
                "message": "Working file not found for: %s" % working_file_id,
            },
            404,
        )
    except FileNotFound:
        return (
            {
                "error": True,
                "message": "Working file not found for: %s" % working_file_id,
            },
            404,
        )


class WorkingFileFileResource(Resource):

    def check_access(self, working_file_id):
        working_file = files_service.get_working_file(working_file_id)
        user_service.check_task_access(working_file["task_id"])
        return working_file

    def save_uploaded_file_in_temporary_folder(self, working_file_id):
        uploaded_file = request.files["file"]
        tmp_folder = current_app.config["TMP_DIR"]
        file_name = "working-file-%s" % working_file_id
        file_path = os.path.join(tmp_folder, file_name)
        uploaded_file.save(file_path)
        return file_path

    @jwt_required()
    def get(self, working_file_id):
        """
        Download working file
        ---
        description: Download a working file from storage. Returns the file
          content with appropriate headers for caching and attachment.
        tags:
        - Files
        parameters:
          - in: path
            name: working_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Working file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Working file downloaded successfully
            content:
              image/png:
                schema:
                  type: string
                  format: binary
                  description: PNG image file
                  example: "binary data"
              image/jpg:
                schema:
                  type: string
                  format: binary
                  description: JPEG image file
                  example: "binary data"
              image/gif:
                schema:
                  type: string
                  format: binary
                  description: GIF image file
                  example: "binary data"
              application/octet-stream:
                schema:
                  type: string
                  format: binary
                  description: Binary file content
                  example: "binary data"
        """
        working_file = self.check_access(working_file_id)
        return send_storage_file(
            working_file_id,
            last_modified=date_helpers.get_datetime_from_string(
                working_file["updated_at"]
            ),
        )

    @jwt_required()
    def post(self, working_file_id):
        """
        Store working file
        ---
        description: Store a working file in the file storage system. Uploads
          the file content and associates it with the working file record.
        tags:
        - Files
        parameters:
          - in: path
            name: working_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Working file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            multipart/form-data:
              schema:
                type: object
                required:
                  - file
                properties:
                  file:
                    type: string
                    format: binary
                    description: Working file to upload
                    example: "file content"
        responses:
          201:
            description: Working file stored successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Working file unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Working file name
                      example: "main"
                    path:
                      type: string
                      description: Working file path
                      example: "/project/asset/working/main_v001.blend"
                    revision:
                      type: integer
                      description: Working file revision
                      example: 1
                    task_id:
                      type: string
                      format: uuid
                      description: Task identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        working_file = self.check_access(working_file_id)
        file_path = self.save_uploaded_file_in_temporary_folder(
            working_file_id
        )
        file_store.add_file("working", working_file_id, file_path)
        os.remove(file_path)
        return working_file, 201


class WorkingFilePathResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, task_id):
        """
        Generate working file path
        ---
        description: Generate a working file path from file tree template based
          on task parameters. Revision can be computed automatically if not
          provided.
        tags:
        - Files
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    description: File name
                    default: main
                    example: "main"
                  mode:
                    type: string
                    description: File mode
                    default: working
                    example: "working"
                  software_id:
                    type: string
                    format: uuid
                    description: Software identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  comment:
                    type: string
                    description: File comment
                    example: "Updated lighting"
                  revision:
                    type: integer
                    description: File revision number
                    example: 1
                  separator:
                    type: string
                    description: Path separator
                    default: /
                    example: "/"
        responses:
          200:
            description: Working file path generated successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    path:
                      type: string
                      description: Generated file path
                      example: "/project/asset/working/main_v001.blend"
                    name:
                      type: string
                      description: Generated file name
                      example: "main_v001.blend"
          400:
            description: Malformed file tree
        """
        (
            name,
            mode,
            software_id,
            comment,
            revision,
            separator,
        ) = self.get_arguments()

        try:
            task = tasks_service.get_task(task_id)
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["entity_id"])

            software = files_service.get_software(software_id)
            is_revision_set_by_user = revision != 0
            if not is_revision_set_by_user:
                revision = files_service.get_next_working_file_revision(
                    task_id, name
                )
            file_path = file_tree_service.get_working_folder_path(
                task,
                mode=mode,
                software=software,
                name=name,
                sep=separator,
                revision=revision,
            )
            file_name = file_tree_service.get_working_file_name(
                task,
                mode=mode,
                revision=revision,
                software=software,
                name=name,
            )
        except MalformedFileTreeException as exception:
            return (
                {"message": str(exception), "received_data": request.json},
                400,
            )

        return {"path": file_path, "name": file_name}, 200

    def get_arguments(self):
        maxsoft = files_service.get_or_create_software(
            "3ds Max", "max", ".max"
        )

        args = self.get_args(
            [
                ("name", "main"),
                ("mode", "working"),
                ("software_id", maxsoft["id"]),
                ("comment", ""),
                ("revision", 0),
                ("sep", "/"),
            ]
        )

        return (
            args["name"],
            args["mode"],
            args["software_id"],
            args["comment"],
            args["revision"],
            args["sep"],
        )


class EntityOutputFilePathResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, entity_id):
        """
        Generate entity output file path
        ---
        description: Generate an output file path from file tree template
          based on entity parameters. Revision can be computed automatically
          if not provided.
        tags:
        - Files
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - output_type_id
                  - task_type_id
                properties:
                  name:
                    type: string
                    description: File name
                    default: main
                    example: "main"
                  mode:
                    type: string
                    description: File mode
                    default: output
                    example: "output"
                  output_type_id:
                    type: string
                    format: uuid
                    description: Output type identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id:
                    type: string
                    format: uuid
                    description: Task type identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  extension:
                    type: string
                    description: File extension
                    example: ".mp4"
                  representation:
                    type: string
                    description: File representation
                    example: "mp4"
                  revision:
                    type: integer
                    description: File revision number
                    example: 1
                  separator:
                    type: string
                    description: Path separator
                    default: /
                    example: "/"
        responses:
          200:
            description: Output file path generated successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    folder_path:
                      type: string
                      description: Generated folder path
                      example: "/project/asset/output"
                    file_name:
                      type: string
                      description: Generated file name
                      example: "main_v001.mp4"
          400:
            description: Malformed file tree
        """
        args = self.get_arguments()
        try:
            entity = entities_service.get_entity(entity_id)
            user_service.check_project_access(entity["project_id"])
            user_service.check_entity_access(entity_id)
            output_type = files_service.get_output_type(args["output_type_id"])
            task_type = tasks_service.get_task_type(args["task_type_id"])
            entity = entities_service.get_entity(entity_id)

            is_revision_set_by_user = args["revision"] != 0
            if not is_revision_set_by_user:
                revision = files_service.get_next_output_file_revision(
                    entity_id, args["name"]
                )
            else:
                revision = args["revision"]

            folder_path = file_tree_service.get_output_folder_path(
                entity,
                mode=args["mode"],
                output_type=output_type,
                task_type=task_type,
                name=args["name"],
                representation=args["representation"],
                sep=args["separator"],
                revision=args["revision"],
            )
            file_name = file_tree_service.get_output_file_name(
                entity,
                mode=args["mode"],
                revision=revision,
                output_type=output_type,
                task_type=task_type,
                name=args["name"],
            )
        except MalformedFileTreeException as exception:
            return (
                {"message": str(exception), "received_data": request.json},
                400,
            )

        return {"folder_path": folder_path, "file_name": file_name}, 200

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "main", False),
                ("mode", "output", False),
                ("output_type_id", None, True),
                ("task_type_id", None, True),
                ("revision", 0, False),
                ("extension", "", False),
                ("representation", "", False),
                ("separator", "/", False),
            ]
        )


class InstanceOutputFilePathResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, asset_instance_id, temporal_entity_id):
        """
        Generate instance output file path
        ---
        description: Generate an output file path from file tree template
          based on asset instance parameters. Revision can be computed
          automatically if not provided.
        tags:
        - Files
        parameters:
          - in: path
            name: asset_instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: temporal_entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Temporal entity unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - output_type_id
                  - task_type_id
                properties:
                  name:
                    type: string
                    description: File name
                    default: main
                    example: "main"
                  mode:
                    type: string
                    description: File mode
                    default: output
                    example: "output"
                  output_type_id:
                    type: string
                    format: uuid
                    description: Output type identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id:
                    type: string
                    format: uuid
                    description: Task type identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
                  extension:
                    type: string
                    description: File extension
                    example: ".mp4"
                  representation:
                    type: string
                    description: File representation
                    example: "mp4"
                  revision:
                    type: integer
                    description: File revision number
                    example: 1
                  separator:
                    type: string
                    description: Path separator
                    default: /
                    example: "/"
        responses:
          200:
            description: Output file path generated successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    folder_path:
                      type: string
                      description: Generated folder path
                      example: "/project/asset/instance/output"
                    file_name:
                      type: string
                      description: Generated file name
                      example: "main_v001.mp4"
        """
        args = self.get_arguments()

        try:
            asset_instance = assets_service.get_asset_instance(
                asset_instance_id
            )
            entity = entities_service.get_entity(temporal_entity_id)
            asset = assets_service.get_asset(asset_instance["asset_id"])
            output_type = files_service.get_output_type(args["output_type_id"])
            task_type = tasks_service.get_task_type(args["task_type_id"])
            user_service.check_project_access(asset["project_id"])
            user_service.check_entity_access(asset["id"])

            folder_path = file_tree_service.get_instance_folder_path(
                asset_instance,
                entity,
                output_type=output_type,
                task_type=task_type,
                mode=args["mode"],
                name=args["name"],
                representation=args["representation"],
                revision=args["revision"],
                sep=args["separator"],
            )
            file_name = file_tree_service.get_instance_file_name(
                asset_instance,
                entity,
                output_type=output_type,
                task_type=task_type,
                mode=args["mode"],
                name=args["name"],
                revision=args["revision"],
            )
        except MalformedFileTreeException as exception:
            return (
                {"message": str(exception), "received_data": request.json},
                400,
            )

        return {"folder_path": folder_path, "file_name": file_name}, 200

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "main", False),
                ("mode", "output", False),
                ("output_type_id", None, True),
                ("task_type_id", None, True),
                ("revision", 0, False),
                ("extension", "", False),
                ("representation", "", False),
                ("separator", "/", False),
            ]
        )


class LastWorkingFilesResource(Resource):

    @jwt_required()
    def get(self, task_id):
        """
        Get last working files
        ---
        description: Retrieve the last working file revisions for each file
          name for a given task. Returns the most recent version of each
          working file.
        tags:
        - Files
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Last working file revisions for each file name
            content:
              application/json:
                schema:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Working file unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Working file name
                        example: "main"
                      revision:
                        type: integer
                        description: Working file revision
                        example: 3
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
        """
        result = {}
        user_service.check_task_access(task_id)
        result = files_service.get_last_working_files_for_task(task_id)

        return result


class TaskWorkingFilesResource(Resource):

    @jwt_required()
    def get(self, task_id):
        """
        Get task working files
        ---
        description: Retrieve all working file revisions for a given task.
          Returns complete list of working files with their revisions.
        tags:
        - Files
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All working file revisions for given task
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
                        description: Working file unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Working file name
                        example: "main"
                      revision:
                        type: integer
                        description: Working file revision
                        example: 1
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        result = {}
        user_service.check_task_access(task_id)
        result = files_service.get_working_files_for_task(task_id)

        return result


class NewWorkingFileResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, task_id):
        """
        Create new working file
        ---
        description: Create a new working file for a task. Working files are
          versioned files used by artists to produce output files. Each
          file requires a comment and generates a path based on file tree
          template.
        tags:
        - Files
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                properties:
                  name:
                    type: string
                    description: Working file name
                    example: "main"
                  mode:
                    type: string
                    description: Working file mode
                    default: working
                    example: "working"
                  description:
                    type: string
                    description: Working file description
                    example: "Main character model"
                  comment:
                    type: string
                    description: Working file comment
                    example: "Updated lighting and materials"
                  person_id:
                    type: string
                    format: uuid
                    description: Person identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  software_id:
                    type: string
                    format: uuid
                    description: Software identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  revision:
                    type: integer
                    description: Working file revision
                    example: 1
                  sep:
                    type: string
                    description: Path separator
                    default: /
                    example: "/"
        responses:
          201:
            description: New working file created successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Working file unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    name:
                      type: string
                      description: Working file name
                      example: "main"
                    path:
                      type: string
                      description: Working file path
                      example: "/project/asset/working/main_v001.blend"
                    revision:
                      type: integer
                      description: Working file revision
                      example: 1
                    task_id:
                      type: string
                      format: uuid
                      description: Task identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        (
            name,
            mode,
            description,
            comment,
            person_id,
            software_id,
            revision,
            sep,
        ) = self.get_arguments()

        try:
            task = tasks_service.get_task(task_id)
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["entity_id"])
            software = files_service.get_software(software_id)
            tasks_service.assign_task(
                task_id, persons_service.get_current_user()["id"]
            )

            if revision == 0:
                revision = files_service.get_next_working_revision(
                    task_id, name
                )

            path = self.build_path(task, name, revision, software, sep, mode)

            working_file = files_service.create_new_working_revision(
                task_id,
                person_id,
                software_id,
                name=name,
                path=path,
                comment=comment,
                revision=revision,
            )
        except EntryAlreadyExistsException:
            return {"error": "The given working file already exists."}, 400

        return working_file, 201

    def build_path(self, task, name, revision, software, sep, mode):
        folder_path = file_tree_service.get_working_folder_path(
            task, name=name, software=software, mode=mode, revision=revision
        )
        file_name = file_tree_service.get_working_file_name(
            task, name=name, software=software, revision=revision, mode=mode
        )
        return "%s%s%s" % (folder_path, sep, file_name)

    def get_arguments(self):
        person = persons_service.get_current_user()
        maxsoft = files_service.get_or_create_software(
            "3ds Max", "max", ".max"
        )

        args = self.get_args(
            [
                {
                    "name": "name",
                    "help": "The asset name is required.",
                    "required": True,
                },
                ("description", ""),
                ("mode", "working"),
                ("comment", ""),
                ("person_id", person["id"]),
                ("software_id", maxsoft["id"]),
                {"name": "revision", "default": 0, "type": int},
                ("sep", "/"),
            ]
        )

        return (
            args["name"],
            args["mode"],
            args["description"],
            args["comment"],
            args["person_id"],
            args["software_id"],
            args["revision"],
            args["sep"],
        )


class ModifiedFileResource(Resource):

    @jwt_required()
    def put(self, working_file_id):
        """
        Update working file modification date
        ---
        description: Update the modification date of a working file to the
          current timestamp. Used to track when the file was last modified.
        tags:
        - Files
        parameters:
          - in: path
            name: working_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Working file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Working file modification date updated successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Working file unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    updated_at:
                      type: string
                      format: date-time
                      description: Updated modification timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        working_file = files_service.get_working_file(working_file_id)
        user_service.check_task_action_access(working_file["task_id"])
        working_file = files_service.update_working_file(
            working_file_id,
            {"updated_at": date_helpers.get_utc_now_datetime()},
        )
        return working_file


class CommentWorkingFileResource(Resource, ArgsMixin):

    @jwt_required()
    def put(self, working_file_id):
        """
        Update working file comment
        ---
        description: Update the comment on a specific working file. Comments
          provide context about changes made to the working file.
        tags:
        - Files
        parameters:
          - in: path
            name: working_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Working file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - comment
                properties:
                  comment:
                    type: string
                    description: Working file comment
                    example: "Updated lighting and materials"
        responses:
          200:
            description: Working file comment updated successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Working file unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    comment:
                      type: string
                      description: Updated comment
                      example: "Updated lighting and materials"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        args = self.get_args(
            [
                {
                    "name": "comment",
                    "required": True,
                    "help": "Comment field expected.",
                }
            ]
        )

        working_file = files_service.get_working_file(working_file_id)
        user_service.check_task_action_access(working_file["task_id"])
        working_file = self.update_comment(working_file_id, args["comment"])
        return working_file

    def update_comment(self, working_file_id, comment):
        working_file = files_service.update_working_file(
            working_file_id, {"comment": comment}
        )
        return working_file


class NewEntityOutputFileResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, entity_id):
        """
        Create new entity output file
        ---
        description: Create a new output file linked to a specific entity.
          Output files are created when artists are satisfied with their
          working files. They track the source working file and require
          output type and task type for categorization. An output type is
          required for better categorization (textures, caches, ...).
          A task type can be set too to give the department related to the
          output file. The revision is automatically set.
        tags:
        - Files
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - output_type_id
                  - task_type_id
                properties:
                  name:
                    type: string
                    description: Output file name
                    example: "main"
                  mode:
                    type: string
                    description: Output file mode
                    default: output
                    example: "output"
                  output_type_id:
                    type: string
                    format: uuid
                    description: Output type identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id:
                    type: string
                    format: uuid
                    description: Task type identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  person_id:
                    type: string
                    format: uuid
                    description: Person identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  working_file_id:
                    type: string
                    format: uuid
                    description: Source working file identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  file_status_id:
                    type: string
                    format: uuid
                    description: File status identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  comment:
                    type: string
                    description: Output file comment
                    example: "Final render"
                  extension:
                    type: string
                    description: File extension
                    example: ".mp4"
                  representation:
                    type: string
                    description: File representation
                    example: "mp4"
                  revision:
                    type: integer
                    description: File revision number
                    example: 1
                  nb_elements:
                    type: integer
                    description: Number of elements
                    default: 1
                    example: 1
                  sep:
                    type: string
                    description: Path separator
                    default: /
                    example: "/"
        responses:
          201:
            description: New output file created successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Output file unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    name:
                      type: string
                      description: Output file name
                      example: "main"
                    path:
                      type: string
                      description: Output file path
                      example: "/project/asset/output/main_v001.mp4"
                    revision:
                      type: integer
                      description: Output file revision
                      example: 1
                    entity_id:
                      type: string
                      format: uuid
                      description: Entity identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        args = self.get_arguments()

        try:
            revision = int(args["revision"])

            try:
                working_file = files_service.get_working_file(
                    args["working_file_id"]
                )
                working_file_id = working_file["id"]
            except WorkingFileNotFoundException:
                working_file_id = None

            entity = entities_service.get_entity(entity_id)
            user_service.check_project_access(entity["project_id"])
            output_type = files_service.get_output_type(args["output_type_id"])
            task_type = tasks_service.get_task_type(args["task_type_id"])

            if args["person_id"] is None:
                person = persons_service.get_current_user()
            else:
                person = persons_service.get_person(args["person_id"])

            output_file = files_service.create_new_output_revision(
                entity_id,
                working_file_id,
                output_type["id"],
                person["id"],
                args["task_type_id"],
                revision=revision,
                name=args["name"],
                comment=args["comment"],
                representation=args["representation"],
                extension=args["extension"],
                nb_elements=int(args["nb_elements"]),
                file_status_id=args["file_status_id"],
            )

            output_file_dict = self.add_path_info(
                output_file,
                "output",
                entity,
                output_type,
                task_type=task_type,
                name=args["name"],
                extension=args["extension"],
                representation=args["representation"],
                separator=args["sep"],
                nb_elements=int(args["nb_elements"]),
            )
        except OutputTypeNotFoundException:
            return {"error": "Cannot find given output type."}, 400
        except PersonNotFoundException:
            return {"error": "Cannot find given person."}, 400
        except EntryAlreadyExistsException:
            return {"error": "The given output file already exists."}, 400

        return output_file_dict, 201

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "main", False),
                ("mode", "output", False),
                ("output_type_id", None, True),
                ("task_type_id", None, True),
                ("person_id", None, False),
                ("working_file_id", None, False),
                ("comment", "", True),
                ("revision", 0, False),
                ("extension", "", False),
                ("representation", "", False),
                ("nb_elements", 1, False),
                ("sep", "/", False),
                ("file_status_id", None, False),
            ]
        )

    def add_path_info(
        self,
        output_file,
        mode,
        entity,
        output_type,
        task_type=None,
        name="main",
        extension="",
        representation="",
        nb_elements=1,
        separator="/",
    ):
        folder_path = file_tree_service.get_output_folder_path(
            entity,
            mode=mode,
            output_type=output_type,
            task_type=task_type,
            revision=output_file["revision"],
            representation=representation,
            name=name,
            sep=separator,
        )
        file_name = file_tree_service.get_output_file_name(
            entity,
            mode=mode,
            revision=output_file["revision"],
            output_type=output_type,
            task_type=task_type,
            name=name,
            nb_elements=nb_elements,
        )

        output_file = files_service.update_output_file(
            output_file["id"],
            {
                "path": "%s%s%s%s"
                % (folder_path, separator, file_name, extension)
            },
        )

        output_file.update(
            {"folder_path": folder_path, "file_name": file_name}
        )

        return output_file


class NewInstanceOutputFileResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, asset_instance_id, temporal_entity_id):
        """
        Create new instance output file
        ---
        description: Create a new output file linked to an asset instance
          for a specific shot. Output files track the source working file
          and require output type and task type for categorization.
        tags:
        - Files
        parameters:
          - in: path
            name: asset_instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: temporal_entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Temporal entity unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - output_type_id
                  - task_type_id
                properties:
                  name:
                    type: string
                    description: Output file name
                    default: main
                    example: "main"
                  mode:
                    type: string
                    description: Output file mode
                    default: output
                    example: "output"
                  output_type_id:
                    type: string
                    format: uuid
                    description: Output type identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id:
                    type: string
                    format: uuid
                    description: Task type identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
                  person_id:
                    type: string
                    format: uuid
                    description: Person identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  working_file_id:
                    type: string
                    format: uuid
                    description: Source working file identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  file_status_id:
                    type: string
                    format: uuid
                    description: File status identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  is_sequence:
                    type: boolean
                    description: Whether file is a sequence
                    default: false
                    example: false
                  comment:
                    type: string
                    description: Output file comment
                    example: "Final render"
                  extension:
                    type: string
                    description: File extension
                    example: ".mp4"
                  representation:
                    type: string
                    description: File representation
                    example: "mp4"
                  revision:
                    type: integer
                    description: File revision number
                    example: 1
                  nb_elements:
                    type: integer
                    description: Number of elements
                    default: 1
                    example: 1
                  sep:
                    type: string
                    description: Path separator
                    default: /
                    example: "/"
        responses:
          201:
            description: New output file created successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Output file unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    name:
                      type: string
                      description: Output file name
                      example: "main"
                    path:
                      type: string
                      description: Output file path
                      example: "/project/asset/instance/output/main_v001.mp4"
                    revision:
                      type: integer
                      description: Output file revision
                      example: 1
                    asset_instance_id:
                      type: string
                      format: uuid
                      description: Asset instance identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    temporal_entity_id:
                      type: string
                      format: uuid
                      description: Temporal entity identifier
                      example: d57d9hd7-fh08-7998-d403-80786315f58
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        args = self.get_arguments()

        try:
            revision = int(args["revision"])
            try:
                working_file = files_service.get_working_file(
                    args["working_file_id"]
                )
                working_file_id = working_file["id"]
            except WorkingFileNotFoundException:
                working_file_id = None

            asset_instance = assets_service.get_asset_instance(
                asset_instance_id
            )
            temporal_entity = entities_service.get_entity(temporal_entity_id)

            entity = assets_service.get_asset(asset_instance["asset_id"])
            user_service.check_project_access(entity["project_id"])

            output_type = files_service.get_output_type(args["output_type_id"])
            task_type = tasks_service.get_task_type(args["task_type_id"])
            if args["person_id"] is None:
                person = persons_service.get_current_user()
            else:
                person = persons_service.get_person(args["person_id"])

            output_file = files_service.create_new_output_revision(
                asset_instance["asset_id"],
                working_file_id,
                output_type["id"],
                person["id"],
                task_type["id"],
                asset_instance_id=asset_instance["id"],
                temporal_entity_id=temporal_entity_id,
                revision=revision,
                name=args["name"],
                representation=args["representation"],
                comment=args["comment"],
                nb_elements=int(args["nb_elements"]),
                extension=args["extension"],
                file_status_id=args["file_status_id"],
            )

            output_file_dict = self.add_path_info(
                output_file,
                "output",
                asset_instance,
                temporal_entity,
                output_type,
                task_type=task_type,
                name=args["name"],
                extension=args["extension"],
                representation=args["representation"],
                nb_elements=int(args["nb_elements"]),
                separator=args["sep"],
            )
        except OutputTypeNotFoundException:
            return {"message": "Cannot find given output type."}, 400
        except PersonNotFoundException:
            return {"message": "Cannot find given person."}, 400
        except EntryAlreadyExistsException:
            return {"message": "The given output file already exists."}, 400

        return output_file_dict, 201

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "main", False),
                ("mode", "output", False),
                ("output_type_id", None, True),
                ("task_type_id", None, True),
                ("person_id", None, False),
                ("working_file_id", None, False),
                ("comment", "", True),
                ("revision", 0, False),
                ("extension", "", False),
                ("representation", "", False),
                ("is_sequence", False, False),
                ("nb_elements", 1, False),
                ("sep", "/", False),
                ("file_status_id", None, False),
            ]
        )

    def add_path_info(
        self,
        output_file,
        mode,
        asset_instance,
        temporal_entity,
        output_type,
        task_type=None,
        name="main",
        extension="",
        representation="",
        nb_elements=1,
        separator="/",
    ):
        folder_path = file_tree_service.get_instance_folder_path(
            asset_instance,
            temporal_entity,
            mode=mode,
            output_type=output_type,
            revision=output_file["revision"],
            task_type=task_type,
            representation=representation,
            name=name,
            sep=separator,
        )
        file_name = file_tree_service.get_instance_file_name(
            asset_instance,
            temporal_entity,
            mode=mode,
            revision=output_file["revision"],
            output_type=output_type,
            task_type=task_type,
            name=name,
        )

        output_file = files_service.update_output_file(
            output_file["id"],
            {
                "path": "%s%s%s%s"
                % (folder_path, separator, file_name, extension)
            },
        )

        output_file.update(
            {"folder_path": folder_path, "file_name": file_name}
        )

        return output_file


class GetNextEntityOutputFileRevisionResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, entity_id):
        """
        Get next entity output file revision
        ---
        description: Get the next revision number for an output file based
          on entity, output type, task type, and name. Used for automatic
          revision numbering.
        tags:
        - Files
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - output_type_id
                  - task_type_id
                properties:
                  name:
                    type: string
                    description: File name
                    default: main
                    example: "main"
                  output_type_id:
                    type: string
                    format: uuid
                    description: Output type identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id:
                    type: string
                    format: uuid
                    description: Task type identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Next revision number for the output file
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    next_revision:
                      type: integer
                      description: Next available revision number
                      example: 3
        """
        args = self.get_arguments()
        entity = entities_service.get_entity(entity_id)
        output_type = files_service.get_output_type(args["output_type_id"])
        task_type = tasks_service.get_task_type(args["task_type_id"])
        user_service.check_project_access(entity["project_id"])

        next_revision_number = files_service.get_next_output_file_revision(
            entity["id"], output_type["id"], task_type["id"], args["name"]
        )

        return {"next_revision": next_revision_number}, 200

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "main", False),
                ("output_type_id", None, True),
                ("task_type_id", None, True),
            ]
        )


class GetNextInstanceOutputFileRevisionResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, asset_instance_id, temporal_entity_id):
        """
        Get next instance output file revision
        ---
        description: Get the next revision number for an output file based
          on asset instance, output type, task type, and name. Used for
          automatic revision numbering.
        tags:
        - Files
        parameters:
          - in: path
            name: asset_instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: temporal_entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Temporal entity unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - output_type_id
                  - task_type_id
                properties:
                  name:
                    type: string
                    description: File name
                    default: main
                    example: "main"
                  output_type_id:
                    type: string
                    format: uuid
                    description: Output type identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id:
                    type: string
                    format: uuid
                    description: Task type identifier
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Next revision number for the instance output file
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    next_revision:
                      type: integer
                      description: Next available revision number
                      example: 2
        """
        args = self.get_arguments()

        asset_instance = assets_service.get_asset_instance(asset_instance_id)
        asset = entities_service.get_entity(asset_instance["asset_id"])
        output_type = files_service.get_output_type(args["output_type_id"])
        task_type = tasks_service.get_task_type(args["task_type_id"])
        user_service.check_project_access(asset["project_id"])

        next_revision_number = files_service.get_next_output_file_revision(
            asset["id"],
            output_type["id"],
            task_type["id"],
            args["name"],
            asset_instance_id=asset_instance["id"],
            temporal_entity_id=temporal_entity_id,
        )

        return {"next_revision": next_revision_number}, 200

    def get_arguments(self):
        return self.get_args(
            [
                ("name", "main", False),
                ("output_type_id", None, True),
                ("task_type_id", None, True),
            ]
        )


class LastEntityOutputFilesResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, entity_id):
        """
        Get last entity output files
        ---
        description: Retrieve the last revisions of output files for a given
          entity grouped by output type and file name. Returns the most
          recent version of each output file.
        tags:
        - Files
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: output_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by output type
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task type
            example: c46c8gc6-eg97-6887-c292-79675204e47
          - in: query
            name: representation
            required: false
            schema:
              type: string
            description: Filter by representation
            example: "mp4"
          - in: query
            name: file_status_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by file status
            example: d57d9hd7-fh08-7998-d403-80786315f58
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter by file name
            example: "main"
        responses:
          200:
            description: Last revisions of output files grouped by output type and file name
            content:
              application/json:
                schema:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Output file unique identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      name:
                        type: string
                        description: Output file name
                        example: "main"
                      revision:
                        type: integer
                        description: Output file revision
                        example: 2
                      path:
                        type: string
                        description: Output file path
                        example: "/project/asset/output/main_v002.mp4"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
        """
        args = self.get_args(
            [
                "output_type_id",
                "task_type_id",
                "representation",
                "file_status_id",
                "name",
            ],
        )

        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])

        return files_service.get_last_output_files_for_entity(
            entity["id"],
            output_type_id=args["output_type_id"],
            task_type_id=args["task_type_id"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
            name=args["name"],
        )


class LastInstanceOutputFilesResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, asset_instance_id, temporal_entity_id):
        """
        Get last instance output files
        ---
        description: Retrieve the last revisions of output files for a given
          instance grouped by output type and file name. Returns the most
          recent version of each output file.
        tags:
        - Files
        parameters:
          - in: path
            name: asset_instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: temporal_entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Temporal entity unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: output_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by output type
            example: c46c8gc6-eg97-6887-c292-79675204e47
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task type
            example: d57d9hd7-fh08-7998-d403-80786315f58
          - in: query
            name: file_status_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by file status
            example: e68e0ie8-gi19-8009-e514-91897426g69
          - in: query
            name: representation
            required: false
            schema:
              type: string
            description: Filter by representation
            example: "cache"
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter by file name
            example: "main"
        responses:
          200:
            description: Last revisions of output files grouped by output type and file name
            content:
              application/json:
                schema:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Output file unique identifier
                        example: f79f1jf9-hj20-9010-f625-a09008537h80
                      name:
                        type: string
                        description: Output file name
                        example: "main"
                      revision:
                        type: integer
                        description: Output file revision
                        example: 1
                      path:
                        type: string
                        description: Output file path
                        example: "/project/asset/instance/output/main_v001.mp4"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
        """
        args = self.get_args(
            [
                "output_type_id",
                "task_type_id",
                "representation",
                "file_status_id",
                "name",
            ],
        )

        asset_instance = assets_service.get_asset_instance(asset_instance_id)
        entity = entities_service.get_entity(asset_instance["asset_id"])
        user_service.check_project_access(entity["project_id"])

        return files_service.get_last_output_files_for_instance(
            asset_instance["id"],
            temporal_entity_id,
            output_type_id=args["output_type_id"],
            task_type_id=args["task_type_id"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
            name=args["name"],
        )


class EntityOutputTypesResource(Resource):

    @jwt_required()
    def get(self, entity_id):
        """
        Get entity output types
        ---
        description: Retrieve all types of output files generated for a
          given entity. Returns list of output types available for the
          entity.
        tags:
        - Files
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All types of output files generated for the entity
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
                        description: Output type unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      name:
                        type: string
                        description: Output type name
                        example: "Cache"
                      short_name:
                        type: string
                        description: Output type short name
                        example: "CACHE"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return files_service.get_output_types_for_entity(entity_id)


class InstanceOutputTypesResource(Resource):

    @jwt_required()
    def get(self, asset_instance_id, temporal_entity_id):
        """
        Get instance output types
        ---
        description: Retrieve all types of output files generated for a
          given asset instance and temporal entity. Returns list of output
          types available for the instance.
        tags:
        - Files
        parameters:
          - in: path
            name: asset_instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: temporal_entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Temporal entity unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: All types of output files generated for the instance
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
                        description: Output type unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      name:
                        type: string
                        description: Output type name
                        example: "Render"
                      short_name:
                        type: string
                        description: Output type short name
                        example: "RENDER"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
        """
        asset_instance = assets_service.get_asset_instance(asset_instance_id)
        entity = entities_service.get_entity(asset_instance["asset_id"])
        user_service.check_project_access(entity["project_id"])
        return files_service.get_output_types_for_instance(
            asset_instance_id, temporal_entity_id
        )


class EntityOutputTypeOutputFilesResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, entity_id, output_type_id):
        """
        Get entity output type files
        ---
        description: Retrieve all output files for a given entity and
          output type. Optionally filter by representation.
        tags:
        - Files
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: output_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Output type unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: representation
            required: false
            schema:
              type: string
            description: Filter by representation
            example: "mp4"
        responses:
          200:
            description: All output files for the entity and output type
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
                        description: Output file unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      name:
                        type: string
                        description: Output file name
                        example: "main"
                      revision:
                        type: integer
                        description: Output file revision
                        example: 1
                      path:
                        type: string
                        description: Output file path
                        example: "/project/asset/output/main_v001.mp4"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
        """
        representation = self.get_text_parameter("representation")

        entity = entities_service.get_entity(entity_id)
        files_service.get_output_type(output_type_id)
        user_service.check_project_access(entity["project_id"])
        output_files = (
            files_service.get_output_files_for_output_type_and_entity(
                entity_id, output_type_id, representation=representation
            )
        )

        return output_files


class InstanceOutputTypeOutputFilesResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, asset_instance_id, temporal_entity_id, output_type_id):
        """
        Get instance output type files
        ---
        description: Retrieve all output files for a given asset instance,
          temporal entity, and output type. Optionally filter by
          representation.
        tags:
        - Files
        parameters:
          - in: path
            name: asset_instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: temporal_entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Temporal entity unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: path
            name: output_type_id
            required: true
            schema:
              type: string
              format: uuid
            description: Output type unique identifier
            example: c46c8gc6-eg97-6887-c292-79675204e47
          - in: query
            name: representation
            required: false
            schema:
              type: string
            description: Filter by representation
            example: "mp4"
        responses:
          200:
            description: All output files for the asset instance and output type
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
                        description: Output file unique identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      name:
                        type: string
                        description: Output file name
                        example: "main"
                      revision:
                        type: integer
                        description: Output file revision
                        example: 1
                      path:
                        type: string
                        description: Output file path
                        example: "/project/asset/instance/output/main_v001.mp4"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
                      asset_instance_id:
                        type: string
                        format: uuid
                        description: Asset instance identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      temporal_entity_id:
                        type: string
                        format: uuid
                        description: Temporal entity identifier
                        example: f79f1jf9-hj20-9010-f625-a09008537h80
        """
        representation = self.get_text_parameter("representation")

        asset_instance = assets_service.get_asset_instance(asset_instance_id)
        asset = assets_service.get_asset(asset_instance["asset_id"])
        user_service.check_project_access(asset["project_id"])

        files_service.get_output_type(output_type_id)
        return (
            files_service.get_output_files_for_output_type_and_asset_instance(
                asset_instance_id,
                temporal_entity_id,
                output_type_id,
                representation=representation,
            )
        )


class ProjectOutputFilesResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Get project output files
        ---
        description: Retrieve all output files for a given project with
          optional filtering by output type, task type, representation,
          file status, and name.
        tags:
        - Files
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: output_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by output type
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task type
            example: c46c8gc6-eg97-6887-c292-79675204e47
          - in: query
            name: file_status_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by file status
            example: d57d9hd7-fh08-7998-d403-80786315f58
          - in: query
            name: representation
            required: false
            schema:
              type: string
            description: Filter by representation
            example: "cache"
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter by file name
            example: "main"
        responses:
          200:
            description: All output files for the project
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
                        description: Output file unique identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      name:
                        type: string
                        description: Output file name
                        example: "main"
                      revision:
                        type: integer
                        description: Output file revision
                        example: 1
                      path:
                        type: string
                        description: Output file path
                        example: "/project/asset/output/main_v001.mp4"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: f79f1jf9-hj20-9010-f625-a09008537h80
        """
        args = self.get_args(
            [
                "output_type_id",
                "task_type_id",
                "representation",
                "file_status_id",
                "name",
            ],
        )
        user_service.check_manager_project_access(project_id)

        return files_service.get_output_files_for_project(
            project_id,
            task_type_id=args["task_type_id"],
            output_type_id=args["output_type_id"],
            name=args["name"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
        )


class EntityOutputFilesResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, entity_id):
        """
        Get entity output files
        ---
        description: Retrieve all output files for a given entity with
          optional filtering by output type, task type, representation,
          file status, and name.
        tags:
        - Files
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: output_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by output type
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task type
            example: c46c8gc6-eg97-6887-c292-79675204e47
          - in: query
            name: file_status_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by file status
            example: d57d9hd7-fh08-7998-d403-80786315f58
          - in: query
            name: representation
            required: false
            schema:
              type: string
            description: Filter by representation
            example: "cache"
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter by file name
            example: "main"
        responses:
          200:
            description: All output files for the entity
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
                        description: Output file unique identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      name:
                        type: string
                        description: Output file name
                        example: "main"
                      revision:
                        type: integer
                        description: Output file revision
                        example: 1
                      path:
                        type: string
                        description: Output file path
                        example: "/project/asset/output/main_v001.mp4"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: f79f1jf9-hj20-9010-f625-a09008537h80
        """
        args = self.get_args(
            [
                "output_type_id",
                "task_type_id",
                "representation",
                "file_status_id",
                "name",
            ],
        )

        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])

        return files_service.get_output_files_for_entity(
            entity["id"],
            task_type_id=args["task_type_id"],
            output_type_id=args["output_type_id"],
            name=args["name"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
        )


class InstanceOutputFilesResource(Resource):

    @jwt_required()
    def get(self, asset_instance_id):
        """
        Get instance output files
        ---
        description: Retrieve all output files for a given asset instance
          and temporal entity with optional filtering by output type, task
          type, representation, file status, and name.
        tags:
        - Files
        parameters:
          - in: path
            name: asset_instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Asset instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: temporal_entity_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by temporal entity
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: output_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by output type
            example: c46c8gc6-eg97-6887-c292-79675204e47
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task type
            example: d57d9hd7-fh08-7998-d403-80786315f58
          - in: query
            name: file_status_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by file status
            example: e68e0ie8-gi19-8009-e514-91897426g69
          - in: query
            name: representation
            required: false
            schema:
              type: string
            description: Filter by representation
            example: "cache"
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter by file name
            example: "main"
        responses:
          200:
            description: All output files for the asset instance and temporal entity
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
                        description: Output file unique identifier
                        example: f79f1jf9-hj20-9010-f625-a09008537h80
                      name:
                        type: string
                        description: Output file name
                        example: "main"
                      revision:
                        type: integer
                        description: Output file revision
                        example: 1
                      path:
                        type: string
                        description: Output file path
                        example: "/project/asset/instance/output/main_v001.mp4"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
                      asset_instance_id:
                        type: string
                        format: uuid
                        description: Asset instance identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      temporal_entity_id:
                        type: string
                        format: uuid
                        description: Temporal entity identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
        """
        args = self.get_args(
            [
                "temporal_entity_id",
                "output_type_id",
                "task_type_id",
                "representation",
                "file_status_id",
                "name",
            ],
        )

        asset_instance = assets_service.get_asset_instance(asset_instance_id)
        asset = assets_service.get_asset(asset_instance["asset_id"])
        user_service.check_project_access(asset["project_id"])

        return files_service.get_output_files_for_instance(
            asset_instance["id"],
            temporal_entity_id=args["temporal_entity_id"],
            task_type_id=args["task_type_id"],
            output_type_id=args["output_type_id"],
            name=args["name"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
        )


class FileResource(Resource):

    @jwt_required()
    def get(self, file_id):
        """
        Get file information
        ---
        description: Retrieve information about a file that could be either
          a working file or an output file. Returns detailed file metadata
          and properties.
        tags:
        - Files
        parameters:
          - in: path
            name: file_id
            required: true
            schema:
              type: string
              format: uuid
            description: File unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: File information retrieved successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: File unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    name:
                      type: string
                      description: File name
                      example: "main"
                    path:
                      type: string
                      description: File path
                      example: "/project/asset/working/main_v001.blend"
                    revision:
                      type: integer
                      description: File revision
                      example: 1
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:00:00Z"
                    task_id:
                      type: string
                      format: uuid
                      description: Task identifier (for working files)
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    entity_id:
                      type: string
                      format: uuid
                      description: Entity identifier (for output files)
                      example: d57d9hd7-fh08-7998-d403-80786315f58
        """
        try:
            file_dict = files_service.get_working_file(file_id)
            task = tasks_service.get_task(file_dict["task_id"])
            project_id = task["project_id"]
        except WorkingFileNotFoundException:
            file_dict = files_service.get_output_file(file_id)
            entity = entities_service.get_entity(file_dict["entity_id"])
            project_id = entity["project_id"]

        user_service.check_project_access(project_id)
        return file_dict


class SetTreeResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, project_id):
        """
        Set project file tree
        ---
        description: Define a template file to use for a given project.
          Template files are located on the server side and each template
          has a name for selection.
        tags:
        - Files
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - tree_name
                properties:
                  tree_name:
                    type: string
                    description: Name of the file tree template
                    example: "default"
        responses:
          200:
            description: File tree template set successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Project unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    name:
                      type: string
                      description: Project name
                      example: "My Project"
                    file_tree:
                      type: object
                      description: File tree template configuration
                      example: {"template": "default"}
                    updated_at:
                      type: string
                      format: date-time
                      description: Last update timestamp
                      example: "2023-01-01T12:30:00Z"
        """
        args = self.get_args(
            [
                {
                    "name": "tree_name",
                    "help": "The name of the tree to set is required.",
                    "required": True,
                }
            ]
        )

        try:
            user_service.check_project_access(project_id)
            tree = file_tree_service.get_tree_from_file(args["tree_name"])
            project = projects_service.update_project(
                project_id, {"file_tree": tree}
            )
        except WrongFileTreeFileException:
            abort(400, "Selected tree is not available")

        return project


class EntityWorkingFilesResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, entity_id):
        """
        Get entity working files
        ---
        description: Retrieve all working files for a given entity with
          optional filtering by task and name. Returns complete list of
          working files with their revisions.
        tags:
        - Files
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: task_id
            required: false
            schema:
              type: string
              format: uuid
            description: Filter by task
            example: b35b7fb5-df86-5776-b181-68564193d36
          - in: query
            name: name
            required: false
            schema:
              type: string
            description: Filter by file name
            example: "main"
        responses:
          200:
            description: All working files for the entity
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
                        description: Working file unique identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      name:
                        type: string
                        description: Working file name
                        example: "main"
                      revision:
                        type: integer
                        description: Working file revision
                        example: 1
                      path:
                        type: string
                        description: Working file path
                        example: "/project/asset/working/main_v001.blend"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:00:00Z"
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      entity_id:
                        type: string
                        format: uuid
                        description: Entity identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
        """
        args = self.get_args(
            [
                "task_id",
                "name",
            ],
        )

        relations = self.get_relations()

        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])

        return files_service.get_working_files_for_entity(
            entity_id,
            task_id=args["task_id"],
            name=args["name"],
            relations=relations,
        )


class GuessFromPathResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self):
        """
        Guess file tree template
        ---
        description: Get list of possible project file tree templates matching
          a file path and data ids corresponding to template tokens.
        tags:
        - Files
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - project_id
                  - file_path
                properties:
                  project_id:
                    type: string
                    format: uuid
                    description: Project unique identifier
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  file_path:
                    type: string
                    description: File path to analyze
                    example: "/project/asset/working/main_v001.blend"
                  sep:
                    type: string
                    description: Path separator
                    default: /
                    example: "/"
        responses:
          200:
            description: List of possible project file tree templates matching the file path
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    matches:
                      type: array
                      items:
                        type: object
                        properties:
                          template:
                            type: string
                            description: Template name
                            example: "default"
                          confidence:
                            type: number
                            description: Confidence score
                            example: 0.95
                          data:
                            type: object
                            description: Extracted data from path
                            properties:
                              project_id:
                                type: string
                                format: uuid
                                description: Project identifier
                                example: a24a6ea4-ce75-4665-a070-57453082c25
                              entity_id:
                                type: string
                                format: uuid
                                description: Entity identifier
                                example: b35b7fb5-df86-5776-b181-68564193d36
          400:
            description: Invalid project ID or file path
        """
        data = self.get_arguments()

        return file_tree_service.guess_from_path(
            project_id=data["project_id"],
            file_path=data["file_path"],
            sep=data["sep"],
        )

    def get_arguments(self):
        return self.get_args(
            [
                {
                    "name": "project_id",
                    "help": "The project id is required.",
                    "required": True,
                },
                {
                    "name": "file_path",
                    "help": "The file path is required.",
                    "required": True,
                },
                ["sep", "/"],
            ]
        )
