import csv
import io
import os
import uuid

from flask import current_app, request
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from zou.app import app
from zou.app.blueprints.crud.base import build_db_error_message
from zou.app.exceptions import WrongParameterException
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    comments_service,
    entities_service,
    entity_types_service,
    metadata_descriptors_service,
    permissions_service,
    persons_service,
    projects_service,
    shots_service,
    tasks_service,
)
from zou.app.utils import permissions, string


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


# The delimiters the sniffer prefers, plus the pipe, minus the space, which
# names hold.
DELIMITERS = ",;\t|:"

# A control character that text does not hold, as is_single_column checks:
# each line is a single cell, whatever delimiter the writer of the file used.
SINGLE_COLUMN_DELIMITER = "\x1f"


class SingleColumnDialect(csv.excel):
    delimiter = SINGLE_COLUMN_DELIMITER


class BaseCsvImportResource(MethodView, ArgsMixin):
    @jwt_required()
    def post(self, *args):
        # Authorize before anything reaches the disk, and drop the file
        # whatever happens next: otherwise any account could fill TMP_DIR
        # by posting to an import route it is not allowed to use.
        self.check_permissions(*args)
        uploaded_file = request.files["file"]
        file_name = f"{uuid.uuid4()}.csv"

        file_path = os.path.join(app.config["TMP_DIR"], file_name)
        uploaded_file.save(file_path)
        self.is_update = self.get_bool_parameter("update")

        try:
            result = self.run_import(file_path, *args)
            return result, 201
        # A malformed file is client input, not a server fault: warnings keep
        # it out of the error monitoring while the 400 still tells the user
        # which line to fix.
        except ImportRowException as e:
            current_app.logger.warning(
                f"Import row {e.line_number} failed: {e.message}"
            )
            return self.format_row_error(e), 400
        except csv.Error as e:
            current_app.logger.warning(f"Import failed: {e}")
            return self.format_error(e), 400
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

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
        # Permissions are checked by post(), before the upload is written.
        result = []
        self.prepare_import(*args)
        # utf-8-sig drops the byte order mark that starts a "CSV UTF-8" file
        # of Excel, which would otherwise begin the first header.
        with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
            # Decoded whole first: a file in another encoding, such as the
            # Windows-1252 of a spreadsheet, is refused before any import.
            try:
                csvfile.read()
            except UnicodeDecodeError:
                raise csv.Error("The file is not encoded in UTF-8")
            csvfile.seek(0)
            reader = csv.DictReader(csvfile, dialect=self.get_dialect(csvfile))
            for row in reader:
                # reader.line_num is the real file line (header included),
                # so errors point at the line the user sees in the file.
                line_number = reader.line_num
                # Spreadsheets often export empty lines made of separators
                # only: they carry nothing to import.
                if not any(
                    isinstance(value, str) and value.strip()
                    for value in row.values()
                ):
                    continue
                try:
                    row = self.import_row(row, *args)
                    result.append(row)
                except IntegrityError as e:
                    raise ImportRowException(
                        build_db_error_message(e), line_number, len(result)
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
                    raise ImportRowException(
                        build_db_error_message(e), line_number, len(result)
                    )
        return result

    def get_dialect(self, csvfile):
        sniffer = csv.Sniffer()
        sample = csvfile.read(8192)
        csvfile.seek(0)
        try:
            dialect = sniffer.sniff(sample)
        except csv.Error:
            # It gives up on a file of a single column.
            if self.is_single_column(csvfile, SingleColumnDialect):
                return SingleColumnDialect
            raise
        dialect.doublequote = True
        # Or takes the quote of its cells for the delimiter, which Python 3.13
        # refuses, or a letter of its names.
        if (
            dialect.delimiter == dialect.quotechar
            or dialect.delimiter.isalnum()
        ):
            if not self.is_single_column(csvfile, dialect):
                raise csv.Error("Could not determine delimiter")
            dialect.delimiter = SINGLE_COLUMN_DELIMITER
        return dialect

    def is_single_column(self, csvfile, dialect):
        """
        Tell whether given file, read with the quote and the spacing of given
        dialect, holds a single column: a header on its first line,
        well-formed quoted cells, and out of them no comma, semicolon, tab,
        pipe, or colon, nor the delimiter of a single column. Such a
        delimiter leaves a doubt: a name can hold it, or a line can hold
        more cells than the header names. A quote left open would merge the
        next lines into one name.
        """
        content = csvfile.read()
        csvfile.seek(0)
        header = content.splitlines()[0] if content else ""
        try:
            return header != "" and not any(
                len(cells) > 1
                for delimiter in DELIMITERS + SINGLE_COLUMN_DELIMITER
                for cells in csv.reader(
                    io.StringIO(content, newline=""),
                    dialect,
                    delimiter=delimiter,
                    strict=True,
                )
            )
        except csv.Error:
            return False

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
    def check_permissions(self, project_id, *args):
        """
        Importing into a production requires managing that production, not
        just holding the manager role somewhere. This mirrors the OTIO
        import next door and the CSV exports, which all scope to the
        project.
        """
        return permissions_service.check_manager_project_access(project_id)

    def get_or_create_episode(self, project_id, name):
        """
        Return the episode of given name. When the production does not have
        it yet, create it with a task for each Episode task type of the
        project, as Kitsu and the episodes import do.
        """
        is_missing = (
            entities_service.find_entity_raw(
                name=name,
                project_id=project_id,
                entity_type_id=entity_types_service.get_episode_type()["id"],
            )
            is None
        )
        episode = shots_service.create_episode(
            project_id, name, created_by=self.current_user_id
        )
        if is_missing:
            # Serialized first: create_tasks commits, which expires the
            # model instances.
            task_types = [
                task_type.serialize()
                for task_type in projects_service.get_project_task_types_raw(
                    project_id, "Episode"
                )
            ]
            for task_type in task_types:
                tasks_service.create_tasks(task_type, [episode])
        return episode

    def get_descriptor_field_map(self, project_id, entity_type):
        """
        Return the metadata descriptors of the project for the given entity
        type, by name. Also reset the person lookup of get_person_id.
        """
        descriptor_map = {}
        self.person_lookup = None
        descriptors = metadata_descriptors_service.get_metadata_descriptors(
            project_id
        )
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
            for person in persons_service.get_persons_raw():
                self.person_lookup[str(person.id)] = str(person.id)
                self.person_lookup[person.full_name.lower()] = str(person.id)
                if person.email:
                    self.person_lookup[person.email.lower()] = str(person.id)
        person_id = self.person_lookup.get(value.strip().lower())
        if person_id is None:
            raise RowException(f"Person not found for {value}")
        return person_id

    def get_assignation_ids(self, row, task_type_name):
        """
        Resolve the "<task type> assignations" cell into person ids. The
        cell holds comma-separated full names, emails or ids (the export
        writes full names); an empty or absent cell means no assignation
        change.
        """
        value = row.get(f"{task_type_name} assignations", None)
        if value in (None, ""):
            return []
        return [
            self.get_person_id(name)
            for name in value.split(",")
            if name.strip() != ""
        ]

    def get_tasks_update(self, row, task_types):
        """
        Return the task changes of the row: one entry per task type whose
        status, comment or assignation cell is filled. Raise RowException
        on an unknown status.
        """
        tasks_update = []
        for task_type in task_types:
            task_status_name = row.get(task_type["name"], None)
            task_status_id = None
            if task_status_name not in [None, ""]:
                for status_id, status_names in self.task_statuses.items():
                    if task_status_name.lower() in status_names:
                        task_status_id = status_id
                        break
                if task_status_id is None:
                    raise RowException(
                        f"Task status not found for {task_status_name}"
                    )

            # An empty cell holds no comment, as a missing column does.
            task_comment_text = (
                row.get(f"{task_type['name']} comment", None) or None
            )
            task_assignees = self.get_assignation_ids(row, task_type["name"])

            if (
                task_status_id is not None
                or task_comment_text is not None
                or task_assignees
            ):
                tasks_update.append(
                    {
                        "task_type_id": task_type["id"],
                        "task_status_id": task_status_id,
                        "comment": task_comment_text,
                        "assignees": task_assignees,
                    }
                )

        return tasks_update

    def apply_task_update(self, task, task_update):
        """
        Add the assignees of the task update to the task, and post a
        comment for a new status or a comment.
        """
        # Assignations only add people: an import never removes one.
        already_assigned = set(task.get("assignees") or [])
        for person_id in task_update["assignees"]:
            if person_id not in already_assigned:
                tasks_service.assign_task(
                    task["id"], person_id, self.current_user_id
                )
        # The status guard needs the explicit None check: an entry created
        # for its assignations alone must not post an empty comment at the
        # default status.
        if task_update["comment"] is not None or (
            task_update["task_status_id"] is not None
            and task_update["task_status_id"] != task["task_status_id"]
        ):
            try:
                comments_service.create_comment(
                    self.current_user_id,
                    task["id"],
                    task_update["task_status_id"] or task["task_status_id"],
                    task_update["comment"] or "",
                    [],
                    {},
                    "",
                )
            except WrongParameterException:
                pass
