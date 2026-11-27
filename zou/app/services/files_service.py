import itertools
import logging
import os
from operator import itemgetter

from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.sql.expression import and_

from zou.app import config
from zou.app.exceptions import (
    EntryAlreadyExistsException,
    NoOutputFileException,
    OutputFileNotFoundException,
    OutputTypeNotFoundException,
    PreviewBackgroundFileNotFoundException,
    PreviewFileNotFoundException,
    SoftwareNotFoundException,
    WorkingFileNotFoundException,
)
from zou.app.models.entity import Entity
from zou.app.models.file_status import FileStatus
from zou.app.models.output_file import OutputFile
from zou.app.models.output_type import OutputType
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.software import Software
from zou.app.models.task import Task
from zou.app.models.working_file import WorkingFile
from zou.app.services import (
    entities_service,
    projects_service,
)
from zou.app.services.base_service import (
    get_instance,
    get_or_create_instance_by_name,
)
from zou.app.stores import file_store, queue_store
from zou.app.utils import (
    cache,
    date_helpers,
    events,
    fields,
    fs,
    query as query_utils,
)

logger = logging.getLogger(__name__)


MOVIE_PREFIXES = ["previews", "lowdef", "source"]
LOWDEF_MOVIE_PREFIXES = ["lowdef", "previews", "source"]
MOVIE_PREFIXES_KEY = "movie_prefixes"


def clear_preview_file_cache(preview_file_id):
    """
    Remove the memoized serializations of the given preview file.
    """
    cache.cache.delete_memoized(get_preview_file, preview_file_id)
    cache.cache.delete_memoized(get_preview_file_for_access, preview_file_id)


def clear_output_file_cache(output_file_id):
    """
    Remove the memoized serialization of the given output file.
    """
    cache.cache.delete_memoized(get_output_file, output_file_id)


def clear_working_file_cache(working_file_id):
    """
    Remove the memoized serialization of the given working file.
    """
    cache.cache.delete_memoized(get_working_file, working_file_id)


def clear_output_type_cache(output_type_id):
    """
    Remove the memoized serialization of the given output type.
    """
    cache.cache.delete_memoized(get_output_type, output_type_id)


def clear_software_cache(software_id):
    """
    Remove the memoized serialization of the given software.
    """
    cache.cache.delete_memoized(get_software, software_id)


def clear_preview_background_file_cache(preview_background_file_id):
    """
    Remove the memoized serializations of the given preview background
    file.
    """
    cache.cache.delete_memoized(
        get_preview_background_file, preview_background_file_id
    )
    cache.cache.delete_memoized(get_preview_background_files)


def _apply_output_file_filters(
    query,
    task_type_id=None,
    output_type_id=None,
    name=None,
    representation=None,
    file_status_id=None,
):
    """
    Apply the optional filters that all output file listings use. If a
    value is falsy, do not apply the related filter.
    """
    if task_type_id:
        query = query.filter(OutputFile.task_type_id == task_type_id)
    if output_type_id:
        query = query.filter(OutputFile.output_type_id == output_type_id)
    if name:
        query = query.filter(OutputFile.name == name)
    if representation:
        query = query.filter(OutputFile.representation == representation)
    if file_status_id:
        query = query.filter(OutputFile.file_status_id == file_status_id)
    return query


def filter_output_files_by_projects(
    query, projects_filter, excluded_project_ids
):
    """
    Return the given output file query limited by the given project filter,
    applied to the projects of the output file entities. Remove the output
    files of the given excluded projects.
    """
    query = (
        query.join(Entity, OutputFile.entity_id == Entity.id)
        .join(Project)
        .filter(projects_filter)
    )
    if excluded_project_ids:
        query = query.filter(Entity.project_id.not_in(excluded_project_ids))
    return query


def clear_file_status_cache():
    """
    Remove the memoized default file status.
    """
    cache.cache.delete_memoized(get_default_file_status)


@cache.memoize_function(240)
def get_default_file_status():
    """
    Return the default file status of a new file.
    """
    default_status = FileStatus.get_by(name=config.DEFAULT_FILE_STATUS)
    if default_status is None:
        default_status = FileStatus(
            name=config.DEFAULT_FILE_STATUS, color="#FFFFFF"
        )
        default_status.save()
    return default_status.serialize()


