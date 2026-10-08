from collections import defaultdict
from sqlalchemy.exc import IntegrityError

from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.person import Person, DepartmentLink, ROLE_TYPES
from zou.app.models.project import (
    Project,
    ProjectPersonLink,
    ProjectTaskTypeLink,
    ProjectTaskStatusLink,
)
from zou.app.models.project_status import ProjectStatus
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task_type import TaskType
from zou.app.models.task_status import TaskStatus
from zou.app.models.department import Department
from zou.app.services import (
    preview_files_service,
    entity_types_service,
)
from zou.app.exceptions import (
    ProjectNotFoundException,
    WrongParameterException,
)

from zou.app.utils import fields, events, cache
from zou.app import db

from sqlalchemy.exc import StatementError
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import or_
from zou.app import config
import re

# Lower bound of a project movie bitrate in Mbit/s. The upper bound is the
# instance high definition bitrate, MOVIE_HIGHDEF_BITRATE.
MIN_MOVIE_BITRATE = 1


def clear_project_cache(project_id):
    """
    Drop every memoized serialization of given project, and the project lists.
    """
    # Both arguments are given: an omitted default is a cache key of its
    # own, so deleting on the id alone would leave the common entry behind.
    project_id = str(project_id)
    cache.cache.delete_memoized(_get_project_cached, project_id, False)
    cache.cache.delete_memoized(_get_project_cached, project_id, True)
    cache.cache.delete_memoized(get_team_roles, project_id)
    cache.cache.delete_memoized(get_project_by_name)
    cache.cache.delete_memoized(open_projects)


@cache.memoize_function(120)
def open_projects(name=None):
    """
    Return all open projects. Allow to filter projects by name.
    """
    query = (
        Project.query.join(
            ProjectStatus, Project.project_status_id == ProjectStatus.id
        )
        .outerjoin(MetadataDescriptor)
        .filter(ProjectStatus.name.in_(("Active", "open", "Open")))
        .order_by(Project.name)
    )

    if name is not None:
        query = query.filter(Project.name == name)

    return get_projects_with_extra_data(query)


def open_project_ids():
    """
    Return all open project ids. Allow to filter projects by name.
    """
    return [project["id"] for project in open_projects()]


def get_projects_with_extra_data(
    query, for_client=False, vendor_departments=None
):
    """
    Helpers function to attach:
    * First episode name to current project when it's a TV Show.
    * Add metadata descriptors for this project.
    * Add task types and task statuses for this project.
    """
    projects_list = query.all()
    project_ids = [project.id for project in projects_list]
    return serialize_projects_with_extra_data(
        projects_list, [(project_ids, for_client, vendor_departments)]
    )


def get_project_with_extra_data(
    project, for_client=False, vendor_departments=None
):
    """
    Serialize one project row the way the open projects listing does, extra
    data included: a project read by its id, the only way to reach a closed
    one, is then no lesser than a listed one.
    """
    return serialize_projects_with_extra_data(
        [project], [([project.id], for_client, vendor_departments)]
    )[0]


def serialize_projects_with_extra_data(projects_list, descriptor_visibilities):
    """
    Serialize given project rows with their extra data, fetched in one query
    per kind for the whole list. The metadata descriptors are narrowed on a
    role that can be set per project: descriptor_visibilities lists the
    (project_ids, for_client, vendor_departments) triples covering the
    rows, and their descriptors are fetched in one query per triple.
    """
    if not projects_list:
        return []

    project_ids = [p.id for p in projects_list]

    descriptors_by_project = {}
    for ids, for_client, vendor_departments in descriptor_visibilities:
        descriptors_by_project.update(
            _fetch_metadata_descriptors_by_project(
                ids, for_client, vendor_departments
            )
        )
    task_types_by_project = _fetch_task_type_links_by_project(project_ids)
    task_statuses_by_project = _fetch_task_status_links_by_project(project_ids)
    tvshow_project_ids = [
        p.id for p in projects_list if p.production_type == "tvshow"
    ]
    first_episodes_by_project = _fetch_first_episodes_by_project(
        tvshow_project_ids
    )
    return [
        _build_project_dict_with_extra_data(
            project,
            descriptors_by_project,
            task_types_by_project,
            task_statuses_by_project,
            first_episodes_by_project,
        )
        for project in projects_list
    ]


