import uuid
import os
import csv

from sqlalchemy.exc import IntegrityError

from flask import request, current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app import app
from zou.app.utils import permissions
from zou.app.services import user_service, projects_service


class ImportRowException(Exception):
    message = ""
    line_number = 0

    def __init__(self, message, line_number):
        Exception.__init__(self, message)
        self.message = message
        self.line_number = line_number


class BaseCsvImportResource(Resource):
    def __init__(self):
        Resource.__init__(self)

    @jwt_required
    def post(self):
        uploaded_file = request.files["file"]
        file_name = "%s.csv" % uuid.uuid4()

        file_path = os.path.join(app.config["TMP_DIR"], file_name)
        uploaded_file.save(file_path)
        self.is_update = request.args.get("update", "false") == "true"

        try:
            result = self.run_import(file_path)
            return result, 201
        except ImportRowException as e:
            current_app.logger.error("Import failed: %s" % e)
            return self.format_error(e), 400

    def format_error(self, exception):
        return {
            "error": True,
            "message": exception.message,
            "line_number": exception.line_number
        }

    def run_import(self, file_path):
        result = []
        self.check_permissions()
        self.prepare_import()
        delimiter = self.get_delimiter(file_path)
        with open(file_path) as csvfile:
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            for row in reader:
                row = self.import_row(row)
                result.append(row)
        return result

    def get_delimiter(self, file_path):
        delimiter = ","
        with open(file_path) as csvfile:
            try:
                content = csvfile.read()
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(content)
                delimiter = dialect.delimiter
            except:
                pass

        return delimiter

    def prepare_import(self):
        pass

    def check_permissions(self):
        return permissions.check_manager_permissions()

    def import_row(self):
        pass

    def add_to_cache_if_absent(self, cache, retrieve_function, name):
        if name not in cache:
            cache[name] = retrieve_function(name)
        return cache[name]

    def get_id_from_cache(self, cache, name):
        cached_object = cache[name]
        if type(cached_object) is dict:
            return cached_object["id"]
        else:
            return cached_object.id


class BaseCsvProjectImportResource(BaseCsvImportResource):
    @jwt_required
    def post(self, project_id):
        uploaded_file = request.files["file"]
        file_name = "%s.csv" % uuid.uuid4()
        file_path = os.path.join(app.config["TMP_DIR"], file_name)
        uploaded_file.save(file_path)
        self.is_update = request.args.get("update", "false") == "true"

        try:
            result = self.run_import(project_id, file_path)
            return result, 201
        except ImportRowException as e:
            return self.format_error(e), 400

    def run_import(self, project_id, file_path):
        result = []
        self.check_project_permissions(project_id)
        self.prepare_import(project_id)
        delimiter = self.get_delimiter(file_path)
        with open(file_path) as csvfile:
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            line_number = 1
            for row in reader:
                try:
                    row = self.import_row(row, project_id)
                    result.append(row)
                except IntegrityError as e:
                    raise ImportRowException(e._message(), line_number)
                except KeyError as e:
                    raise ImportRowException(
                        "A columns is missing: %s" % e.args,
                        line_number
                    )
                line_number += 1
        return result

    def check_project_permissions(self, project_id):
        return user_service.check_manager_project_access(project_id)

    def import_row(self, project_id):
        pass

    def get_descriptor_field_map(self, project_id, entity_type):
        descriptor_map = {}
        descriptors = projects_service.get_metadata_descriptors(project_id)
        for descriptor in descriptors:
            if descriptor["entity_type"] == entity_type:
                descriptor_map[descriptor["name"]] = descriptor["field_name"]
        return descriptor_map