def filter_working_files_by_projects(query, projects_filter):
    """
    Return the given working file query limited by the given project filter,
    applied to the projects of the working file entities.
    """
    return (
        query.join(Entity, WorkingFile.entity_id == Entity.id)
        .join(Project)
        .filter(projects_filter)
    )


def get_working_file_raw(working_file_id):
    """
    Return the given working file as an active record.
    """
    return get_instance(
        WorkingFile, working_file_id, WorkingFileNotFoundException
    )


@cache.memoize_function(240)
def get_working_file(working_file_id):
    """
    Return the given working file as a dict.
    """
    return get_working_file_raw(working_file_id).serialize(relations=True)


def get_output_file_raw(output_file_id):
    """
    Return the given output file as an active record.
    """
    return get_instance(
        OutputFile, output_file_id, OutputFileNotFoundException
    )


@cache.memoize_function(240)
def get_output_file(output_file_id):
    """
    Return the given output file as a dict.
    """
    return get_output_file_raw(output_file_id).serialize()


def get_software_raw(software_id):
    """
    Return the given software as an active record.
    """
    return get_instance(Software, software_id, SoftwareNotFoundException)


@cache.memoize_function(240)
def get_software(software_id):
    """
    Return the given software as a dict.
    """
    return get_software_raw(software_id).serialize()


def get_output_type_raw(output_type_id):
    """
    Return the given output type as an active record.
    """
    return get_instance(
        OutputType, output_type_id, OutputTypeNotFoundException
    )


@cache.memoize_function(240)
def get_output_type(output_type_id):
    """
    Return the given output type as a dict.
    """
    return get_output_type_raw(output_type_id).serialize()


def get_or_create_output_type(name, short_name=""):
    """
    Return the output type that has the given name. If it does not exist,
    create it.
    """
    return get_or_create_instance_by_name(
        OutputType, name=name, short_name=short_name
    )


def get_or_create_software(name, short_name, file_extension):
    """
    Return the software that has the given name. If it does not exist,
    create it.
    """
    return get_or_create_instance_by_name(
        Software,
        name=name,
        short_name=short_name,
        file_extension=file_extension,
    )


def get_last_working_files_for_task(task_id):
    """
    Return the last revisions of the given task as a dict. The key is the
    file name.
    """
    query = WorkingFile.query.with_entities(
        WorkingFile.name,
        WorkingFile.task_id,
        func.max(WorkingFile.revision).label("MAX"),
    ).group_by(
        WorkingFile.name,
        WorkingFile.task_id,
    )

    query = query.filter(WorkingFile.task_id == task_id)
    statement = query.subquery()

    query = WorkingFile.query.join(
        statement,
        and_(
            WorkingFile.task_id == statement.c.task_id,
            WorkingFile.name == statement.c.name,
            WorkingFile.revision == statement.c.MAX,
        ),
    )

    working_files = fields.serialize_models(query.all())

    working_files_by_name = {
        k: list(v)[0]
        for k, v in itertools.groupby(working_files, key=itemgetter("name"))
    }

    return working_files_by_name


def get_next_working_revision(task_id, name):
    """
    Return the next working file revision for the given task and name.
    """
    working_files = (
        WorkingFile.query.filter_by(task_id=task_id, name=name)
        .order_by(desc(WorkingFile.revision))
        .all()
    )
    if len(working_files) > 0:
        revision = working_files[0].revision + 1
    else:
        revision = 1
    return revision


def create_new_working_revision(
    task_id,
    person_id,
    software_id,
    name="main",
    path="",
    comment="",
    revision=0,
    description="",
):
    """
    Create a new working file revision for the given task. An author
    (user) and a software are necessary. Emit a working-file:new event and
    return the working file as a dict. If the revision exists, raise
    EntryAlreadyExistsException.
    """
    task = Task.get(task_id)
    if revision == 0:
        revision = get_next_working_revision(task_id, name)

    try:
        working_file = WorkingFile.create(
            comment=comment,
            description=description,
            name=name,
            revision=revision,
            path=path,
            task_id=task.id,
            software_id=software_id,
            entity_id=task.entity_id,
            person_id=person_id,
        )
        events.emit(
            "working-file:new",
            {"working_file_id": working_file.id},
            project_id=str(task.project_id),
        )
    except IntegrityError:
        raise EntryAlreadyExistsException

    return working_file.serialize()


