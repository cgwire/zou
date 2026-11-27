import re
from collections import defaultdict

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import joinedload, selectinload

from zou.app import config, db
from zou.app.exceptions import (
    ProjectNotFoundException,
    SoftwareNotFoundException,
    TaskStatusNotFoundException,
    WrongParameterException,
)
from zou.app.models.department import Department
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType, TaskTypeAssetTypeLink
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.person import ROLE_TYPES, DepartmentLink, Person
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.project import (
    Project,
    ProjectAssetTypeTaskTypeLink,
    ProjectPersonLink,
    ProjectTaskStatusLink,
    ProjectTaskTypeLink,
    ProjectTaskTypeSoftwareLink,
)
from zou.app.models.project_status import ProjectStatus
from zou.app.models.software import Software
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.services import (
    entity_types_service,
)
from zou.app.services.base_service import get_instance
from zou.app.utils import cache, events, fields

# Lower limit of a project movie bitrate in Mbit/s. The upper limit is the
# high definition bitrate of the instance, MOVIE_HIGHDEF_BITRATE.
MIN_MOVIE_BITRATE = 1

# The collections that a project dict serializes.
PROJECT_RELATIONS = [
    Project.team,
    Project.asset_types,
    Project.task_statuses,
    Project.task_types,
    Project.status_automations,
    Project.preview_background_files,
]


def with_project_relations(query):
    """
    Load the collections of the listed projects with one query for each
    collection, not one query for each project at serialization.
    """
    return query.options(
        *[selectinload(relation) for relation in PROJECT_RELATIONS]
    )


def clear_project_cache(project_id):
    """
    Drop all the memoized serializations of the given project, and the
    project lists.
    """
    # Give both arguments. An omitted default is a different cache key.
    # A delete with only the ID keeps the usual entry in the cache.
    project_id = str(project_id)
    cache.cache.delete_memoized(_get_project_cached, project_id, False)
    cache.cache.delete_memoized(_get_project_cached, project_id, True)
    cache.cache.delete_memoized(get_team_person_ids, project_id)
    cache.cache.delete_memoized(get_team_roles, project_id)
    cache.cache.delete_memoized(get_project_by_name)
    cache.cache.delete_memoized(open_projects)


@cache.memoize_function(120)
def open_projects(name=None):
    """
    Return all the open projects. A filter on the project name is possible.
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
    Return the IDs of all the open projects.
    """
    return [project["id"] for project in open_projects()]


def get_projects_with_extra_data(
    query, for_client=False, vendor_departments=None
):
    """
    Run the given project query and return the projects as dicts with
    their extra data:

    - the project status name.
    - the metadata descriptors.
    - the task type and task status links.
    - the asset type workflows.
    - for a TV show, the ID of the first episode.
    """
    projects_list = with_project_relations(query).all()
    project_ids = [project.id for project in projects_list]
    return serialize_projects_with_extra_data(
        projects_list, [(project_ids, for_client, vendor_departments)]
    )


def get_project_with_extra_data(
    project, for_client=False, vendor_departments=None
):
    """
    Serialize one project row as the open projects list does, with the
    extra data. This is the only way to read a closed project, so a project
    read by its ID has the same data as a listed project.
    """
    return serialize_projects_with_extra_data(
        [project], [([project.id], for_client, vendor_departments)]
    )[0]


def serialize_projects_with_extra_data(projects_list, descriptor_visibilities):
    """
    Serialize the given project rows with their extra data. Get the extra
    data with one query for each kind, for the full list. A role can be set
    for each project, and the metadata descriptors depend on this role.
    descriptor_visibilities lists the (project_ids, for_client,
    vendor_departments) triples for the rows. Get their descriptors with
    one query for each triple.
    """
    if not projects_list:
        return []

    project_ids = [p.id for p in projects_list]

    status_names = dict(
        db.session.query(ProjectStatus.id, ProjectStatus.name)
        .filter(
            ProjectStatus.id.in_({p.project_status_id for p in projects_list})
        )
        .all()
    )
    descriptors_by_project = {}
    for ids, for_client, vendor_departments in descriptor_visibilities:
        descriptors_by_project.update(
            _fetch_metadata_descriptors_by_project(
                ids, for_client, vendor_departments
            )
        )
    task_types_by_project = _fetch_task_type_links_by_project(project_ids)
    task_statuses_by_project = _fetch_task_status_links_by_project(project_ids)
    workflows_by_project = _fetch_asset_type_workflows_by_project(project_ids)
    tvshow_project_ids = [
        p.id for p in projects_list if p.production_type == "tvshow"
    ]
    first_episodes_by_project = _fetch_first_episodes_by_project(
        tvshow_project_ids
    )
    return [
        _build_project_dict_with_extra_data(
            project,
            status_names,
            descriptors_by_project,
            task_types_by_project,
            task_statuses_by_project,
            workflows_by_project,
            first_episodes_by_project,
        )
        for project in projects_list
    ]