def _fetch_task_type_links_by_project(project_ids):
    """
    Return the task type links of given projects grouped by project.
    """
    task_type_links = ProjectTaskTypeLink.query.filter(
        ProjectTaskTypeLink.project_id.in_(project_ids)
    ).all()
    task_types_by_project = defaultdict(dict)
    for link in task_type_links:
        task_types_by_project[link.project_id][str(link.task_type_id)] = {
            "priority": link.priority,
            "hd_bitrate_compression": link.hd_bitrate_compression,
            "ld_bitrate_compression": link.ld_bitrate_compression,
        }
    return task_types_by_project


def _fetch_task_status_links_by_project(project_ids):
    """
    Return the task status links of given projects grouped by project.
    """
    task_status_links = ProjectTaskStatusLink.query.filter(
        ProjectTaskStatusLink.project_id.in_(project_ids)
    ).all()
    task_statuses_by_project = defaultdict(dict)
    for link in task_status_links:
        task_statuses_by_project[link.project_id][str(link.task_status_id)] = {
            "priority": link.priority,
            "roles_for_board": fields.serialize_list(link.roles_for_board),
        }
    return task_statuses_by_project


def _fetch_first_episodes_by_project(project_ids):
    """
    Return the first episode of each given project, the one the clients
    land on when they open a TV show.
    """
    if not project_ids:
        return {}

    episode_type = entity_types_service.get_episode_type()
    first_episodes_by_project = {}

    episodes = (
        Entity.query.filter(
            Entity.project_id.in_(project_ids),
            Entity.entity_type_id == episode_type["id"],
            Entity.status == "running",
        )
        .order_by(Entity.project_id, Entity.name)
        .all()
    )

    seen_projects = set()
    for episode in episodes:
        if episode.project_id not in seen_projects:
            first_episodes_by_project[episode.project_id] = episode
            seen_projects.add(episode.project_id)

    missing_projects = set(project_ids) - seen_projects
    if missing_projects:
        fallback_episodes = (
            Entity.query.filter(
                Entity.project_id.in_(missing_projects),
                Entity.entity_type_id == episode_type["id"],
            )
            .order_by(Entity.project_id, Entity.name)
            .all()
        )

        for episode in fallback_episodes:
            if episode.project_id not in first_episodes_by_project:
                first_episodes_by_project[episode.project_id] = episode

    return first_episodes_by_project


def _serialize_descriptor(descriptor):
    """
    Serialize a metadata descriptor with the departments it is limited to.
    """
    return {
        "id": fields.serialize_value(descriptor.id),
        "name": descriptor.name,
        "field_name": descriptor.field_name,
        "data_type": fields.serialize_value(descriptor.data_type),
        "choices": descriptor.choices,
        "for_client": descriptor.for_client or False,
        "entity_type": descriptor.entity_type,
        "task_type_id": fields.serialize_value(descriptor.task_type_id),
        "position": descriptor.position,
        "departments": [
            str(department.id) for department in descriptor.departments
        ],
    }


def _build_project_dict_with_extra_data(
    project,
    descriptors_by_project,
    task_types_by_project,
    task_statuses_by_project,
    first_episodes_by_project,
):
    """
    Assemble one project dict from the project row and the maps prefetched
    for the whole page, so no query is issued per project.
    """
    project_dict = project.serialize(relations=True)

    project_dict["descriptors"] = [
        _serialize_descriptor(descriptor)
        for descriptor in descriptors_by_project.get(project.id, [])
    ]
    task_type_links = task_types_by_project.get(project.id, {})
    project_dict["task_type_links"] = task_type_links
    project_dict["task_types_priority"] = {
        task_type_id: link["priority"]
        for task_type_id, link in task_type_links.items()
    }
    project_dict["task_statuses_link"] = task_statuses_by_project.get(
        project.id, {}
    )
    if project.production_type == "tvshow":
        episode = first_episodes_by_project.get(project.id)
        if episode is not None:
            project_dict["first_episode_id"] = fields.serialize_value(
                episode.id
            )

    return project_dict


