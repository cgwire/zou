import uuid
import os
import csv

from sqlalchemy.exc import IntegrityError

from flask import request, current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
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


class RowException(Exception):
    message = ""

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


class BaseCsvImportResource(Resource, ArgsMixin):
    @jwt_required()
    def post(self, *args):
        uploaded_file = request.files["file"]
        file_name = "%s.csv" % uuid.uuid4()

        file_path = os.path.join(app.config["TMP_DIR"], file_name)
        uploaded_file.save(file_path)
        self.is_update = self.get_bool_parameter("update")

        try:
            result = self.run_import(file_path, *args)
            return result, 201
        except ImportRowException as e:
            current_app.logger.error(
                "Import row %s failed: %s" % (e.line_number, e.message)
            )
            return self.format_row_error(e), 400
        except csv.Error as e:
            current_app.logger.error("Import failed: %s" % e)
            return self.format_error(e), 400

    def format_row_error(self, exception):
        return {
            "error": True,
            "message": exception.message,
            "line_number": exception.line_number,
        }

    def format_error(self, exception):
        return {"error": True, "message": str(exception)}

    def run_import(self, file_path, *args):
        result = []
        self.check_permissions(*args)
        self.prepare_import(*args)
        with open(file_path) as csvfile:
            reader = csv.DictReader(csvfile, dialect=self.get_dialect(csvfile))
            line_number = 1
            for row in reader:
                try:
                    row = self.import_row(row, *args)
                    result.append(row)
                except IntegrityError as e:
                    raise ImportRowException(e._message(), line_number)
                except RowException as e:
                    raise ImportRowException(e.message, line_number)
                except KeyError as e:
                    raise ImportRowException(
                        f"A columns is missing: {str(e)}", line_number
                    )
                except ValueError as e:
                    raise ImportRowException(
                        f"A value is invalid: {str(e)}", line_number
                    )
                except Exception as e:
                    raise ImportRowException(str(e), line_number)
                line_number += 1
        return result

    def get_dialect(self, csvfile):
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(csvfile.read())
        dialect.doublequote = True
        csvfile.seek(0)
        return dialect

    def prepare_import(self, *args):
        pass

    def check_permissions(self, *args):
        return permissions.check_manager_permissions()

    def import_row(self, *args):
        pass

    def add_to_cache_if_absent(self, cache, retrieve_function, name):
        if name not in cache:
            cache[name] = retrieve_function(name)
        return cache[name]

    def get_id_from_cache(self, cache, name):
        cached_object = cache[name]
        if isinstance(cached_object, dict):
            return cached_object["id"]
        else:
            return cached_object.id


class BaseCsvProjectImportResource(BaseCsvImportResource, ArgsMixin):
    @jwt_required()
    def check_project_permissions(self, project_id):
        return user_service.check_manager_project_access(project_id)

    def get_descriptor_field_map(self, project_id, entity_type):
        descriptor_map = {}
        descriptors = projects_service.get_metadata_descriptors(project_id)
        for descriptor in descriptors:
            if descriptor["entity_type"] == entity_type:
                descriptor_map[descriptor["name"]] = descriptor["field_name"]
        return descriptor_map