def _fetch_task_type_links_by_project(project_ids):
    """
    Return the task type links of the given projects, grouped by project.
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
            "is_client_visible": link.is_client_visible,
        }
    return task_types_by_project


def _fetch_task_status_links_by_project(project_ids):
    """
    Return the task status links of the given projects, grouped by project.
    """
    task_status_links = ProjectTaskStatusLink.query.filter(
        ProjectTaskStatusLink.project_id.in_(project_ids)
    ).all()
    task_statuses_by_project = defaultdict(dict)
    for link in task_status_links:
        task_statuses_by_project[link.project_id][str(link.task_status_id)] = {
            "priority": link.priority,
            "roles_for_board": fields.serialize_list(link.roles_for_board),
            "is_client_allowed": link.is_client_allowed,
        }
    return task_statuses_by_project


def _fetch_asset_type_workflows_by_project(project_ids):
    """
    Return the asset type workflows specific to the given projects, grouped
    by project and then by asset type.
    """
    links = ProjectAssetTypeTaskTypeLink.query.filter(
        ProjectAssetTypeTaskTypeLink.project_id.in_(project_ids)
    ).all()
    workflows_by_project = defaultdict(lambda: defaultdict(list))
    for link in links:
        workflows_by_project[link.project_id][str(link.asset_type_id)].append(
            str(link.task_type_id)
        )
    return workflows_by_project


def _fetch_first_episodes_by_project(project_ids):
    """
    Return the first episode of each given project. The clients open this
    episode first when they open a TV show.
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
    status_names,
    descriptors_by_project,
    task_types_by_project,
    task_statuses_by_project,
    workflows_by_project,
    first_episodes_by_project,
):
    """
    Make one project dict from the project row and from the maps that the
    caller got before for the full page. Because of this, no query occurs for
    each project.
    """
    project_dict = project.serialize(relations=True)
    project_dict["project_status_name"] = status_names.get(
        project.project_status_id
    )

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
    project_dict["asset_type_workflows"] = workflows_by_project.get(
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
    Return all the projects with the extra data, as for a project read by
    its ID.
    """
    return get_projects_with_extra_data(
        Project.query.join(
            ProjectStatus, Project.project_status_id == ProjectStatus.id
        ).order_by(Project.name)
    )


@cache.memoize_function(480)
def get_project_statuses():
    """
    Return all the project statuses.
    """
    return fields.serialize_models(ProjectStatus.get_all())


def get_or_create_open_status():
    """
    Return the open status. If it does not exist, create it.
    """
    return get_or_create_project_status("Open")


@cache.memoize_function(480)
def get_open_status():
    """
    Return the open status. If it does not exist, create it.
    """
    return get_or_create_project_status("Open")


@cache.memoize_function(120)
def get_closed_status():
    """
    Return the closed status. If it does not exist, create it.
    """
    return get_or_create_project_status("Closed")


def clear_project_status_cache():
    """
    Drop the memoized project status list and the open and closed lookups.
    """
    cache.cache.delete_memoized(get_project_statuses)
    cache.cache.delete_memoized(get_open_status)
    cache.cache.delete_memoized(get_closed_status)


def get_or_create_project_status(name):
    """
    Return the given status. If it does not exist, create it.
    """
    project_status = ProjectStatus.get_by(name=name)
    if project_status is None:
        project_status = ProjectStatus(name=name, color="#000000")
        project_status.save()
        clear_project_status_cache()
    return project_status.serialize()


def save_project_status(project_statuses):
    """
    Save in the database all the project statuses given as parameter.
    """
    result = []
    filtered_satuses = (x for x in project_statuses if x is not None)

    for status in filtered_satuses:
        project_status = get_or_create_project_status(status)
        result.append(project_status)
    return result


def get_project_raw(project_id):
    """
    Return the project that has the given ID, as an active record. If the
    project is not found, raise an exception.
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
    Return the project that has the given ID, as a dict. If the project is
    not found, raise an exception.

    Normalize the ID before the memoization, because the memoization keys
    on the argument. If not, a UUID and its string are two entries, and
    clear_project_cache drops only one of them.
    """
    return _get_project_cached(str(project_id), relations)


@cache.memoize_function(120)
def get_project_by_name(project_name):
    """
    Return the project that has the given name. If the project is not
    found, raise an exception.
    """
    project = Project.query.filter(Project.name.ilike(project_name)).first()

    if project is None:
        raise ProjectNotFoundException()

    return get_project_with_extra_data(project)


def update_project(project_id, data):
    """
    Update the project that has the given ID with the data of the *data*
    dict. Drop its cache and emit a project:update event.
    """
    project = get_project_raw(project_id)
    project.update(data)
    clear_project_cache(project_id)
    events.emit("project:update", {}, project_id=project_id)
    return project.serialize()


def _check_project_role(role):
    """
    Refuse a role that a project link cannot have. The admin role is
    global by design. All other values are typos: the column is an enum,
    so a write of such a value raises a KeyError deep in the driver, and
    the caller gets no clear answer.
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
    Add a person of the database to the project team, with an optional
    project-specific role. The function validates the role before it
    creates the membership. Because of this, an invalid role does not leave a
    partial state.
    """
    _check_project_role(role)
    person = Person.get(person_id)
    if (
        person is not None
        and person.preview_project_id is not None
        and str(person.preview_project_id) != str(project_id)
    ):
        raise WrongParameterException(
            "A preview account can only belong to its own project"
        )
    project = _add_to_list_attr(project_id, Person, person_id, "team")
    if role is not None:
        update_team_member_role(project_id, person_id, role)
        project = get_project_raw(project_id).serialize()
    return project


def remove_team_member(project_id, person_id):
    """
    Remove a person of the database from the project team.
    """
    return _remove_from_list_attr(project_id, Person, person_id, "team")


def update_team_member_role(project_id, person_id, role):
    """
    Set the role of the given person on the given project. If the role is
    None, the person inherits their global role again.
    """
    _check_project_role(role)
    person = Person.get(person_id)
    # A preview account must show exactly what a client sees.
    if person is not None and person.preview_project_id is not None:
        raise WrongParameterException(
            "A preview account keeps its client role"
        )
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
    Return the team members of the given project as active records, with
    their departments loaded eagerly. If not, the serialization of each
    member loads its departments with one more query.
    """
    project = get_project_raw(project_id)
    return (
        Person.query.options(selectinload(Person.departments))
        .join(ProjectPersonLink, ProjectPersonLink.person_id == Person.id)
        .filter(ProjectPersonLink.project_id == project.id)
        .all()
    )


@cache.memoize_function(240)
def get_team_person_ids(project_id):
    """
    Return the IDs of the persons in the team of the given project. If the
    project is not found, raise an exception. The result is memoized,
    because each project access check reads it. Always give the project ID
    as a string, because the cache keys on it.

    The IDs come only from the link table. A load of the project row also
    loads the full person row of each member, and no access check needs
    these rows.
    """
    try:
        person_ids = [
            str(person_id)
            for (person_id,) in ProjectPersonLink.query.with_entities(
                ProjectPersonLink.person_id
            ).filter_by(project_id=project_id)
        ]
    except StatementError:
        raise ProjectNotFoundException()
    if not person_ids:
        # A project that does not exist also has no team.
        get_project_raw(project_id)
    return person_ids


@cache.memoize_function(120)
def get_team_roles(project_id):
    """
    Return a dict that maps person IDs to their explicit role on the given
    project. The dict does not contain the persons that inherit their
    global role. The result is memoized, because each project access check
    of a non-admin reads it. Always give the project ID as a string,
    because the cache keys on it.
    """
    return {
        str(link.person_id): getattr(link.role, "code", link.role)
        for link in ProjectPersonLink.query.filter_by(
            project_id=project_id
        ).filter(ProjectPersonLink.role.isnot(None))
    }


def add_asset_type_setting(project_id, asset_type_id):
    """
    Add an asset type of the database to the asset types of the project.
    """
    return _add_to_list_attr(
        project_id, EntityType, asset_type_id, "asset_types"
    )


def remove_asset_type_setting(project_id, asset_type_id):
    """
    Remove an asset type of the database from the asset types of the
    project, with its project workflow.
    """
    _check_setting_id(asset_type_id)
    ProjectAssetTypeTaskTypeLink.query.filter_by(
        project_id=project_id, asset_type_id=asset_type_id
    ).delete()
    return _remove_from_list_attr(
        project_id, EntityType, asset_type_id, "asset_types"
    )


def get_asset_type_workflow(project_id, asset_type_id):
    """
    Return the IDs of the task types of an asset type workflow. This is the
    workflow of the project if it is set, or else the studio workflow. An
    empty list means that all the asset task types are accepted.
    """
    links = ProjectAssetTypeTaskTypeLink.query.filter_by(
        project_id=project_id, asset_type_id=asset_type_id
    ).all()
    if not links:
        links = TaskTypeAssetTypeLink.query.filter_by(
            asset_type_id=asset_type_id
        ).all()
    return [str(link.task_type_id) for link in links]


def filter_assets_in_workflow(project_id, task_type_id, assets):
    """
    Return the given assets whose asset type workflow accepts the task type.
    """
    workflows = {}
    result = []
    for asset in assets:
        asset_type_id = asset["entity_type_id"]
        if asset_type_id not in workflows:
            workflows[asset_type_id] = get_asset_type_workflow(
                project_id, asset_type_id
            )
        workflow = workflows[asset_type_id]
        if not workflow or str(task_type_id) in workflow:
            result.append(asset)
    return result


def set_asset_type_workflow(project_id, asset_type_id, task_type_ids):
    """
    Replace the workflow of an asset type for the given project. An empty
    list removes it, and then the asset type uses the studio workflow
    again.
    """
    project = get_project_raw(project_id)
    if asset_type_id not in {str(at.id) for at in project.asset_types}:
        raise WrongParameterException(
            f"Asset type {asset_type_id} is not in project {project_id}."
        )
    asset_task_type_ids = {
        str(task_type.id)
        for task_type in project.task_types
        if task_type.for_entity == "Asset"
    }
    wanted_ids = set(task_type_ids)
    invalid_ids = wanted_ids - asset_task_type_ids
    if invalid_ids:
        raise WrongParameterException(
            f"Not asset task types of project {project_id}: "
            f"{', '.join(sorted(invalid_ids))}."
        )
    ProjectAssetTypeTaskTypeLink.query.filter_by(
        project_id=project_id, asset_type_id=asset_type_id
    ).delete()
    db.session.add_all(
        ProjectAssetTypeTaskTypeLink(
            project_id=project_id,
            asset_type_id=asset_type_id,
            task_type_id=task_type_id,
        )
        for task_type_id in wanted_ids
    )
    return _save_project(project)


def add_task_type_setting(
    project_id,
    task_type_id,
    priority=None,
    bitrates=None,
    is_client_visible=None,
):
    """
    Add a task type of the database to the task types of the project. An
    existing link keeps its priority. If the bitrates and the client
    visibility are given, the link gets them.
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
    visibility = (
        {}
        if is_client_visible is None
        else {"is_client_visible": is_client_visible}
    )
    if not link:
        ProjectTaskTypeLink.create(
            task_type_id=task_type_id,
            project_id=project_id,
            priority=priority,
            **(bitrates or {}),
            **visibility,
        )
    elif bitrates is not None or visibility:
        link.update({**(bitrates or {}), **visibility})
    return _save_project(project)


def remove_task_type_setting(project_id, task_type_id):
    """
    Remove a task type of the database from the task types of the project
    and from the project workflows. If a workflow becomes empty, remove it:
    its asset type then uses the studio workflow again.
    """
    _check_setting_id(task_type_id)
    ProjectAssetTypeTaskTypeLink.query.filter_by(
        project_id=project_id, task_type_id=task_type_id
    ).delete()
    return _remove_from_list_attr(
        project_id, TaskType, task_type_id, "task_types"
    )


def add_task_status_setting(project_id, task_status_id):
    """
    Add a task status of the database to the task statuses of the project.
    """
    return _add_to_list_attr(
        project_id, TaskStatus, task_status_id, "task_statuses"
    )


def remove_task_status_setting(project_id, task_status_id):
    """
    Remove a task status of the database from the task statuses of the
    project.
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
    Add many task types (with their priority), task statuses and asset
    types to the project settings in one operation. Skip the unknown IDs.
    If replace_task_types is set, the given task type list is the full
    set: remove the existing links that are not in this list.
    """
    project = get_project_raw(project_id)
    project_id = str(project.id)

    wanted_task_types = {}
    for entry in task_types or []:
        wanted_task_types[str(entry["task_type_id"])] = entry

    existing_links = {
        str(link.task_type_id): link
        for link in ProjectTaskTypeLink.query.filter_by(project_id=project_id)
    }
    for task_type_id, entry in wanted_task_types.items():
        link = existing_links.get(task_type_id)
        priority = entry.get("priority")
        # If the visibility is not given, an existing link does not change.
        visibility = (
            {}
            if entry.get("is_client_visible") is None
            else {"is_client_visible": entry["is_client_visible"]}
        )
        if link is None:
            if TaskType.get(task_type_id) is not None:
                ProjectTaskTypeLink.create(
                    task_type_id=task_type_id,
                    project_id=project_id,
                    priority=priority,
                    **visibility,
                )
        else:
            changes = dict(visibility)
            if priority is not None and link.priority != priority:
                changes["priority"] = priority
            if changes:
                link.update(changes)
    if replace_task_types:
        for task_type_id, link in existing_links.items():
            if task_type_id not in wanted_task_types:
                task_type = TaskType.get(task_type_id)
                if task_type is not None:
                    project.task_types.remove(task_type)
                ProjectAssetTypeTaskTypeLink.query.filter_by(
                    project_id=project_id, task_type_id=task_type_id
                ).delete()

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
    Add a status automation of the database to the status automations of
    the project.
    """
    return _add_to_list_attr(
        project_id,
        StatusAutomation,
        status_automation_id,
        "status_automations",
    )


def remove_status_automation_setting(project_id, status_automation_id):
    """
    Remove a status automation of the database from the status automations
    of the project.
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
    Add a preview background file of the database to the backgrounds of the
    project.
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
    Remove a preview background file of the database from the backgrounds
    of the project.
    """
    return _remove_from_list_attr(
        project_id,
        PreviewBackgroundFile,
        preview_background_file_id,
        "preview_background_files",
    )


def _add_to_list_attr(project_id, model_class, model_id, list_attr):
    """
    Append a row to one of the project settings lists. If the row is
    already in the list, do nothing.
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
            # above is not atomic. Because of this, ignore the duplicate and
            # return the current project. Model.save() already did a rollback
            # of the failed transaction.
            return get_project_raw(project_id).serialize()
    else:
        return project.serialize()


def _check_setting_id(model_id):
    if not fields.is_valid_id(model_id):
        raise WrongParameterException(f"{model_id} is not a valid id.")


def _remove_from_list_attr(project_id, model_class, model_id, list_attr):
    """
    Remove a row from one of the project settings lists. If the row is not
    in the list, do nothing.
    """
    _check_setting_id(model_id)
    project = get_project_raw(project_id)
    model = model_class.get(model_id)
    try:
        getattr(project, list_attr).remove(model)
    except ValueError:
        pass
    return _save_project(project)


def _save_project(project):
    """
    Save the project, drop its cache and notify the clients.
    """
    project.save()
    clear_project_cache(str(project.id))
    events.emit("project:update", {}, project_id=str(project.id))
    return project.serialize()


def is_tv_show(project):
    """
    Return True if the given project is a TV show. Episodes apply only to
    TV shows.
    """
    return project["production_type"] == "tvshow"


def is_open(project):
    """
    Return True if the given project is still open.
    """
    open_status = get_open_status()
    return project["project_status_id"] == open_status["id"]


def has_tasks_or_entities(project_id):
    """
    Return True if the given project owns at least one task or one entity.
    """
    return (
        Task.query.filter_by(project_id=project_id).first() is not None
        or Entity.query.filter_by(project_id=project_id).first() is not None
    )


def _notify_project_settings_change(project_id):
    """
    Drop the project cache and notify the clients after a change on one of
    its task type or task status links. These tables are not the project.
    But the clients read them through the project, so the clients must get
    the project again.
    """
    project_id = str(project_id)
    clear_project_cache(project_id)
    events.emit("project:update", {}, project_id=project_id)


def create_project_task_type_link(project_id, task_type_id, priority):
    """
    Link a task type to the given project with a priority. If the link
    already exists, update the priority.
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
    Link a task status to the given project. If the link already exists,
    update the priority and the board roles.
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


def set_task_status_client_allowed(project_id, task_status_id, value):
    """
    For the given project, override the permission of the clients to set
    the given task status. None sets the studio value again. The status
    must be linked to the project.
    """
    if not task_status_id or not fields.is_valid_id(str(task_status_id)):
        raise TaskStatusNotFoundException()
    link = ProjectTaskStatusLink.get_by(
        project_id=project_id, task_status_id=task_status_id
    )
    if link is None:
        raise TaskStatusNotFoundException()
    link.update({"is_client_allowed": value})
    _notify_project_settings_change(project_id)
    return link.serialize()


def get_client_allowed_overrides(project_id):
    """
    Return the task status IDs of the given project whose client permission
    is overridden, mapped to the override.
    """
    links = ProjectTaskStatusLink.query.filter(
        ProjectTaskStatusLink.project_id == project_id,
        ProjectTaskStatusLink.is_client_allowed.isnot(None),
    ).all()
    return {str(link.task_status_id): link.is_client_allowed for link in links}


def is_task_status_client_allowed(project_id, task_status):
    """
    Return True if the clients of the given project can set the given task
    status. Use the project override if it exists. If not, use the studio
    value.
    """
    link = ProjectTaskStatusLink.get_by(
        project_id=project_id, task_status_id=task_status["id"]
    )
    if link is None or link.is_client_allowed is None:
        return bool(task_status.get("is_client_allowed"))
    return link.is_client_allowed


def set_project_task_type_link_priorities(project_id, task_type_ids):
    """
    Set the priority of the task type links of the project from the given
    ordered list of IDs (priority = position, from 1). The function changes
    only existing links, so a reorder never creates links. Return the
    updated links.
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
    Set the priority of the task status links of the project from the given
    ordered list of IDs (priority = position, from 1). The function changes
    only the priority, so the board roles of each link stay the same.
    Return the updated links.
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
    Return the task types configured on the given project as active
    records. If for_entity is given, return only the task types of this
    entity kind. for_entity became a nullable column in 2018 and only
    the shots got a backfill. Because of this, an older task type has NULL,
    which means "Asset", the model default.
    """
    query = TaskType.query.join(ProjectTaskTypeLink).filter(
        ProjectTaskTypeLink.project_id == project_id
    )
    if for_entity is not None:
        query = _filter_task_types_for_entity(query, for_entity)
    return query.all()


def _filter_task_types_for_entity(query, for_entity):
    """
    Limit a task type query to the given entity kind. A NULL for_entity
    means "Asset" (see get_project_task_types_raw).
    """
    if for_entity == "Asset":
        return query.filter(
            or_(TaskType.for_entity == "Asset", TaskType.for_entity.is_(None))
        )
    return query.filter(TaskType.for_entity == for_entity)


def get_project_task_types(project_id):
    """
    Return the task types configured on the given project.
    """
    project = get_project_raw(project_id)
    return Project.serialize_list(project.task_types)


def get_project_task_statuses(project_id):
    """
    Return the task statuses configured on the given project.
    """
    project = get_project_raw(project_id)
    return Project.serialize_list(project.task_statuses)


def get_project_status_automations(project_id):
    """
    Return the status automations configured on the given project, in the
    order of their creation. The automations that a status change starts
    apply in this order.
    """
    project = get_project_raw(project_id)
    return Project.serialize_list(project.status_automations)


def get_project_preview_background_files(project_id):
    """
    Return the preview background files configured on the given project.
    """
    project = get_project_raw(project_id)
    return Project.serialize_list(project.preview_background_files)


def get_project_fps(project_id):
    """
    Return the fps set on the project. If it is not set, return the
    default fps.
    """
    project = get_project(project_id)
    return float(project["fps"] or "25.00")


def get_task_type_priority_map(project_id, for_entity="Asset"):
    """
    Return a dict that maps a task type ID to a priority.
    """
    query = ProjectTaskTypeLink.query.join(TaskType).filter(
        ProjectTaskTypeLink.project_id == project_id
    )
    task_types = _filter_task_types_for_entity(query, for_entity).all()
    return {
        str(task_type_link.task_type_id): task_type_link.priority
        for task_type_link in task_types
    }


def get_task_type_links(project_id, for_entity="Asset"):
    """
    Return a list of links for the given project and entity type.
    """
    query = ProjectTaskTypeLink.query.join(TaskType).filter(
        ProjectTaskTypeLink.project_id == project_id
    )
    task_type_links = (
        _filter_task_types_for_entity(query, for_entity)
        .order_by(ProjectTaskTypeLink.priority.desc())
        .all()
    )
    return ProjectTaskTypeLink.serialize_list(task_type_links)


def get_department_team(project_id, department_id):
    """
    Return all the persons of the given department in the given project,
    as active records.
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
    Return the query filter that keeps only the open projects.
    """
    open_status = get_open_status()
    return Project.project_status_id == open_status["id"]


def narrow_metadata_descriptors(
    query, for_client=False, vendor_departments=None
):
    """
    Limit the given metadata descriptors query to the descriptors that a
    client or a vendor can read.
    """
    narrowing = build_descriptor_narrowing(for_client, vendor_departments)
    if narrowing is None:
        return query
    return query.filter(narrowing)


def _fetch_metadata_descriptors_by_project(
    project_ids, for_client=False, vendor_departments=None
):
    """
    Return the metadata descriptors of the given projects, grouped by
    project, with one query. Clients get only the descriptors published to
    them. A vendor gets only the descriptors of their departments.
    """
    descriptors_query = narrow_metadata_descriptors(
        MetadataDescriptor.query.filter(
            MetadataDescriptor.project_id.in_(project_ids)
        ),
        for_client,
        vendor_departments,
    )
    # Load the departments eagerly to prevent N+1 queries at the
    # serialization of the descriptors.
    descriptors_query = descriptors_query.options(
        joinedload(MetadataDescriptor.departments)
    )

    all_descriptors = descriptors_query.all()
    descriptors_by_project = defaultdict(list)
    for desc in all_descriptors:
        descriptors_by_project[desc.project_id].append(desc)
    return descriptors_by_project


def build_descriptor_narrowing(for_client=False, vendor_departments=None):
    """
    Return the criterion that keeps the metadata descriptors that a client
    or a vendor can read. If nothing is limited, return None. A client gets
    only the descriptors published to clients. A vendor gets only the
    descriptors of their departments or of no department. All the routes
    that serve descriptors use this function, so that they all apply the
    same rule.
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
    Return True if the dimension has the 1920x1080 pattern.
    """
    return resolution is not None and bool(
        re.match(r"^\d{3,4}x\d{3,4}$", resolution)
    )


def is_valid_partial_resolution(resolution):
    """
    Return True if the dimension has the x1080 pattern.
    """
    return resolution is not None and bool(re.match(r"^x\d{3,4}$", resolution))


def validate_resolution(resolution):
    """
    If the resolution is set but does not match the canonical "WIDTHxHEIGHT"
    or "xHEIGHT" format, raise WrongParameterException. Empty values (None
    or "") are accepted: the runtime then uses 1080p.

    The CRUD boundary uses this function. Because of this, users get a 400
    error immediately, not a silent default value at normalization time.
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
    If a movie bitrate is set but is not an integer number of Mbit/s
    between 1 and the high definition bitrate of the instance, raise
    WrongParameterException.
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
    Check the hd_bitrate_compression and ld_bitrate_compression that a
    settings change sets:

    - each value must be in the limits.
    - a low definition bitrate must never be more than the high definition
      bitrate of the movies.

    Find the high definition bitrate as the encoder does, in this order:

    - data.
    - current (the object that changes), for a bitrate that is not in data.
    - inherited (the level that the object uses if its value is not set).
    - the config.

    Do not check the bitrates that the change does not change, sent again
    or not. The encoder limits them, as it limits an unset low definition
    bitrate.
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
    Return the (highdef, lowdef) bitrates in Mbit/s for the encoding of the
    movies of a task. Use the value of the task type link, then the value
    of the project, then the value of the config. Each value is found
    separately.
    """
    bitrates = []
    for key, default in (
        ("hd_bitrate_compression", config.MOVIE_HIGHDEF_BITRATE),
        ("ld_bitrate_compression", config.MOVIE_LOWDEF_BITRATE),
    ):
        value = (task_type_link or {}).get(key) or project.get(key)
        bitrates.append(value or default)
    # The writes check only the bitrates that they change. A stored or
    # inherited bitrate can be more than a ceiling that was decreased
    # after. A low definition bitrate can be more than its high definition
    # bitrate. The encoder never goes above the ceilings.
    highdef = min(bitrates[0], config.MOVIE_HIGHDEF_BITRATE)
    lowdef = min(bitrates[1], highdef)
    return highdef, lowdef


def _check_task_type_software_ids(task_type_id, software_id):
    if not fields.is_valid_id(task_type_id) or not fields.is_valid_id(
        software_id
    ):
        raise WrongParameterException(
            "task_type_id and software_id must be valid UUIDs."
        )


def _serialize_task_type_software_link(link):
    return {
        "project_id": str(link.project_id),
        "task_type_id": str(link.task_type_id),
        "software_id": str(link.software_id),
    }


def get_task_type_software_links(project_id):
    """
    Return the softwares set for each task type of the given project, as
    dicts with project_id, task_type_id and software_id.
    """
    links = ProjectTaskTypeSoftwareLink.query.filter_by(
        project_id=project_id
    ).order_by(
        ProjectTaskTypeSoftwareLink.task_type_id,
        ProjectTaskTypeSoftwareLink.software_id,
    )
    return [_serialize_task_type_software_link(link) for link in links]


def add_task_type_software(project_id, task_type_id, software_id):
    """
    Link the given software to the given task type of the given project.
    The task type must be one of the project. The software must not be
    archived. If the link exists, return it as it is.
    """
    _check_task_type_software_ids(task_type_id, software_id)
    project = get_project_raw(project_id)
    project_id = str(project.id)
    if not ProjectTaskTypeLink.get_by(
        project_id=project_id, task_type_id=task_type_id
    ):
        raise WrongParameterException(
            "The task type is not a task type of the project."
        )
    software = get_instance(Software, software_id, SoftwareNotFoundException)
    if software.archived:
        raise WrongParameterException("The software is archived.")
    link = ProjectTaskTypeSoftwareLink.get_by(
        project_id=project_id,
        task_type_id=task_type_id,
        software_id=software_id,
    )
    if link is None:
        link = ProjectTaskTypeSoftwareLink.create(
            project_id=project_id,
            task_type_id=task_type_id,
            software_id=software_id,
        )
        events.emit("project:update", {}, project_id=project_id)
    return _serialize_task_type_software_link(link)


def remove_task_type_software(project_id, task_type_id, software_id):
    """
    Unlink the given software from the given task type of the given
    project. Return the deleted link. If the link does not exist, return
    None.
    """
    _check_task_type_software_ids(task_type_id, software_id)
    project = get_project_raw(project_id)
    project_id = str(project.id)
    link = ProjectTaskTypeSoftwareLink.get_by(
        project_id=project_id,
        task_type_id=task_type_id,
        software_id=software_id,
    )
    if link is None:
        return None
    removed = _serialize_task_type_software_link(link)
    link.delete()
    events.emit("project:update", {}, project_id=project_id)
    return removed