def get_projects():
    """
    Return all projects, with their Project-scoped metadata descriptors so the
    admin productions view can render Project metadata columns.
    """
    query = (
        Project.query.join(
            ProjectStatus, Project.project_status_id == ProjectStatus.id
        )
        .add_columns(ProjectStatus.name)
        .order_by(Project.name)
    )

    entries = query.all()
    if not entries:
        return []

    descriptors_by_project = _fetch_all_project_descriptors_by_project()

    result = []
    for project, project_status_name in entries:
        data = project.serialize()
        data["project_status_name"] = project_status_name
        data["descriptors"] = [
            _serialize_descriptor(descriptor)
            for descriptor in descriptors_by_project.get(project.id, [])
        ]
        result.append(data)
    return result


@cache.memoize_function(480)
def get_project_statuses():
    """
    Return every project status.
    """
    return fields.serialize_models(ProjectStatus.get_all())


def get_or_create_open_status():
    """
    Return open status. If it does not exist, it creates it.
    """
    return get_or_create_project_status("Open")


@cache.memoize_function(480)
def get_open_status():
    """
    Return open status. If it does not exist, it creates it.
    """
    return get_or_create_project_status("Open")


@cache.memoize_function(120)
def get_closed_status():
    """
    Return closed status. If it does not exist, it creates it.
    """
    return get_or_create_project_status("Closed")


def get_or_create_project_status(name):
    """
    Return given status. If it does not exist, it creates it.
    """
    project_status = ProjectStatus.get_by(name=name)
    if project_status is None:
        project_status = ProjectStatus(name=name, color="#000000")
        project_status.save()
    return project_status.serialize()


def save_project_status(project_statuses):
    """
    Save in database all project status given in parameter.
    """
    result = []
    filtered_satuses = (x for x in project_statuses if x is not None)

    for status in filtered_satuses:
        project_status = get_or_create_project_status(status)
        result.append(project_status)
    return result


def get_project_raw(project_id):
    """
    Get project matching given id, as active record. Raises an exception if
    project is not found.
    """
    try:
        project = Project.get(project_id)
    except StatementError:
        raise ProjectNotFoundException()

    if project is None:
        raise ProjectNotFoundException()

    return project


@cache.memoize_function(240)
def _get_project_cached(project_id, relations=False):
    return get_project_raw(project_id).serialize(relations=relations)


def get_project(project_id, relations=False):
    """
    Get project matching given id, as a dict. Raises an exception if project is
    not found.

    The id is normalised before it reaches the memoization, which keys on the
    argument: a UUID and its string form would otherwise be two entries, and
    clear_project_cache would only ever drop one of them.
    """
    return _get_project_cached(str(project_id), relations)


@cache.memoize_function(120)
def get_project_by_name(project_name):
    """
    Get project matching given name. Raises an exception if project is not
    found.
    """
    project = Project.query.filter(Project.name.ilike(project_name)).first()

    if project is None:
        raise ProjectNotFoundException()

    return project.serialize()


def update_project(project_id, data):
    """
    Update project matching given id with data from *data* dict.
    """
    project = get_project_raw(project_id)
    project.update(data)
    clear_project_cache(project_id)
    events.emit("project:update", {}, project_id=project_id)
    return project.serialize()


def _check_project_role(role):
    """
    Refuse a role a project link cannot carry. admin is global by design,
    and anything else is a typo: the column is an enum, so writing it
    raises a KeyError deep in the driver rather than answering the caller.
    """
    if role is None:
        return
    if role == "admin":
        raise WrongParameterException(
            "admin is a global role and cannot be set per project"
        )
    if role not in [code for code, _ in ROLE_TYPES]:
        raise WrongParameterException(f"{role} is not a role")


def add_team_member(project_id, person_id, role=None):
    """
    Add a person listed in database to the project team, with an optional
    project-specific role. The role is validated before the membership is
    created so an invalid role leaves no partial state behind.
    """
    _check_project_role(role)
    project = _add_to_list_attr(project_id, Person, person_id, "team")
    if role is not None:
        update_team_member_role(project_id, person_id, role)
        project = get_project_raw(project_id).serialize()
    return project


def remove_team_member(project_id, person_id):
    """
    Remove a person listed in database from the the project team.
    """
    return _remove_from_list_attr(project_id, Person, person_id, "team")