def create_new_output_revision(
    entity_id,
    working_file_id,
    output_type_id,
    person_id,
    task_type_id,
    revision=0,
    representation="",
    name="main",
    comment="",
    extension="",
    nb_elements=1,
    asset_instance_id=None,
    temporal_entity_id=None,
    file_status_id=None,
):
    """
    Create a new output file for the given entity. The output type, task
    type, author and source file are necessary.

    The revision is the next available revision, but you can force it.
    You can also set an extension and a name.

    You can also give an asset instance. Then the output file is linked to
    the asset instance.

    The `temporal_entity_id` applies only to asset instance output files.
    It tells if the output is generated in the context of a shot or of a
    scene.

    Emit an output-file:new event and return the output file as a dict.
    If the revision exists, raise EntryAlreadyExistsException.
    """

    if revision < 1:
        try:
            output_file = get_last_output_revision(
                entity_id,
                output_type_id,
                task_type_id,
                name=name,
                asset_instance_id=asset_instance_id,
                temporal_entity_id=temporal_entity_id,
            )

            revision = output_file["revision"] + 1
        except NoOutputFileException:
            revision = 1

    file_status_id = file_status_id or get_default_file_status()["id"]

    try:
        output_file = OutputFile.get_by(
            name=name,
            entity_id=entity_id,
            asset_instance_id=asset_instance_id,
            output_type_id=output_type_id,
            task_type_id=task_type_id,
            temporal_entity_id=temporal_entity_id,
            representation=representation,
            revision=revision,
        )

        if output_file is None:
            output_file = OutputFile.create(
                name=name,
                comment=comment,
                extension=extension,
                representation=representation,
                revision=revision,
                entity_id=entity_id,
                asset_instance_id=asset_instance_id,
                person_id=person_id,
                source_file_id=working_file_id,
                output_type_id=output_type_id,
                file_status_id=file_status_id,
                task_type_id=task_type_id,
                nb_elements=nb_elements,
                temporal_entity_id=temporal_entity_id,
            )
            entity = entities_service.get_entity(entity_id)
            events.emit(
                "output-file:new",
                {"output_file_id": output_file.id},
                project_id=entity["project_id"],
            )
        else:
            raise EntryAlreadyExistsException

    except IntegrityError:
        raise EntryAlreadyExistsException

    return output_file.serialize()


def get_working_files_for_task(task_id):
    """
    Return all the working files of the given task, sorted by revision
    from the largest to the smallest.
    """
    working_files = (
        WorkingFile.query.filter_by(task_id=task_id)
        .filter(WorkingFile.revision >= 0)
        .order_by(desc(WorkingFile.revision))
        .all()
    )
    return fields.serialize_models(working_files)


def get_working_files_for_entity(
    entity_id, task_id=None, name=None, relations=False
):
    """
    Return all the working files of the given entity and parameters,
    sorted by revision from the largest to the smallest.
    """
    query = WorkingFile.query.filter_by(entity_id=entity_id)

    if task_id:
        query = query.filter(WorkingFile.task_id == task_id)
    if name:
        query = query.filter(WorkingFile.name == name)

    query = query.filter(WorkingFile.revision >= 0).order_by(
        desc(WorkingFile.revision)
    )

    working_files = query.all()
    return fields.serialize_models(working_files, relations=relations)


def get_next_working_file_revision(task_id, name):
    """
    Return the next available working file revision for the given task and
    name.
    """
    last_working_files = get_last_working_files_for_task(task_id)
    working_file = last_working_files.get(name, None)
    if working_file is not None:
        revision = working_file["revision"] + 1
    else:
        revision = 1
    return revision


def get_next_output_file_revision(
    entity_id,
    output_type_id,
    task_type_id,
    name="main",
    asset_instance_id=None,
    temporal_entity_id=None,
):
    """
    Return the next available output file revision for the given entity,
    output type, task type and name. If an asset instance is given, return
    the next available revision of the instance, not of the entity.
    """
    try:
        last_output = get_last_output_revision(
            output_type_id=output_type_id,
            task_type_id=task_type_id,
            entity_id=entity_id,
            name=name,
            asset_instance_id=asset_instance_id,
            temporal_entity_id=temporal_entity_id,
        )
        return last_output["revision"] + 1
    except NoOutputFileException:
        return 1


