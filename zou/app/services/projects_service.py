import slugify

from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.person import Person, DepartmentLink
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
    assets_service,
    base_service,
    edits_service,
    shots_service,
)
from zou.app.services.exception import (
    ProjectNotFoundException,
    MetadataDescriptorNotFoundException,
    DepartmentNotFoundException,
    WrongParameterException,
)

from zou.app.utils import fields, events, cache

from sqlalchemy.exc import StatementError
from sqlalchemy.orm.exc import ObjectDeletedError
from sqlalchemy import or_


def clear_project_cache(project_id):
    cache.cache.delete_memoized(get_project, project_id)
    cache.cache.delete_memoized(get_project_with_relations, project_id)
    cache.cache.delete_memoized(get_project_by_name)
    cache.cache.delete_memoized(open_projects)


@cache.memoize_function(120)
def open_projects(name=None):
    """
    Return all open projects. Allow to filter projects by name.
    """
    query = (
        Project.query.join(ProjectStatus)
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
    """
    projects = []
    for project in query.all():
        project_dict = project.serialize(relations=True)
        if for_client:
            descriptors = MetadataDescriptor.get_all_by(
                project_id=project.id, for_client=True
            )
        elif vendor_departments is not None:
            descriptors = MetadataDescriptor.query.filter(
                or_(
                    MetadataDescriptor.departments == None,
                    MetadataDescriptor.departments.any(
                        Department.id.in_(vendor_departments)
                    ),
                )
            )
        else:
            descriptors = MetadataDescriptor.get_all_by(project_id=project.id)
        project_dict["descriptors"] = []
        for descriptor in descriptors:
            project_dict["descriptors"].append(
                {
                    "id": fields.serialize_value(descriptor.id),
                    "name": descriptor.name,
                    "field_name": descriptor.field_name,
                    "data_type": fields.serialize_value(descriptor.data_type),
                    "choices": descriptor.choices,
                    "for_client": descriptor.for_client or False,
                    "entity_type": descriptor.entity_type,
                    "departments": [
                        str(department.id)
                        for department in descriptor.departments
                    ],
                }
            )

        project_dict["task_types_priority"] = {
            str(task_type_link.task_type_id): task_type_link.priority
            for task_type_link in ProjectTaskTypeLink.query.filter_by(
                project_id=project.id
            )
        }

        project_dict["task_statuses_link"] = {
            str(task_status_link.task_status_id): {
                "priority": task_status_link.priority,
                "roles_for_board": fields.serialize_list(
                    task_status_link.roles_for_board
                ),
            }
            for task_status_link in ProjectTaskStatusLink.query.filter_by(
                project_id=project.id
            )
        }

        if project.production_type == "tvshow":
            first_episode = (
                Entity.query.join(EntityType)
                .filter(EntityType.name == "Episode")
                .filter(Entity.project_id == project.id)
                .filter(Entity.status == "running")
                .order_by(Entity.name)
                .first()
            )
            if first_episode is None:
                first_episode = (
                    Entity.query.join(EntityType)
                    .filter(EntityType.name == "Episode")
                    .filter(Entity.project_id == project.id)
                    .order_by(Entity.name)
                    .first()
                )

            if first_episode is not None:
                project_dict["first_episode_id"] = fields.serialize_value(
                    first_episode.id
                )

        projects.append(project_dict)
    return projects


def get_projects():
    """
    Return all projects. Allow to filter projects by name.
    """
    query = (
        Project.query.join(ProjectStatus)
        .add_columns(ProjectStatus.name)
        .order_by(Project.name)
    )

    result = []
    for entry in query.all():
        (project, project_status_name) = entry
        data = project.serialize()
        data["project_status_name"] = project_status_name
        result.append(data)

    return result


@cache.memoize_function(480)
def get_project_statuses():
    return fields.serialize_models(ProjectStatus.get_all())


def get_or_create_open_status():
    """
    Return open status. If it does not exist, it creates it.
    """
    return get_or_create_status("Open")


@cache.memoize_function(480)
def get_open_status():
    """
    Return open status. If it does not exist, it creates it.
    """
    return get_or_create_status("Open")


@cache.memoize_function(120)
def get_closed_status():
    """
    Return closed status. If it does not exist, it creates it.
    """
    return get_or_create_status("Closed")


def get_or_create_status(name):
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
        project_status = get_or_create_status(status)
        result.append(project_status)
    return result


def get_or_create_project(name):
    """
    Get project which match given name. Create it if it does not exist.
    """
    project = Project.get_by(name=name)
    if project is None:
        open_status = get_or_create_open_status()
        project = Project(name=name, project_status_id=open_status["id"])
        project.save()
    return project.serialize()


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
def get_project(project_id):
    """
    Get project matching given id, as a dict. Raises an exception if project is
    not found.
    """
    return get_project_raw(project_id).serialize()


@cache.memoize_function(240)
def get_project_with_relations(project_id):
    """
    Get project matching given id, as a dict. Raises an exception if project is
    not found.
    """
    return get_project_raw(project_id).serialize(relations=True)


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


def add_team_member(project_id, person_id):
    """
    Add a person listed in database to the the project team.
    """
    return _add_to_list_attr(project_id, Person, person_id, "team")


def remove_team_member(project_id, person_id):
    """
    Remove a person listed in database from the the project team.
    """
    return _remove_from_list_attr(project_id, Person, person_id, "team")


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


def add_task_type_setting(project_id, task_type_id, priority=None):
    """
    Add a task type listed in database to the the project task types.
    """
    link = ProjectTaskTypeLink.get_by(
        task_type_id=task_type_id, project_id=project_id
    )
    if not link:
        ProjectTaskTypeLink.create(
            task_type_id=task_type_id, project_id=project_id, priority=priority
        )
    return _save_project(get_project_raw(project_id))


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
    project = get_project_raw(project_id)
    model = model_class.get(model_id)
    if str(model.id) not in [str(m.id) for m in getattr(project, list_attr)]:
        getattr(project, list_attr).append(model)
        return _save_project(project)
    else:
        return project.serialize()


def _remove_from_list_attr(project_id, model_class, model_id, list_attr):
    project = get_project_raw(project_id)
    model = model_class.get(model_id)
    try:
        getattr(project, list_attr).remove(model)
    except ValueError:
        pass
    return _save_project(project)


def _save_project(project):
    project.save()
    clear_project_cache(str(project.id))
    events.emit("project:update", {}, project_id=str(project.id))
    return project.serialize()


def add_metadata_descriptor(
    project_id,
    entity_type,
    name,
    data_type,
    choices,
    for_client,
    departments=[],
):
    if not departments:
        departments = []

    try:
        departments_objects = [
            Department.get(department_id)
            for department_id in departments
            if department_id is not None
        ]
    except StatementError:
        raise DepartmentNotFoundException()

    try:
        descriptor = MetadataDescriptor.create(
            project_id=project_id,
            entity_type=entity_type,
            name=name,
            data_type=data_type,
            choices=choices,
            for_client=for_client,
            departments=departments_objects,
            field_name=slugify.slugify(name, separator="_"),
        )
    except Exception:
        raise WrongParameterException
    events.emit(
        "metadata-descriptor:new",
        {"metadata_descriptor_id": str(descriptor.id)},
        project_id=project_id,
    )
    clear_project_cache(project_id)
    return descriptor.serialize()


def get_metadata_descriptors(project_id, for_client=False):
    """
    Get all metadata descriptors for given project and entity type.
    """
    query = MetadataDescriptor.query.filter(
        MetadataDescriptor.project_id == project_id
    ).order_by(MetadataDescriptor.name)
    if for_client:
        query = query.filter(MetadataDescriptor.for_client == True)

    descriptors = query.all()
    return fields.serialize_models(descriptors, relations=True)


def get_metadata_descriptor_raw(metadata_descriptor_id):
    """
    Get metadata descriptor for given id as active record.
    """
    return base_service.get_instance(
        MetadataDescriptor,
        metadata_descriptor_id,
        MetadataDescriptorNotFoundException,
    )


def get_metadata_descriptor(metadata_descriptor_id):
    """
    Get metadata descriptor for given id as dict.
    """
    return get_metadata_descriptor_raw(metadata_descriptor_id).serialize(
        relations=True
    )


def update_metadata_descriptor(metadata_descriptor_id, changes):
    """
    Update metadata descriptor information for given id.
    """
    descriptor = get_metadata_descriptor_raw(metadata_descriptor_id)

    if "name" in changes and len(changes["name"]) > 0:
        changes["field_name"] = slugify.slugify(changes["name"], separator="_")
        if descriptor.field_name != changes["field_name"]:
            query = Entity.query.filter(
                Entity.project_id == descriptor.project_id
            )
            if descriptor.entity_type == "Shot":
                shot_type = shots_service.get_shot_type()
                query = query.filter(Entity.entity_type_id == shot_type["id"])
            elif descriptor.entity_type == "Asset":
                query = query.filter(assets_service.build_asset_type_filter())
            elif descriptor.entity_type == "Edit":
                edit_type = edits_service.get_edit_type()
                query = query.filter(Entity.entity_type_id == edit_type["id"])

            entities = query.all()
            for entity in entities:
                metadata = fields.serialize_value(entity.data) or {}
                value = metadata.pop(descriptor.field_name, None)
                if value is not None:
                    metadata[changes["field_name"]] = value
                    entity.update_no_commit({"data": metadata})
            Entity.commit()

    if "departments" in changes:
        if not changes["departments"]:
            changes["departments"] = []

        try:
            departments_objects = [
                Department.get(department_id)
                for department_id in changes["departments"]
                if department_id is not None
            ]
        except StatementError:
            raise DepartmentNotFoundException()

        changes["departments"] = departments_objects

    descriptor.update(changes)
    events.emit(
        "metadata-descriptor:update",
        {"metadata_descriptor_id": str(descriptor.id)},
        project_id=descriptor.project_id,
    )
    clear_project_cache(str(descriptor.project_id))
    return descriptor.serialize()


def remove_metadata_descriptor(metadata_descriptor_id):
    """
    Delete metadata descriptor and related informations.
    """
    descriptor = get_metadata_descriptor_raw(metadata_descriptor_id)
    entities = Entity.get_all_by(project_id=descriptor.project_id)
    for entity in entities:
        metadata = fields.serialize_value(entity.data)
        if metadata is not None:
            metadata.pop(descriptor.field_name, None)
            entity.update({"data": metadata})
    try:
        descriptor.delete()
    except ObjectDeletedError:
        pass
    events.emit(
        "metadata-descriptor:delete",
        {"metadata_descriptor_id": str(descriptor.id)},
        project_id=descriptor.project_id,
    )
    clear_project_cache(str(descriptor.project_id))
    return descriptor.serialize()


def is_tv_show(project):
    return project["production_type"] == "tvshow"


def is_open(project):
    open_status = get_open_status()
    return project["project_status_id"] == open_status["id"]


def create_project_task_type_link(project_id, task_type_id, priority):
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

    return task_type_link.serialize()


def create_project_task_status_link(
    project_id, task_status_id, priority, roles_for_board=[]
):
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

    return task_status_link.serialize()


def get_project_task_types(project_id):
    project = get_project_raw(project_id)
    return Project.serialize_list(project.task_types)


def get_project_task_statuses(project_id):
    project = get_project_raw(project_id)
    return Project.serialize_list(project.task_statuses)


def get_project_status_automations(project_id):
    project = get_project_raw(project_id)
    return Project.serialize_list(project.status_automations)


def get_project_preview_background_files(project_id):
    project = get_project_raw(project_id)
    return Project.serialize_list(project.preview_background_files)


def get_project_fps(project_id):
    """
    Return fps set at project level or default fps if it not set.
    """
    project = get_project(project_id)
    return float(project["fps"] or "24.00")


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


def get_department_team(project_id, department_id):
    persons = (
        Person.query.join(
            ProjectPersonLink, ProjectPersonLink.person_id == Person.id
        )
        .join(DepartmentLink, DepartmentLink.person_id == Person.id)
        .filter(ProjectPersonLink.project_id == project_id)
        .filter(DepartmentLink.department_id == department_id)
    ).all()
    return persons