def update_team_member_role(project_id, person_id, role):
    """
    Set the role of given person on given project. A None role restores
    inheritance of the person's global role.
    """
    _check_project_role(role)
    link = ProjectPersonLink.query.filter_by(
        project_id=project_id, person_id=person_id
    ).first()
    if link is None:
        raise WrongParameterException(
            "Person is not a member of the project team"
        )
    link.role = role
    db.session.commit()
    clear_project_cache(str(project_id))
    events.emit("project:update", {}, project_id=str(project_id))
    return {
        "project_id": str(link.project_id),
        "person_id": str(link.person_id),
        "role": (
            getattr(link.role, "code", link.role)
            if link.role is not None
            else None
        ),
    }


def get_team_raw(project_id):
    """
    Return the team members of given project as active records, with
    their departments eager-loaded: serializing them person by person
    lazy-loads one departments query per member otherwise.
    """
    project = get_project_raw(project_id)
    return (
        Person.query.options(selectinload(Person.departments))
        .filter(Person.id.in_([person.id for person in project.team]))
        .all()
    )


@cache.memoize_function(120)
def get_team_roles(project_id):
    """
    Return a dict mapping person ids to their explicit role on given
    project. Persons inheriting their global role are absent from the dict.
    Memoized: every project access check of a non-admin reads it. Always
    call it with the project id as a string, the cache is keyed on it.
    """
    return {
        str(link.person_id): getattr(link.role, "code", link.role)
        for link in ProjectPersonLink.query.filter_by(
            project_id=project_id
        ).filter(ProjectPersonLink.role.isnot(None))
    }


def add_asset_type_setting(project_id, asset_type_id):
    """
    Add an asset type listed in database to the the project asset types.
    """
    return _add_to_list_attr(
        project_id, EntityType, asset_type_id, "asset_types"
    )


def remove_asset_type_setting(project_id, asset_type_id):
    """
    Remove an asset type listed in database from the the project asset types.
    """
    return _remove_from_list_attr(
        project_id, EntityType, asset_type_id, "asset_types"
    )


def add_task_type_setting(
    project_id,
    task_type_id,
    priority=None,
    bitrates=None,
):
    """
    Add a task type listed in database to the the project task types. An
    existing link keeps its priority and gets the bitrates when given.
    """
    project_id = str(project_id)
    task_type_id = str(task_type_id)
    if not task_type_id or not fields.is_valid_id(task_type_id):
        raise WrongParameterException(
            "task_type_id is required and must be a valid UUID"
        )

    project = get_project_raw(project_id)
    if bitrates is not None:
        validate_movie_bitrates(bitrates, inherited=project.serialize())
    link = ProjectTaskTypeLink.get_by(
        task_type_id=task_type_id, project_id=project_id
    )
    if not link:
        ProjectTaskTypeLink.create(
            task_type_id=task_type_id,
            project_id=project_id,
            priority=priority,
            **(bitrates or {}),
        )
    elif bitrates is not None:
        link.update(bitrates)
    return _save_project(project)


def remove_task_type_setting(project_id, task_type_id):
    """
    Remove a task status listed in database from the the project task types.
    """
    return _remove_from_list_attr(
        project_id, TaskType, task_type_id, "task_types"
    )


def add_task_status_setting(project_id, task_status_id):
    """
    Add a task status listed in database to the the project task statuses.
    """
    return _add_to_list_attr(
        project_id, TaskStatus, task_status_id, "task_statuses"
    )


def remove_task_status_setting(project_id, task_status_id):
    """
    Remove a task status listed in database from the the project task statuses.
    """
    return _remove_from_list_attr(
        project_id, TaskStatus, task_status_id, "task_statuses"
    )