def get_last_output_revision(
    entity_id,
    output_type_id,
    task_type_id,
    name="main",
    asset_instance_id=None,
    temporal_entity_id=None,
):
    """
    Return the output file with the highest revision for the given entity,
    output type, task type and name. If an asset instance is given, return
    the last output file of the instance, not of the entity.
    """
    query = (
        OutputFile.query.filter_by(
            output_type_id=output_type_id, task_type_id=task_type_id, name=name
        )
        .filter(OutputFile.revision > 0)
        .order_by(desc(OutputFile.revision))
    )

    if asset_instance_id is None:
        query = query.filter(OutputFile.entity_id == entity_id)
    else:
        query = query.filter(
            OutputFile.asset_instance_id == asset_instance_id,
            OutputFile.temporal_entity_id == temporal_entity_id,
        )

    output_files = query.all()

    if len(output_files) == 0:
        raise NoOutputFileException()

    return output_files[0].serialize()


def get_output_files_for_project(
    project_id,
    task_type_id=None,
    output_type_id=None,
    name=None,
    representation=None,
    file_status_id=None,
):
    """
    Return the output files of the given project, sorted by creation date.
    """
    query = OutputFile.query

    query = _apply_output_file_filters(
        query,
        task_type_id=task_type_id,
        output_type_id=output_type_id,
        name=name,
        representation=representation,
        file_status_id=file_status_id,
    )

    output_files = (
        query.filter(OutputFile.asset_instance_id == None)
        .filter(OutputFile.temporal_entity_id == None)
        .filter(OutputFile.revision >= 0)
        .filter(Entity.project_id == project_id)
        .join(Entity, OutputFile.entity_id == Entity.id)
        .order_by(desc(OutputFile.created_at))
        .all()
    )
    return fields.serialize_models(output_files)


def get_output_files_for_entity(
    entity_id,
    task_type_id=None,
    output_type_id=None,
    name=None,
    representation=None,
    file_status_id=None,
):
    """
    Return the output files of the given entity, sorted by revision.
    """
    query = OutputFile.query.filter_by(entity_id=entity_id)

    query = _apply_output_file_filters(
        query,
        task_type_id=task_type_id,
        output_type_id=output_type_id,
        name=name,
        representation=representation,
        file_status_id=file_status_id,
    )

    query = query.filter(OutputFile.asset_instance_id == None).filter(
        OutputFile.temporal_entity_id == None
    )

    output_files = (
        query.filter(OutputFile.revision >= 0)
        .order_by(desc(OutputFile.revision))
        .all()
    )
    return fields.serialize_models(output_files)


def get_output_files_for_instance(
    asset_instance_id,
    temporal_entity_id,
    task_type_id=None,
    output_type_id=None,
    name=None,
    representation=None,
    file_status_id=None,
):
    """
    Return the output files of the given instance, sorted by revision.
    """
    query = OutputFile.query.filter_by(asset_instance_id=asset_instance_id)

    if temporal_entity_id:
        query = query.filter(
            OutputFile.temporal_entity_id == temporal_entity_id
        )
    query = _apply_output_file_filters(
        query,
        task_type_id=task_type_id,
        output_type_id=output_type_id,
        name=name,
        representation=representation,
        file_status_id=file_status_id,
    )

    output_files = (
        query.filter(OutputFile.revision >= 0)
        .order_by(desc(OutputFile.revision))
        .all()
    )
    return fields.serialize_models(output_files)


def get_last_output_files_for_entity(
    entity_id,
    task_type_id=None,
    output_type_id=None,
    name=None,
    representation=None,
    file_status_id=None,
):
    """
    Return the last output files for the given parameters.

    A subquery gets the maximum revision. Then the given parameters filter
    the result.
    """
    # Query the maximum revision for each possible argument set.
    # Group and filter by file status only if it is given. If not, different
    # groups of files can share the same history with different statuses.
    # This could be very misleading when the user would want to get the last.
    if file_status_id:
        query = OutputFile.query.with_entities(
            OutputFile.task_type_id,
            OutputFile.output_type_id,
            OutputFile.name,
            OutputFile.representation,
            OutputFile.file_status_id,
            func.max(OutputFile.revision).label("MAX"),
        ).group_by(
            OutputFile.task_type_id,
            OutputFile.output_type_id,
            OutputFile.name,
            OutputFile.representation,
            OutputFile.file_status_id,
        )
    else:
        query = OutputFile.query.with_entities(
            OutputFile.task_type_id,
            OutputFile.output_type_id,
            OutputFile.name,
            OutputFile.representation,
            func.max(OutputFile.revision).label("MAX"),
        ).group_by(
            OutputFile.task_type_id,
            OutputFile.output_type_id,
            OutputFile.name,
            OutputFile.representation,
        )

    query = query.filter(OutputFile.entity_id == entity_id).filter(
        OutputFile.asset_instance_id == None
    )
    query = _apply_output_file_filters(
        query,
        task_type_id=task_type_id,
        output_type_id=output_type_id,
        name=name,
        representation=representation,
        file_status_id=file_status_id,
    )
    statement = query.subquery()

    # Make a join query to get the maximum revision and filter by the
    # given arguments.
    query = OutputFile.query.join(
        statement,
        and_(
            OutputFile.entity_id == entity_id,
            OutputFile.asset_instance_id == None,
            OutputFile.task_type_id == statement.c.task_type_id,
            OutputFile.output_type_id == statement.c.output_type_id,
            OutputFile.name == statement.c.name,
            OutputFile.representation == statement.c.representation,
            OutputFile.revision == statement.c.MAX,
        ),
    )

    output_files = query.all()
    return fields.serialize_models(output_files)


