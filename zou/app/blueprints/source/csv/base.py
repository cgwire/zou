import uuid
import os
import csv

from sqlalchemy.exc import IntegrityError

from flask import request, current_app
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app import app
from zou.app.models.person import Person
from zou.app.utils import permissions, string
from zou.app.services import user_service, projects_service


class ImportRowException(Exception):
    message = ""
    line_number = 0

    def __init__(self, message, line_number, imported_rows=0):
        Exception.__init__(self, message)
        self.message = message
        self.line_number = line_number
        self.imported_rows = imported_rows


class RowException(Exception):
    message = ""

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


class BaseCsvImportResource(MethodView, ArgsMixin):
    @jwt_required()
    def post(self, *args):
        uploaded_file = request.files["file"]
        file_name = f"{uuid.uuid4()}.csv"

        file_path = os.path.join(app.config["TMP_DIR"], file_name)
        uploaded_file.save(file_path)
        self.is_update = self.get_bool_parameter("update")

        try:
            result = self.run_import(file_path, *args)
            return result, 201
        except ImportRowException as e:
            current_app.logger.error(
                f"Import row {e.line_number} failed: {e.message}"
            )
            return self.format_row_error(e), 400
        except csv.Error as e:
            current_app.logger.error(f"Import failed: {e}")
            return self.format_error(e), 400

    def format_row_error(self, exception):
        return {
            "error": True,
            "message": exception.message,
            "line_number": exception.line_number,
            "imported_rows": exception.imported_rows,
        }

    def format_error(self, exception):
        return {"error": True, "message": str(exception)}

    def run_import(self, file_path, *args):
        """
        Import rows one by one, each committed on its own: a failure stops
        the import but keeps previously imported rows (imported_rows in
        the error payload tells the client how many). Fixing the file and
        re-importing with update=true completes the job idempotently.
        """
        result = []
        self.check_permissions(*args)
        self.prepare_import(*args)
        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile, dialect=self.get_dialect(csvfile))
            for row in reader:
                # reader.line_num is the real file line (header included),
                # so errors point at the line the user sees in the file.
                line_number = reader.line_num
                try:
                    row = self.import_row(row, *args)
                    result.append(row)
                except IntegrityError as e:
                    raise ImportRowException(
                        e._message(), line_number, len(result)
                    )
                except RowException as e:
                    raise ImportRowException(
                        e.message, line_number, len(result)
                    )
                except KeyError as e:
                    raise ImportRowException(
                        f"A columns is missing: {str(e)}",
                        line_number,
                        len(result),
                    )
                except ValueError as e:
                    raise ImportRowException(
                        f"A value is invalid: {str(e)}",
                        line_number,
                        len(result),
                    )
                except Exception as e:
                    raise ImportRowException(str(e), line_number, len(result))
        return result

    def get_dialect(self, csvfile):
        sniffer = csv.Sniffer()
        sample = csvfile.read(8192)
        csvfile.seek(0)
        dialect = sniffer.sniff(sample)
        dialect.doublequote = True
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
        self.person_lookup = None
        descriptors = projects_service.get_metadata_descriptors(project_id)
        for descriptor in descriptors:
            if descriptor["entity_type"] == entity_type:
                descriptor_map[descriptor["name"]] = descriptor
        return descriptor_map

    def get_descriptor_values(self, row, data=None):
        """
        Return a new data dict merging the row's metadata descriptor cells
        into the given base data, storing typed values in their canonical
        form: booleans as true/false strings, persons as their id.
        """
        new_data = dict(data or {})
        for name, descriptor in self.descriptor_fields.items():
            if name in row:
                value = row[name]
                # An empty cell means "not set": store it as is instead of
                # feeding it to the typed conversions (strtobool raises on "").
                if value not in (None, ""):
                    if descriptor["data_type"] == "boolean":
                        value = "true" if string.strtobool(value) else "false"
                    elif descriptor["data_type"] == "person":
                        value = self.get_person_id(value)
                new_data[descriptor["field_name"]] = value
        return new_data

    def get_person_id(self, value):
        """
        Resolve a person cell to a person id. Accepts the person full name,
        email or id, so that CSV files exported by Kitsu (full names) and
        older files built from raw ids both import correctly.
        """
        if value in (None, ""):
            return value
        if self.person_lookup is None:
            self.person_lookup = {}
            for person in Person.query.all():
                self.person_lookup[str(person.id)] = str(person.id)
                self.person_lookup[person.full_name.lower()] = str(person.id)
                if person.email:
                    self.person_lookup[person.email.lower()] = str(person.id)
        person_id = self.person_lookup.get(value.strip().lower())
        if person_id is None:
            raise RowException(f"Person not found for {value}")
        return person_id