def update_project_settings(
    project_id,
    task_types=None,
    task_status_ids=None,
    asset_type_ids=None,
    replace_task_types=False,
):
    """
    Add several task types (with their priority), task statuses and asset
    types to the project settings in a single operation. Unknown ids are
    skipped. When replace_task_types is set, the given task type list is the
    full wanted set: existing links absent from it are removed.
    """
    project = get_project_raw(project_id)
    project_id = str(project.id)

    wanted_task_types = {}
    for entry in task_types or []:
        wanted_task_types[str(entry["task_type_id"])] = entry.get("priority")

    existing_links = {
        str(link.task_type_id): link
        for link in ProjectTaskTypeLink.query.filter_by(project_id=project_id)
    }
    for task_type_id, priority in wanted_task_types.items():
        link = existing_links.get(task_type_id)
        if link is None:
            if TaskType.get(task_type_id) is not None:
                ProjectTaskTypeLink.create(
                    task_type_id=task_type_id,
                    project_id=project_id,
                    priority=priority,
                )
        elif priority is not None and link.priority != priority:
            link.update({"priority": priority})
    if replace_task_types:
        for task_type_id, link in existing_links.items():
            if task_type_id not in wanted_task_types:
                task_type = TaskType.get(task_type_id)
                if task_type is not None:
                    project.task_types.remove(task_type)

    task_status_map = {
        str(status.id): status for status in project.task_statuses
    }
    for task_status_id in task_status_ids or []:
        task_status = TaskStatus.get(task_status_id)
        if (
            task_status is not None
            and str(task_status.id) not in task_status_map
        ):
            project.task_statuses.append(task_status)
            task_status_map[str(task_status.id)] = task_status

    asset_type_map = {
        str(asset_type.id): asset_type for asset_type in project.asset_types
    }
    for asset_type_id in asset_type_ids or []:
        asset_type = EntityType.get(asset_type_id)
        if asset_type is not None and str(asset_type.id) not in asset_type_map:
            project.asset_types.append(asset_type)
            asset_type_map[str(asset_type.id)] = asset_type

    return _save_project(project)


def add_status_automation_setting(project_id, status_automation_id):
    """
    Add a status automation listed in database to the project status automations.
    """
    return _add_to_list_attr(
        project_id,
        StatusAutomation,
        status_automation_id,
        "status_automations",
    )


def remove_status_automation_setting(project_id, status_automation_id):
    """
    Remove a status automation listed in database from the project status
    automations.
    """
    return _remove_from_list_attr(
        project_id,
        StatusAutomation,
        status_automation_id,
        "status_automations",
    )


def add_preview_background_file_setting(
    project_id, preview_background_file_id
):
    """
    Add a preview background file listed in database to the project backgrounds.
    """
    return _add_to_list_attr(
        project_id,
        PreviewBackgroundFile,
        preview_background_file_id,
        "preview_background_files",
    )


def remove_preview_background_file_setting(
    project_id, preview_background_file_id
):
    """
    Remove a preview background file listed in database from the project backgrounds.
    """
    return _remove_from_list_attr(
        project_id,
        PreviewBackgroundFile,
        preview_background_file_id,
        "preview_background_files",
    )


def _add_to_list_attr(project_id, model_class, model_id, list_attr):
    """
    Append a row to one of the project settings lists, no-op when already there.
    """
    project = get_project_raw(project_id)
    model = model_class.get(model_id)
    if model is None:
        model_name = model_class.__name__
        raise WrongParameterException(
            f"{model_name} with id {model_id} not found"
        )
    if str(model.id) not in [str(m.id) for m in getattr(project, list_attr)]:
        getattr(project, list_attr).append(model)
        try:
            return _save_project(project)
        except IntegrityError:
            # A concurrent request already added the same link. The check
            # above is not atomic, so treat the duplicate as a no-op and
            # return the up-to-date project. The failed transaction has
            # already been rolled back by Model.save().
            return get_project_raw(project_id).serialize()
    else:
        return project.serialize()


def _remove_from_list_attr(project_id, model_class, model_id, list_attr):
    """
    Remove a row from one of the project settings lists, no-op when absent.
    """
    project = get_project_raw(project_id)
    model = model_class.get(model_id)
    try:
        getattr(project, list_attr).remove(model)
    except ValueError:
        pass
    return _save_project(project)


def _save_project(project):
    """
    Persist the project, drop its cache and notify the clients.
    """
    project.save()
    clear_project_cache(str(project.id))
    events.emit("project:update", {}, project_id=str(project.id))
    return project.serialize()


def is_tv_show(project):
    """
    Return True when given project is a TV show, so episodes apply.
    """
    return project["production_type"] == "tvshow"