def get_last_output_files_for_instance(
    asset_instance_id,
    temporal_entity_id,
    task_type_id=None,
    output_type_id=None,
    name=None,
    representation=None,
    file_status_id=None,
):
    """
    Return the last output files of the given asset instance and temporal
    entity, grouped by task type, output type, name and representation.
    """
    # Query the maximum revision for each possible argument set.
    # Group and filter by file status only if it is given. If not, different
    # groups of files can share the same history with different statuses.
    # This could be very misleading when the user would want to get the last.
    if file_status_id:
        query = OutputFile.query.with_entities(
            OutputFile.asset_instance_id,
            OutputFile.temporal_entity_id,
            OutputFile.task_type_id,
            OutputFile.output_type_id,
            OutputFile.name,
            OutputFile.representation,
            OutputFile.file_status_id,
            func.max(OutputFile.revision).label("MAX"),
        ).group_by(
            OutputFile.asset_instance_id,
            OutputFile.temporal_entity_id,
            OutputFile.task_type_id,
            OutputFile.output_type_id,
            OutputFile.name,
            OutputFile.representation,
            OutputFile.file_status_id,
        )
    else:
        query = OutputFile.query.with_entities(
            OutputFile.asset_instance_id,
            OutputFile.temporal_entity_id,
            OutputFile.task_type_id,
            OutputFile.output_type_id,
            OutputFile.name,
            OutputFile.representation,
            func.max(OutputFile.revision).label("MAX"),
        ).group_by(
            OutputFile.asset_instance_id,
            OutputFile.temporal_entity_id,
            OutputFile.task_type_id,
            OutputFile.output_type_id,
            OutputFile.name,
            OutputFile.representation,
        )
    query = query.filter(OutputFile.asset_instance_id == asset_instance_id)
    query = query.filter(OutputFile.temporal_entity_id == temporal_entity_id)
    query = _apply_output_file_filters(
        query,
        task_type_id=task_type_id,
        output_type_id=output_type_id,
        name=name,
        representation=representation,
        file_status_id=file_status_id,
    )
    statement = query.subquery()

    # Make a join query to get the maximum revision.
    query = OutputFile.query.join(
        statement,
        and_(
            OutputFile.asset_instance_id == statement.c.asset_instance_id,
            OutputFile.temporal_entity_id == statement.c.temporal_entity_id,
            OutputFile.task_type_id == statement.c.task_type_id,
            OutputFile.output_type_id == statement.c.output_type_id,
            OutputFile.name == statement.c.name,
            OutputFile.representation == statement.c.representation,
            OutputFile.revision == statement.c.MAX,
        ),
    )

    output_files = query.all()
    return fields.serialize_models(output_files)


def filter_preview_files_by_project(query, project_id):
    """
    Return the given preview file query limited to the previews of the
    tasks of the given project. Use a subquery, not a join: the project
    filter of the preview file list already joins the task table.
    """
    return query.filter(
        PreviewFile.task_id.in_(
            Task.query.with_entities(Task.id).filter(
                Task.project_id == project_id
            )
        )
    )


def filter_preview_files_by_open_projects(query, access_filter):
    """
    Return the given preview file query limited to the previews of the
    tasks of open projects, then limited by the given access filter.
    """
    return (
        query.join(Task)
        .join(Project)
        .join(
            ProjectStatus,
            Project.project_status_id == ProjectStatus.id,
        )
        .filter(projects_service.build_open_project_filter())
        .filter(access_filter)
    )


