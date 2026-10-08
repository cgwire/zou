from flasgger import swag_from
import os

from flask import request, current_app
from flask import send_file as flask_send_file
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from flask_fs.errors import FileNotFound
from zou.app import config

from zou.app.mixin import ArgsMixin
from zou.app.utils import fs, date_helpers, validation
from zou.app.blueprints.files.schemas import (
    WorkingFilePathSchema,
    OutputFilePathSchema,
    NewWorkingFileSchema,
    WorkingFileCommentSchema,
    NewOutputFileSchema,
    NextRevisionSchema,
    SetTreeSchema,
    GuessFilePathSchema,
)
from zou.app.stores import file_store
from zou.app.services import (
    file_tree_service,
    files_service,
    persons_service,
    projects_service,
    assets_service,
    tasks_service,
    entities_service,
    permissions_service,
    task_types_service,
)

from zou.app.exceptions import (
    EntryAlreadyExistsException,
    MalformedFileTreeException,
    OutputTypeNotFoundException,
    PersonNotFoundException,
    WrongFileTreeFileException,
    WrongParameterException,
    WorkingFileNotFoundException,
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

    download_name = ""
    if as_attachment:
        download_name = working_file_id

    try:
        # The lookup is what raises FileNotFound: it has to sit inside
        # the try, or a missing binary is a 500 instead of a 404.
        file_path = fs.get_file_path_and_file(
            config,
            get_local_path,
            open_file,
            prefix,
            working_file_id,
            extension,
        )
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
                "message": f"Working file not found for: {working_file_id}",
            },
            404,
        )
    except FileNotFound:
        return (
            {
                "error": True,
                "message": f"Working file not found for: {working_file_id}",
            },
            404,
        )


class WorkingFileFileResource(MethodView):

    def check_access(self, working_file_id):
        working_file = files_service.get_working_file(working_file_id)
        permissions_service.check_task_access(working_file["task_id"])
        return working_file

    def save_uploaded_file_in_temporary_folder(self, working_file_id):
        uploaded_file = request.files["file"]
        tmp_folder = current_app.config["TMP_DIR"]
        file_name = f"working-file-{working_file_id}"
        file_path = os.path.join(tmp_folder, file_name)
        uploaded_file.save(file_path)
        return file_path

    @jwt_required()
    @swag_from("openapi/WorkingFileFileResource_get.yml")
    def get(self, working_file_id):
        """
        Download working file
        """
        working_file = self.check_access(working_file_id)
        return send_storage_file(
            working_file_id,
            last_modified=date_helpers.get_datetime_from_string(
                working_file["updated_at"]
            ),
        )

    @jwt_required()
    @swag_from("openapi/WorkingFileFileResource_post.yml")
    def post(self, working_file_id):
        """
        Store working file
        """
        working_file = self.check_access(working_file_id)
        file_path = self.save_uploaded_file_in_temporary_folder(
            working_file_id
        )
        try:
            file_store.add_file("working", working_file_id, file_path)
        finally:
            os.remove(file_path)
        return working_file, 201


class WorkingFilePathResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/WorkingFilePathResource_post.yml")
    def post(self, task_id):
        """
        Generate working file path
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
            permissions_service.check_project_access(task["project_id"])
            permissions_service.check_entity_access(task["entity_id"])

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
        body = validation.validate_request_body(WorkingFilePathSchema)
        software_id = body.software_id if body.software_id else maxsoft["id"]

        return (
            body.name,
            body.mode,
            software_id,
            body.comment,
            body.revision,
            body.sep,
        )


class EntityOutputFilePathResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/EntityOutputFilePathResource_post.yml")
    def post(self, entity_id):
        """
        Generate entity output file path
        """
        args = self.get_arguments()
        try:
            entity = entities_service.get_entity(entity_id)
            permissions_service.check_project_access(entity["project_id"])
            permissions_service.check_entity_access(entity_id)
            output_type = files_service.get_output_type(args["output_type_id"])
            task_type = task_types_service.get_task_type(args["task_type_id"])
            is_revision_set_by_user = args["revision"] != 0
            if not is_revision_set_by_user:
                revision = files_service.get_next_output_file_revision(
                    entity_id,
                    args["output_type_id"],
                    args["task_type_id"],
                    args["name"],
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
        body = validation.validate_request_body(OutputFilePathSchema)
        return body.model_dump()


class InstanceOutputFilePathResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/InstanceOutputFilePathResource_post.yml")
    def post(self, asset_instance_id, temporal_entity_id):
        """
        Generate instance output file path
        """
        args = self.get_arguments()

        try:
            asset_instance = assets_service.get_asset_instance(
                asset_instance_id
            )
            entity = entities_service.get_entity(temporal_entity_id)
            asset = assets_service.get_asset(asset_instance["asset_id"])
            output_type = files_service.get_output_type(args["output_type_id"])
            task_type = task_types_service.get_task_type(args["task_type_id"])
            permissions_service.check_project_access(asset["project_id"])
            permissions_service.check_entity_access(asset["id"])

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
        body = validation.validate_request_body(OutputFilePathSchema)
        return body.model_dump()


class LastWorkingFilesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/LastWorkingFilesResource_get.yml")
    def get(self, task_id):
        """
        Get last working files
        """
        result = {}
        permissions_service.check_task_access(task_id)
        result = files_service.get_last_working_files_for_task(task_id)

        return result


class TaskWorkingFilesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/TaskWorkingFilesResource_get.yml")
    def get(self, task_id):
        """
        Get task working files
        """
        result = {}
        permissions_service.check_task_access(task_id)
        result = files_service.get_working_files_for_task(task_id)

        return result


class NewWorkingFileResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/NewWorkingFileResource_post.yml")
    def post(self, task_id):
        """
        Create new working file
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
            permissions_service.check_project_access(task["project_id"])
            permissions_service.check_entity_access(task["entity_id"])
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
        return f"{folder_path}{sep}{file_name}"

    def get_arguments(self):
        person = persons_service.get_current_user()
        body = validation.validate_request_body(NewWorkingFileSchema)

        person_id = body.person_id if body.person_id else person["id"]
        software_id = body.software_id
        if software_id is None:
            default_soft = files_service.get_or_create_software(
                "Blender", "blender", ".blend"
            )
            software_id = default_soft["id"]

        return (
            body.name,
            body.mode,
            body.description,
            body.comment,
            person_id,
            software_id,
            body.revision,
            body.sep,
        )


class ModifiedFileResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ModifiedFileResource_put.yml")
    def put(self, working_file_id):
        """
        Update working file modification date
        """
        working_file = files_service.get_working_file(working_file_id)
        permissions_service.check_task_action_access(working_file["task_id"])
        working_file = files_service.update_working_file(
            working_file_id,
            {"updated_at": date_helpers.get_utc_now_datetime()},
        )
        return working_file


class CommentWorkingFileResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/CommentWorkingFileResource_put.yml")
    def put(self, working_file_id):
        """
        Update working file comment
        """
        body = validation.validate_request_body(WorkingFileCommentSchema)

        working_file = files_service.get_working_file(working_file_id)
        permissions_service.check_task_action_access(working_file["task_id"])
        working_file = self.update_comment(working_file_id, body.comment)
        return working_file

    def update_comment(self, working_file_id, comment):
        working_file = files_service.update_working_file(
            working_file_id, {"comment": comment}
        )
        return working_file


class NewEntityOutputFileResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/NewEntityOutputFileResource_post.yml")
    def post(self, entity_id):
        """
        Create new entity output file
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
            permissions_service.check_project_access(entity["project_id"])
            output_type = files_service.get_output_type(args["output_type_id"])
            task_type = task_types_service.get_task_type(args["task_type_id"])

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
        except MalformedFileTreeException as exception:
            return {"error": str(exception)}, 400

        return output_file_dict, 201

    def get_arguments(self):
        body = validation.validate_request_body(NewOutputFileSchema)
        return body.model_dump()

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
            {"path": f"{folder_path}{separator}{file_name}{extension}"},
        )

        output_file.update(
            {"folder_path": folder_path, "file_name": file_name}
        )

        return output_file


class NewInstanceOutputFileResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/NewInstanceOutputFileResource_post.yml")
    def post(self, asset_instance_id, temporal_entity_id):
        """
        Create new instance output file
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
            permissions_service.check_project_access(entity["project_id"])

            output_type = files_service.get_output_type(args["output_type_id"])
            task_type = task_types_service.get_task_type(args["task_type_id"])
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
        body = validation.validate_request_body(NewOutputFileSchema)
        return body.model_dump()

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
            {"path": f"{folder_path}{separator}{file_name}{extension}"},
        )

        output_file.update(
            {"folder_path": folder_path, "file_name": file_name}
        )

        return output_file


class GetNextEntityOutputFileRevisionResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/GetNextEntityOutputFileRevisionResource_post.yml")
    def post(self, entity_id):
        """
        Get next entity output file revision
        """
        body = validation.validate_request_body(NextRevisionSchema)
        entity = entities_service.get_entity(entity_id)
        output_type = files_service.get_output_type(body.output_type_id)
        task_type = task_types_service.get_task_type(body.task_type_id)
        permissions_service.check_project_access(entity["project_id"])

        next_revision_number = files_service.get_next_output_file_revision(
            entity["id"], output_type["id"], task_type["id"], body.name
        )

        return {"next_revision": next_revision_number}, 200


class GetNextInstanceOutputFileRevisionResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/GetNextInstanceOutputFileRevisionResource_post.yml")
    def post(self, asset_instance_id, temporal_entity_id):
        """
        Get next instance output file revision
        """
        body = validation.validate_request_body(NextRevisionSchema)

        asset_instance = assets_service.get_asset_instance(asset_instance_id)
        asset = entities_service.get_entity(asset_instance["asset_id"])
        output_type = files_service.get_output_type(body.output_type_id)
        task_type = task_types_service.get_task_type(body.task_type_id)
        permissions_service.check_project_access(asset["project_id"])

        next_revision_number = files_service.get_next_output_file_revision(
            asset["id"],
            output_type["id"],
            task_type["id"],
            body.name,
            asset_instance_id=asset_instance["id"],
            temporal_entity_id=temporal_entity_id,
        )

        return {"next_revision": next_revision_number}, 200


class LastEntityOutputFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/LastEntityOutputFilesResource_get.yml")
    def get(self, entity_id):
        """
        Get last entity output files
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
        permissions_service.check_project_access(entity["project_id"])

        return files_service.get_last_output_files_for_entity(
            entity["id"],
            output_type_id=args["output_type_id"],
            task_type_id=args["task_type_id"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
            name=args["name"],
        )


class LastInstanceOutputFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/LastInstanceOutputFilesResource_get.yml")
    def get(self, asset_instance_id, temporal_entity_id):
        """
        Get last instance output files
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
        permissions_service.check_project_access(entity["project_id"])

        return files_service.get_last_output_files_for_instance(
            asset_instance["id"],
            temporal_entity_id,
            output_type_id=args["output_type_id"],
            task_type_id=args["task_type_id"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
            name=args["name"],
        )


class EntityOutputTypesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/EntityOutputTypesResource_get.yml")
    def get(self, entity_id):
        """
        Get entity output types
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        return files_service.get_output_types_for_entity(entity_id)


class InstanceOutputTypesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/InstanceOutputTypesResource_get.yml")
    def get(self, asset_instance_id, temporal_entity_id):
        """
        Get instance output types
        """
        asset_instance = assets_service.get_asset_instance(asset_instance_id)
        entity = entities_service.get_entity(asset_instance["asset_id"])
        permissions_service.check_project_access(entity["project_id"])
        return files_service.get_output_types_for_instance(
            asset_instance_id, temporal_entity_id
        )


class EntityOutputTypeOutputFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/EntityOutputTypeOutputFilesResource_get.yml")
    def get(self, entity_id, output_type_id):
        """
        Get entity output type files
        """
        representation = self.get_text_parameter("representation")

        entity = entities_service.get_entity(entity_id)
        files_service.get_output_type(output_type_id)
        permissions_service.check_project_access(entity["project_id"])
        output_files = (
            files_service.get_output_files_for_output_type_and_entity(
                entity_id, output_type_id, representation=representation
            )
        )

        return output_files


class InstanceOutputTypeOutputFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/InstanceOutputTypeOutputFilesResource_get.yml")
    def get(self, asset_instance_id, temporal_entity_id, output_type_id):
        """
        Get instance output type files
        """
        representation = self.get_text_parameter("representation")

        asset_instance = assets_service.get_asset_instance(asset_instance_id)
        asset = assets_service.get_asset(asset_instance["asset_id"])
        permissions_service.check_project_access(asset["project_id"])

        files_service.get_output_type(output_type_id)
        return (
            files_service.get_output_files_for_output_type_and_asset_instance(
                asset_instance_id,
                temporal_entity_id,
                output_type_id,
                representation=representation,
            )
        )


class ProjectOutputFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProjectOutputFilesResource_get.yml")
    def get(self, project_id):
        """
        Get project output files
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
        permissions_service.check_manager_project_access(project_id)

        return files_service.get_output_files_for_project(
            project_id,
            task_type_id=args["task_type_id"],
            output_type_id=args["output_type_id"],
            name=args["name"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
        )


class EntityOutputFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/EntityOutputFilesResource_get.yml")
    def get(self, entity_id):
        """
        Get entity output files
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
        permissions_service.check_project_access(entity["project_id"])

        return files_service.get_output_files_for_entity(
            entity["id"],
            task_type_id=args["task_type_id"],
            output_type_id=args["output_type_id"],
            name=args["name"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
        )


class InstanceOutputFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/InstanceOutputFilesResource_get.yml")
    def get(self, asset_instance_id):
        """
        Get instance output files
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
        permissions_service.check_project_access(asset["project_id"])

        return files_service.get_output_files_for_instance(
            asset_instance["id"],
            temporal_entity_id=args["temporal_entity_id"],
            task_type_id=args["task_type_id"],
            output_type_id=args["output_type_id"],
            name=args["name"],
            representation=args["representation"],
            file_status_id=args["file_status_id"],
        )


class FileResource(MethodView):

    @jwt_required()
    @swag_from("openapi/FileResource_get.yml")
    def get(self, file_id):
        """
        Get file information
        """
        try:
            file_dict = files_service.get_working_file(file_id)
            task = tasks_service.get_task(file_dict["task_id"])
            project_id = task["project_id"]
        except WorkingFileNotFoundException:
            file_dict = files_service.get_output_file(file_id)
            entity = entities_service.get_entity(file_dict["entity_id"])
            project_id = entity["project_id"]

        permissions_service.check_project_access(project_id)
        return file_dict


class SetTreeResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/SetTreeResource_post.yml")
    def post(self, project_id):
        """
        Set project file tree
        """
        body = validation.validate_request_body(SetTreeSchema)

        try:
            permissions_service.check_manager_project_access(project_id)
            tree = file_tree_service.get_tree_from_file(body.tree_name)
            project = projects_service.update_project(
                project_id, {"file_tree": tree}
            )
        except WrongFileTreeFileException:
            raise WrongParameterException("Selected tree is not available")

        return project


class EntityWorkingFilesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/EntityWorkingFilesResource_get.yml")
    def get(self, entity_id):
        """
        Get entity working files
        """
        args = self.get_args(
            [
                "task_id",
                "name",
            ],
        )

        relations = self.get_relations()

        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])

        return files_service.get_working_files_for_entity(
            entity_id,
            task_id=args["task_id"],
            name=args["name"],
            relations=relations,
        )


class GuessFromPathResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/GuessFromPathResource_post.yml")
    def post(self):
        """
        Guess file tree template
        """
        body = validation.validate_request_body(GuessFilePathSchema)
        permissions_service.check_project_access(body.project_id)

        return file_tree_service.guess_from_path(
            project_id=body.project_id,
            file_path=body.file_path,
            sep=body.sep,
        )