def is_open(project):
    """
    Return True when given project is still open.
    """
    open_status = get_open_status()
    return project["project_status_id"] == open_status["id"]


def _notify_project_settings_change(project_id):
    """
    Drop the project cache and notify the clients after a change on one of its
    task type or task status links. Those tables are not the project, but the
    clients read them through it, so the project is what they have to refetch.
    """
    project_id = str(project_id)
    clear_project_cache(project_id)
    events.emit("project:update", {}, project_id=project_id)


def create_project_task_type_link(project_id, task_type_id, priority):
    """
    Link a task type to given project with a priority, or update the
    priority when the link already exists.
    """
    if not task_type_id or not fields.is_valid_id(task_type_id):
        raise WrongParameterException(
            "task_type_id is required and must be a valid UUID"
        )

    task_type_link = ProjectTaskTypeLink.get_by(
        project_id=project_id, task_type_id=task_type_id
    )

    if priority is not None:
        priority = int(priority)

    if task_type_link is None:
        task_type_link = ProjectTaskTypeLink.create(
            project_id=project_id, task_type_id=task_type_id, priority=priority
        )
    else:
        task_type_link.update({"priority": priority})

    task_type_link_dict = task_type_link.serialize()
    _notify_project_settings_change(task_type_link_dict["project_id"])
    return task_type_link_dict


def create_project_task_status_link(
    project_id, task_status_id, priority, roles_for_board=None
):
    """
    Link a task status to given project, or update the priority and the
    board roles when the link already exists.
    """
    if not task_status_id or not fields.is_valid_id(task_status_id):
        raise WrongParameterException(
            "task_status_id is required and must be a valid UUID"
        )

    task_status_link = ProjectTaskStatusLink.get_by(
        project_id=project_id, task_status_id=task_status_id
    )

    if priority is not None:
        priority = int(priority)

    if task_status_link is None:
        task_status_link = ProjectTaskStatusLink.create(
            project_id=project_id,
            task_status_id=task_status_id,
            priority=priority,
            roles_for_board=roles_for_board,
        )
    else:
        task_status_link.update(
            {"priority": priority, "roles_for_board": roles_for_board}
        )

    task_status_link_dict = task_status_link.serialize()
    _notify_project_settings_change(task_status_link_dict["project_id"])
    return task_status_link_dict


def set_project_task_type_link_priorities(project_id, task_type_ids):
    """
    Set the priority of the project's task type links from the given ordered
    id list (priority = position, 1-based). Only existing links are touched,
    so a reorder never creates links. Returns the updated links.
    """
    links = []
    for priority, task_type_id in enumerate(task_type_ids, start=1):
        link = ProjectTaskTypeLink.get_by(
            project_id=project_id, task_type_id=task_type_id
        )
        if link is not None:
            link.update({"priority": priority})
            links.append(link.serialize())
    _notify_project_settings_change(project_id)
    return links


def set_project_task_status_link_priorities(project_id, task_status_ids):
    """
    Set the priority of the project's task status links from the given ordered
    id list (priority = position, 1-based). Only the priority is updated, so
    the board roles of each link are preserved. Returns the updated links.
    """
    links = []
    for priority, task_status_id in enumerate(task_status_ids, start=1):
        link = ProjectTaskStatusLink.get_by(
            project_id=project_id, task_status_id=task_status_id
        )
        if link is not None:
            link.update({"priority": priority})
            links.append(link.serialize())
    _notify_project_settings_change(project_id)
    return links


def get_project_task_types_raw(project_id, for_entity=None):
    """
    Task types configured on given project as active records, narrowed to
    the ones of an entity kind when for_entity is given. for_entity was
    added nullable in 2018 and only ever backfilled for shots, so a task
    type predating it reads NULL and means "Asset", the model default.
    """
    query = TaskType.query.join(ProjectTaskTypeLink).filter(
        ProjectTaskTypeLink.project_id == project_id
    )
    if for_entity == "Asset":
        query = query.filter(
            or_(TaskType.for_entity == "Asset", TaskType.for_entity.is_(None))
        )
    elif for_entity is not None:
        query = query.filter(TaskType.for_entity == for_entity)
    return query.all()