def update_extra_preview_revisions_no_commit(
    task_id, revision, new_revision, preview_file_id
):
    """
    Set the given new revision on the previews of the given task that have
    the given revision, except the given preview file. Do not commit: the
    caller commits.
    """
    PreviewFile.query.filter_by(task_id=task_id, revision=revision).filter(
        PreviewFile.id != preview_file_id
    ).update({"revision": new_revision})


def get_preview_file_raw(preview_file_id):
    """
    Return the preview file as an active record.
    """
    try:
        preview_file = PreviewFile.get(preview_file_id)
    except StatementError:
        raise PreviewFileNotFoundException()

    if preview_file is None:
        raise PreviewFileNotFoundException()

    return preview_file


@cache.memoize_function(240)
def get_preview_file(preview_file_id):
    """
    Return the preview file as a dict.
    """
    preview_file = get_preview_file_raw(preview_file_id)
    return preview_file.serialize()


@cache.memoize_function(240)
def get_preview_file_for_access(preview_file_id):
    """
    Return a light version of the preview file for the picture and movie
    download endpoints. These endpoints only:
    - check permissions
    - send a Last-Modified header
    - get the stored versions of a movie.
    Do not load the JSONB annotations and data columns. On long shots,
    they can be several MB. If the response is a static file from disk,
    they take most of the query time.
    """
    try:
        row = (
            PreviewFile.query.with_entities(
                PreviewFile.id,
                PreviewFile.task_id,
                PreviewFile.updated_at,
                PreviewFile.extension,
                PreviewFile.status,
                PreviewFile.data[MOVIE_PREFIXES_KEY].label("movie_prefixes"),
            )
            .filter_by(id=preview_file_id)
            .first()
        )
    except StatementError:
        raise PreviewFileNotFoundException()
    if row is None:
        raise PreviewFileNotFoundException()
    return {
        "id": str(row.id),
        "task_id": str(row.task_id) if row.task_id else None,
        "updated_at": fields.serialize_value(row.updated_at),
        "extension": row.extension,
        "status": getattr(row.status, "code", row.status),
        # None for a preview file that is older than the record. If not,
        # a list of prefixes.
        "movie_prefixes": (
            row.movie_prefixes
            if isinstance(row.movie_prefixes, list)
            else None
        ),
    }


def get_preview_file_data(preview_file):
    """
    Return the data column of the preview file if it is a dict. If not,
    return an empty dict. A PUT can set this bare JSONB column to any
    value.
    """
    return preview_file.data if isinstance(preview_file.data, dict) else {}


def _is_movie_stored(prefix, preview_file_id):
    """
    Return True if the movie of the given preview file is under the given
    prefix. Examine the local download cache first. If the cache has the
    movie, the movie routes do not use the object storage.
    """
    if config.FS_BACKEND != "local":
        file_path = fs.get_cache_file_path(
            config, prefix, preview_file_id, "mp4"
        )
        if not fs.is_invalid_file(file_path):
            return True
    try:
        return file_store.exists_movie(prefix, preview_file_id)
    except Exception:
        logger.warning(
            f"Could not check the store for {prefix}-{preview_file_id}.",
            exc_info=1,
        )
        return False


def probe_movie_prefixes(preview_file_id):
    """
    Ask the storage which versions of the movie exist. This applies to a
    preview file that is older than the record written at storage time.
    It costs one round trip for each prefix.
    """
    return [
        prefix
        for prefix in MOVIE_PREFIXES
        if _is_movie_stored(prefix, preview_file_id)
    ]


def get_movie_prefixes(stored_prefixes, lowdef):
    """
    Return the storage prefixes to try for a movie, best first. First come
    the prefixes that contain the movie, in the order that the route
    prefers. Then come the other prefixes, because a record can be older
    than a movie that was encoded again or copied.
    """
    prefixes = LOWDEF_MOVIE_PREFIXES if lowdef else MOVIE_PREFIXES
    return [prefix for prefix in prefixes if prefix in stored_prefixes] + [
        prefix for prefix in prefixes if prefix not in stored_prefixes
    ]