def get_project_task_types(project_id):
    """
    Return the task types configured on given project.
    """
    project = get_project_raw(project_id)
    return Project.serialize_list(project.task_types)


def get_project_task_statuses(project_id):
    """
    Return the task statuses configured on given project.
    """
    project = get_project_raw(project_id)
    return Project.serialize_list(project.task_statuses)


def get_project_status_automations(project_id):
    """
    Return the status automations configured on given project.
    """
    project = get_project_raw(project_id)
    return Project.serialize_list(project.status_automations)


def get_project_preview_background_files(project_id):
    """
    Return the preview background files configured on given project.
    """
    project = get_project_raw(project_id)
    return Project.serialize_list(project.preview_background_files)


def get_project_fps(project_id):
    """
    Return fps set at project level or default fps if it not set.
    """
    project = get_project(project_id)
    return float(project["fps"] or "25.00")


def get_task_type_priority_map(project_id, for_entity="Asset"):
    """
    Return a dict allowing to match a task type id with a priority.
    """
    task_types = (
        ProjectTaskTypeLink.query.join(TaskType)
        .filter(ProjectTaskTypeLink.project_id == project_id)
        .filter(TaskType.for_entity == for_entity)
    ).all()
    return {
        str(task_type_link.task_type_id): task_type_link.priority
        for task_type_link in task_types
    }


def get_task_type_links(project_id, for_entity="Asset"):
    """
    Return a lisk of links for given project and entity type.
    """
    task_type_links = (
        ProjectTaskTypeLink.query.join(TaskType)
        .filter(ProjectTaskTypeLink.project_id == project_id)
        .filter(TaskType.for_entity == for_entity)
        .order_by(ProjectTaskTypeLink.priority.desc())
    ).all()
    return ProjectTaskTypeLink.serialize_list(task_type_links)


def get_department_team(project_id, department_id):
    """
    Get all persons in a given department for a given project.
    """
    persons = (
        Person.query.join(
            ProjectPersonLink, ProjectPersonLink.person_id == Person.id
        )
        .join(DepartmentLink, DepartmentLink.person_id == Person.id)
        .filter(ProjectPersonLink.project_id == project_id)
        .filter(DepartmentLink.department_id == department_id)
    ).all()
    return persons


def build_open_project_filter():
    """
    Query filter for project to retrieve only open projects.
    """
    open_status = get_open_status()
    return Project.project_status_id == open_status["id"]


def narrow_metadata_descriptors(
    query, for_client=False, vendor_departments=None
):
    """
    Narrow given metadata descriptors query to the ones a client or a vendor
    may read.
    """
    narrowing = build_descriptor_narrowing(for_client, vendor_departments)
    if narrowing is None:
        return query
    return query.filter(narrowing)


def _fetch_metadata_descriptors_by_project(
    project_ids, for_client=False, vendor_departments=None
):
    """
    Return the metadata descriptors of given projects grouped by project,
    in one query. Clients only get the descriptors published to them, and
    a vendor only the ones of their departments.
    """
    descriptors_query = narrow_metadata_descriptors(
        MetadataDescriptor.query.filter(
            MetadataDescriptor.project_id.in_(project_ids)
        ),
        for_client,
        vendor_departments,
    )
    # Eager-load departments to avoid N+1 when serializing descriptors
    descriptors_query = descriptors_query.options(
        joinedload(MetadataDescriptor.departments)
    )

    all_descriptors = descriptors_query.all()
    descriptors_by_project = defaultdict(list)
    for desc in all_descriptors:
        descriptors_by_project[desc.project_id].append(desc)
    return descriptors_by_project


def _fetch_all_project_descriptors_by_project():
    """
    Return the metadata descriptors of every project grouped by project.
    """
    descriptors = (
        MetadataDescriptor.query.filter(
            MetadataDescriptor.entity_type == "Project"
        )
        .options(joinedload(MetadataDescriptor.departments))
        .all()
    )
    by_project = defaultdict(list)
    for descriptor in descriptors:
        by_project[descriptor.project_id].append(descriptor)
    return by_project


def build_descriptor_narrowing(for_client=False, vendor_departments=None):
    """
    Return the criterion keeping the metadata descriptors a client or a
    vendor may read, None when nothing is narrowed: a client only gets the
    ones published to clients, a vendor only the ones of their departments
    or of no department. Shared by every route serving descriptors, so that
    they all apply the same rule.
    """
    if for_client:
        return MetadataDescriptor.for_client == True
    if vendor_departments is not None:
        return or_(
            MetadataDescriptor.departments == None,
            MetadataDescriptor.departments.any(
                Department.id.in_(vendor_departments)
            ),
        )
    return None


def is_valid_resolution(resolution):
    """
    Return true if the dimension follows the 1920x1080 pattern.
    """
    return resolution is not None and bool(
        re.match(r"^\d{3,4}x\d{3,4}$", resolution)
    )


def is_valid_partial_resolution(resolution):
    """
    Return true if the dimension follows the x1080 pattern.
    """
    return resolution is not None and bool(re.match(r"^x\d{3,4}$", resolution))


def validate_resolution(resolution):
    """
    Raise WrongParameterException if the resolution is set but doesn't
    match the canonical "WIDTHxHEIGHT" or "xHEIGHT" format. Empty values
    (None or "") are accepted: the runtime falls back to 1080p.

    Used at the CRUD boundary so users get an immediate 400 instead of
    a silent fallback at normalization time.
    """
    if resolution in (None, ""):
        return
    if not (
        is_valid_resolution(resolution)
        or is_valid_partial_resolution(resolution)
    ):
        raise WrongParameterException(
            f"Invalid resolution {resolution}. Expected format: '1920x1080' or 'x1080'."
        )


def validate_movie_bitrate(bitrate):
    """
    Raise WrongParameterException when a movie bitrate is set but is not
    an integer number of Mbit/s between 1 and the instance high definition
    bitrate.
    """
    if bitrate is None:
        return
    if (
        not isinstance(bitrate, int)
        or isinstance(bitrate, bool)
        or not MIN_MOVIE_BITRATE <= bitrate <= config.MOVIE_HIGHDEF_BITRATE
    ):
        raise WrongParameterException(
            f"Invalid bitrate {bitrate}. Expected an integer number of "
            f"Mbit/s between {MIN_MOVIE_BITRATE} and "
            f"{config.MOVIE_HIGHDEF_BITRATE}."
        )


def validate_movie_bitrates(data, current=None, inherited=None):
    """
    Check the hd_bitrate_compression and ld_bitrate_compression a settings
    change sets: each within bounds, and a low definition one never above
    the high definition bitrate the movies will get. That one resolves as
    the encoder does: data, then current (the object being changed) for a
    bitrate absent from data, then inherited (the level the object falls
    back on), then the config. Bitrates the change leaves as they are, sent
    back or not, are not checked: the encoder caps them, as it caps an
    unset low definition bitrate.
    """
    current = current or {}
    changes = {
        key: data[key]
        for key in ("hd_bitrate_compression", "ld_bitrate_compression")
        if key in data and data[key] != current.get(key)
    }
    for bitrate in changes.values():
        validate_movie_bitrate(bitrate)
    lowdef = changes.get("ld_bitrate_compression")
    if lowdef is None:
        return
    highdef, _ = get_movie_bitrates(inherited or {}, {**current, **data})
    if lowdef > highdef:
        raise WrongParameterException(
            f"The low definition bitrate ({lowdef}) cannot exceed the high "
            f"definition one ({highdef})."
        )


def get_movie_bitrates(project, task_type_link=None):
    """
    Return the (highdef, lowdef) bitrates in Mbit/s the movies of a task
    are encoded at: the task type link's, then the project's, then the
    config's. Each version resolves on its own.
    """
    bitrates = []
    for key, default in (
        ("hd_bitrate_compression", config.MOVIE_HIGHDEF_BITRATE),
        ("ld_bitrate_compression", config.MOVIE_LOWDEF_BITRATE),
    ):
        value = (task_type_link or {}).get(key) or project.get(key)
        bitrates.append(value or default)
    # Writes only check the bitrates they change: a stored or inherited one
    # can exceed a ceiling lowered since, or a low definition one its high
    # definition one. The encoder never exceeds the ceilings.
    highdef = min(bitrates[0], config.MOVIE_HIGHDEF_BITRATE)
    lowdef = min(bitrates[1], highdef)
    return highdef, lowdef