def record_movie_prefixes_later(
    preview_file_id, served_prefix, recorded_prefixes
):
    """
    Probe the storage for the versions of a movie and write them on the
    preview file. If there is a job queue, do it on the queue. The probe
    costs one round trip for each version, and the first byte of a cold
    movie must not wait for it. If there is no queue, do it inline.
    """
    if config.ENABLE_JOB_QUEUE:
        queue_store.job_queue.enqueue(
            probe_and_record_movie_prefixes,
            args=(preview_file_id, served_prefix, recorded_prefixes),
            job_timeout=60,
        )
    else:
        probe_and_record_movie_prefixes(
            preview_file_id, served_prefix, recorded_prefixes
        )


def probe_and_record_movie_prefixes(
    preview_file_id, served_prefix, recorded_prefixes
):
    """
    Probe the storage for the versions of a movie. If they are different
    from the recorded versions, record them on the preview file. If the
    probe does not find the version that was just served, the probe
    failed: do not record it. This function runs from a job or from a
    request. If there is no app context, it makes its own.
    """
    from flask import has_app_context

    from zou.app import app

    def run():
        stored_prefixes = probe_movie_prefixes(preview_file_id)
        if served_prefix in stored_prefixes and set(stored_prefixes) != set(
            recorded_prefixes or []
        ):
            record_movie_prefixes(preview_file_id, stored_prefixes)

    if has_app_context():
        run()
    else:
        with app.app_context():
            run()


def record_movie_prefixes(preview_file_id, prefixes):
    """
    Record on the preview file the stored versions of its movie. Do not
    send a notification: the clients see no change.
    """
    preview_file = get_preview_file_raw(preview_file_id)
    preview_file.update(
        {
            "data": {
                **get_preview_file_data(preview_file),
                MOVIE_PREFIXES_KEY: prefixes,
            }
        }
    )
    clear_preview_file_cache(preview_file_id)


def get_preview_files_for_task(task_id):
    """
    Return all the preview files of the given task.
    """
    previews = PreviewFile.query.filter_by(task_id=task_id).order_by(
        PreviewFile.revision.desc()
    )
    return fields.serialize_models(previews)


def create_preview_file_raw(
    name,
    revision,
    task_id,
    person_id,
    source="webgui",
    extension="mp4",
    position=1,
):
    """
    Insert a preview file row and return the active record. Do not emit
    an event and do not update the task: the callers do these steps.
    """
    return PreviewFile.create(
        name=name,
        revision=revision,
        source=source,
        task_id=task_id,
        person_id=person_id,
        extension=extension,
        position=position,
        status="processing",
    )


def create_preview_file(
    name,
    revision,
    task_id,
    person_id,
    source="webgui",
    extension="mp4",
    position=1,
):
    """
    Same as create_preview_file_raw, but return the serialized dict.
    """
    return create_preview_file_raw(
        name, revision, task_id, person_id, source, extension, position
    ).serialize()


def update_working_file(working_file_id, data):
    """
    Update the given working file and remove its cache.
    """
    working_file = get_working_file_raw(working_file_id)
    working_file.update(data)
    clear_working_file_cache(working_file_id)
    return working_file.serialize()


def update_output_file(output_file_id, data):
    """
    Update the given output file and remove its cache.
    """
    output_file = get_output_file_raw(output_file_id)
    output_file.update(data)
    clear_output_file_cache(output_file_id)
    return output_file.serialize()


def store_working_file_content(working_file_id, file_path):
    """
    Save the given local file as the content of the given working file, then
    remove the local file. Set the size and the upload date of the working
    file. Return the working file as a dict.
    """
    return update_working_file(
        working_file_id,
        store_file_content("working", working_file_id, file_path),
    )


def store_output_file_content(output_file_id, file_path):
    """
    Save the given local file as the content of the given output file, then
    remove the local file. Set the size and the upload date of the output
    file. Return the output file as a dict.
    """
    return update_output_file(
        output_file_id, store_file_content("output", output_file_id, file_path)
    )


def store_file_content(prefix, file_id, file_path):
    """
    Save the given local file in the file storage, then remove it. Return
    the fields that an upload sets on a working file or an output file.
    """
    try:
        file_store.add_file(prefix, file_id, file_path)
        size = os.path.getsize(file_path)
    finally:
        os.remove(file_path)
    return {
        "uploaded_at": date_helpers.get_utc_now_datetime(),
        "size": size,
    }


def get_output_types_for_entity(entity_id):
    """
    Return the output types of all the output files of the given entity.
    """
    output_types = (
        OutputType.query.join(OutputFile)
        .filter(OutputFile.entity_id == entity_id)
        .order_by(OutputType.name)
        .all()
    )
    return OutputType.serialize_list(output_types)


def get_output_types_for_instance(asset_instance_id, temporal_entity_id=None):
    """
    Return the output types of all the output files of the given instance.
    """
    output_types = (
        OutputType.query.join(OutputFile)
        .filter(
            OutputFile.asset_instance_id == asset_instance_id,
            OutputFile.temporal_entity_id == temporal_entity_id,
        )
        .order_by(OutputType.name)
        .all()
    )
    return OutputType.serialize_list(output_types)


def get_output_files_for_output_type_and_entity(
    entity_id, output_type_id, representation=None
):
    """
    Return the output files of the given entity and output type.
    """
    query = (
        OutputFile.query.filter(OutputFile.entity_id == entity_id)
        .filter(OutputFile.asset_instance_id == None)  # noqa Entity only
        .filter(OutputFile.output_type_id == output_type_id)
        .order_by(desc(OutputFile.revision))
    )

    if representation is not None:
        query = query.filter(OutputFile.representation == representation)

    output_files = query.all()
    return OutputFile.serialize_list(output_files)


def get_output_files_for_output_type_and_asset_instance(
    asset_instance_id, temporal_entity_id, output_type_id, representation=None
):
    """
    Return the output files of the given asset instance and output type.
    """
    query = OutputFile.query.filter(
        OutputFile.asset_instance_id == asset_instance_id,
        OutputFile.output_type_id == output_type_id,
        OutputFile.temporal_entity_id == temporal_entity_id,
    ).order_by(desc(OutputFile.revision))

    if representation is not None:
        query = query.filter(OutputFile.representation == representation)

    output_files = query.all()
    return OutputFile.serialize_list(output_files)


def get_preview_files_for_project(
    project_id, page=-1, limit=None, cursor_id=None
):
    """
    Return the preview files of the given project: all of them, one page,
    or the files after a cursor (see query_utils.get_paginated_results).
    """
    query = (
        PreviewFile.query.join(Task)
        .filter(Task.project_id == project_id)
        .order_by(desc(PreviewFile.updated_at))
    )
    return query_utils.get_paginated_results(
        query, page, limit, cursor_id=cursor_id
    )


def get_preview_background_file_raw(preview_background_file_id):
    """
    Return the preview background file that has the given ID as an active
    record.
    """
    try:
        preview_background = PreviewBackgroundFile.get(
            preview_background_file_id
        )
    except StatementError:
        raise PreviewBackgroundFileNotFoundException

    if preview_background is None:
        raise PreviewBackgroundFileNotFoundException

    return preview_background


@cache.memoize_function(1200)
def get_preview_background_file(preview_background_file_id):
    """
    Return the preview background file that has the given ID as a dict.
    """
    return get_preview_background_file_raw(
        preview_background_file_id
    ).serialize()


@cache.memoize_function(120)
def get_preview_background_files():
    """
    Return all the preview background files.
    """
    return fields.serialize_models(PreviewBackgroundFile.get_all())


def reset_default_preview_background_files(preview_background_file_id):
    """
    Set is_default=False on all the preview background files, except the
    file that has the given ID.
    """
    query = PreviewBackgroundFile.query.filter(
        PreviewBackgroundFile.id != preview_background_file_id,
        PreviewBackgroundFile.is_default == True,
    )
    unseated = [
        str(preview_background.id) for preview_background in query.all()
    ]
    query.update({"is_default": False})
    PreviewBackgroundFile.commit()
    # The rows written here are not the default anymore. The download
    # routes read each row alone. Without this step, these rows stay the
    # default for the full memoization window of twenty minutes.
    for preview_background_id in unseated:
        clear_preview_background_file_cache(preview_background_id)


def update_preview_background_file(preview_background_file_id, data):
    """
    Update the given preview background file and remove its cache.
    """
    preview_background_file = get_preview_background_file_raw(
        preview_background_file_id
    )
    preview_background_file.update(data)
    clear_preview_background_file_cache(preview_background_file_id)
    return preview_background_file.serialize()


def remove_quietly(remove_from_store, prefix, file_id, force=False):
    """
    Mark a stored file as deleted, and ignore a failure. The database row
    is already deleted. An object that stays in the store must not make
    the deletion fail.
    """
    try:
        remove_from_store(prefix, file_id, force=force)
    except Exception:
        logger.warning(
            f"Stored file {prefix}-{file_id} could not be removed.", exc_info=1
        )
