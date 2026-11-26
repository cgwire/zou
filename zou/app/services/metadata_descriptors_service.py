import slugify
from sqlalchemy import and_, false, or_
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import ObjectDeletedError

from zou.app.exceptions import (
    DepartmentNotFoundException,
    MetadataDescriptorNotFoundException,
    WrongParameterException,
)
from zou.app.models.department import Department
from zou.app.models.entity import Entity
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task
from zou.app.services import (
    base_service,
    entity_types_service,
    projects_service,
)
from zou.app.utils import events, fields

# Keys that the built-in fields of an entity use in its data: the frame
# rate and the size of its previews, its maximum number of retakes, its
# frame range and its trim handles. A column with the same field name would
# share their values. Kitsu keeps the same list in src/lib/descriptors.js.
BUILT_IN_ENTITY_DATA_FIELDS = (
    "fps",
    "frame_in",
    "frame_out",
    "handle_in",
    "handle_out",
    "max_retakes",
    "resolution",
)


def _migrate_metadata_field_name(model, old_key, new_key):
    """
    Move a value from old_key to new_key in model.data, without a commit. If
    old_key is absent, do nothing. Return True if an update was applied.
    """
    metadata = fields.serialize_value(model.data) or {}
    value = metadata.pop(old_key, None)
    if value is None:
        return False
    metadata[new_key] = value
    model.update_no_commit({"data": metadata})
    return True


def _entity_query_for_descriptor_entity_type(descriptor):
    """
    Return the entities whose `data` holds a value for this descriptor (not
    Project and not Task). A field name is unique only for each entity type,
    thus the query keeps the entities of the descriptor type:
    - each asset type for Asset,
    - the type with that name for a shot, scene, sequence, episode or edit
      column,
    - no type for any other name.
    Leave out the rows without the key: a removal writes again only the rows
    that it changes.
    """
    query = Entity.query.filter(
        Entity.project_id == descriptor.project_id,
        Entity.data.has_key(descriptor.field_name),
    )
    if descriptor.entity_type == "Asset":
        return query.filter(entity_types_service.build_asset_type_filter())
    if descriptor.entity_type == "Shot":
        entity_type = entity_types_service.get_shot_type()
    elif descriptor.entity_type == "Scene":
        entity_type = entity_types_service.get_scene_type()
    elif descriptor.entity_type == "Sequence":
        entity_type = entity_types_service.get_sequence_type()
    elif descriptor.entity_type == "Episode":
        entity_type = entity_types_service.get_episode_type()
    elif descriptor.entity_type == "Edit":
        entity_type = entity_types_service.get_edit_type()
    else:
        return query.filter(false())
    return query.filter(Entity.entity_type_id == entity_type["id"])


def _task_query_for_descriptor(descriptor):
    """
    Return the tasks whose `data` holds a value for this Task descriptor.
    """
    return Task.query.filter(
        Task.project_id == descriptor.project_id,
        Task.task_type_id == descriptor.task_type_id,
        Task.data.has_key(descriptor.field_name),
    )


def _strip_metadata_field_from_model_data(model, field_name):
    """
    Remove field_name from model.data if `data` is not null.
    """
    metadata = fields.serialize_value(model.data)
    if metadata is not None:
        metadata.pop(field_name, None)
        model.update({"data": metadata})


def _migrate_descriptor_field_rename(descriptor, new_field_name):
    """
    Apply the rename of a metadata field to Project.data or to the matching
    Entity rows. Do not commit: the caller commits the moved values with the
    descriptor. Thus, if the update of the descriptor fails, the moved values
    roll back too.
    """
    if descriptor.entity_type == "Project":
        project = projects_service.get_project_raw(descriptor.project_id)
        _migrate_metadata_field_name(
            project, descriptor.field_name, new_field_name
        )
        return
    if descriptor.entity_type == "Task":
        for task in _task_query_for_descriptor(descriptor).all():
            _migrate_metadata_field_name(
                task, descriptor.field_name, new_field_name
            )
        return
    entities = _entity_query_for_descriptor_entity_type(descriptor).all()
    for entity in entities:
        _migrate_metadata_field_name(
            entity, descriptor.field_name, new_field_name
        )


def _remove_stored_values_for_metadata_descriptor(descriptor):
    """
    Remove the field values of the descriptor from:
    - Project.data, for the Project type,
    - the Task.data rows of its task type, for the Task type,
    - the Entity.data rows of its entity type, for the other types.
    """
    if descriptor.entity_type == "Project":
        project = projects_service.get_project_raw(descriptor.project_id)
        _strip_metadata_field_from_model_data(project, descriptor.field_name)
        return
    if descriptor.entity_type == "Task":
        for task in _task_query_for_descriptor(descriptor).all():
            _strip_metadata_field_from_model_data(task, descriptor.field_name)
        return
    for entity in _entity_query_for_descriptor_entity_type(descriptor).all():
        _strip_metadata_field_from_model_data(entity, descriptor.field_name)


def _find_descriptors_by_field(project_ids, entity_type, field_name):
    """
    Return the metadata descriptors that have the given field name and entity
    type in the given projects.
    """
    return MetadataDescriptor.query.filter(
        MetadataDescriptor.project_id.in_(project_ids),
        MetadataDescriptor.entity_type == entity_type,
        MetadataDescriptor.field_name == field_name,
    ).all()


def build_metadata_descriptors_filter(descriptor_visibilities):
    """
    Return a filter that keeps the metadata descriptors of the projects of
    the given (project_ids, for_client, vendor_departments) triples. Each
    triple narrows its projects: a query on many projects narrows each
    project for the role held on it.
    """
    criteria = []
    for project_ids, for_client, vendor_departments in descriptor_visibilities:
        criterion = MetadataDescriptor.project_id.in_(project_ids)
        narrowing = projects_service.build_descriptor_narrowing(
            for_client, vendor_departments
        )
        if narrowing is not None:
            criterion = and_(criterion, narrowing)
        criteria.append(criterion)
    if not criteria:
        return false()
    return or_(*criteria)


def check_metadata_descriptor_field_name(entity_type, field_name):
    """
    Refuse the key of a built-in field as the field name of a column whose
    values are in the entity data. Project and task columns store their values
    in the project data or the task data, where these keys have no meaning.
    """
    if (
        entity_type not in ("Project", "Task")
        and field_name in BUILT_IN_ENTITY_DATA_FIELDS
    ):
        raise WrongParameterException(
            "Metadata descriptor name is used by a built-in field."
        )


def _check_metadata_descriptor_rename(descriptor, name, field_name):
    """
    Refuse a new name in these conditions:
    - It is longer than the name column or the field name column holds.
    - Another descriptor of the same project, entity type and task type (the
      scope of the unique indexes) holds it as its name or its field name.
    The update of the descriptor would fail on it after the stored values
    moved to the new key, and overwrite any value already there. A new field
    name must also not be the key of a built-in field. A column created with
    such a key before this check keeps it.
    """
    columns = MetadataDescriptor.__table__.c
    if (
        len(name) > columns.name.type.length
        or len(field_name) > columns.field_name.type.length
    ):
        raise WrongParameterException("Metadata descriptor name is too long.")
    if field_name != descriptor.field_name:
        check_metadata_descriptor_field_name(
            descriptor.entity_type, field_name
        )
    query = MetadataDescriptor.query.filter(
        MetadataDescriptor.id != descriptor.id,
        MetadataDescriptor.project_id == descriptor.project_id,
        MetadataDescriptor.entity_type == descriptor.entity_type,
        or_(
            MetadataDescriptor.name == name,
            MetadataDescriptor.field_name == field_name,
        ),
    )
    if descriptor.task_type_id is not None:
        query = query.filter(
            MetadataDescriptor.task_type_id == descriptor.task_type_id
        )
    if query.first() is not None:
        raise WrongParameterException("Metadata descriptor already exists.")


def add_metadata_descriptor(
    project_id,
    entity_type,
    name,
    data_type,
    choices,
    for_client,
    departments=None,
    task_type_id=None,
):
    """
    Register a custom field for the given `entity_type` in this project. The
    values are stored in:
    - `Entity.data` (Asset, Shot, …),
    - `Project.data` if `entity_type` is ``Project``,
    - `Task.data` if it is ``Task`` (scoped to `task_type_id`).
    Raise WrongParameterException if the field name is the key of a built-in
    field or if the descriptor already exists.
    """
    if not departments:
        departments = []
    field_name = slugify.slugify(name, separator="_")
    check_metadata_descriptor_field_name(entity_type, field_name)

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
            task_type_id=task_type_id,
            name=name,
            data_type=data_type,
            choices=choices,
            for_client=for_client,
            departments=departments_objects,
            field_name=field_name,
        )
    except IntegrityError:
        raise WrongParameterException("Metadata descriptor already exists.")
    events.emit(
        "metadata-descriptor:new",
        {"metadata_descriptor_id": str(descriptor.id)},
        project_id=project_id,
    )
    projects_service.clear_project_cache(project_id)
    return descriptor.serialize(relations=True)


def get_metadata_descriptors(
    project_id, for_client=False, vendor_departments=None
):
    """
    Return all metadata descriptors for the given project. For a client or a
    vendor, narrow them as the open projects listing does.
    """
    query = MetadataDescriptor.query.filter(
        MetadataDescriptor.project_id == project_id
    ).order_by(MetadataDescriptor.position, MetadataDescriptor.name)
    query = projects_service.narrow_metadata_descriptors(
        query, for_client, vendor_departments
    )

    # Load the departments now to prevent N+1 queries in serialization
    query = query.options(joinedload(MetadataDescriptor.departments))
    descriptors = query.all()
    return fields.serialize_models(descriptors, relations=True)


def get_metadata_descriptor_raw(metadata_descriptor_id):
    """
    Return the metadata descriptor for the given ID as an active record.
    """
    return base_service.get_instance(
        MetadataDescriptor,
        metadata_descriptor_id,
        MetadataDescriptorNotFoundException,
    )


def get_metadata_descriptor(metadata_descriptor_id):
    """
    Return the metadata descriptor for the given ID as a dict.
    """
    return get_metadata_descriptor_raw(metadata_descriptor_id).serialize(
        relations=True
    )


def get_project_metadata_descriptor(project_id, metadata_descriptor_id):
    """
    Return the metadata descriptor for the given ID as a dict, if it belongs
    to the given project. The client sends the ID with a project that it can
    access: a descriptor of another project is not found.
    """
    descriptor = get_metadata_descriptor(metadata_descriptor_id)
    if descriptor["project_id"] != str(project_id):
        raise MetadataDescriptorNotFoundException()
    return descriptor


def is_metadata_descriptor_visible(
    metadata_descriptor_id, for_client=False, vendor_departments=None
):
    """
    Return True if the narrowing for a client or a vendor keeps the given
    metadata descriptor.
    """
    query = projects_service.narrow_metadata_descriptors(
        MetadataDescriptor.query.filter(
            MetadataDescriptor.id == metadata_descriptor_id
        ),
        for_client,
        vendor_departments,
    )
    return query.first() is not None


def update_metadata_descriptor(metadata_descriptor_id, changes):
    """
    Update the metadata descriptor for the given ID. All the checks that can
    refuse the changes run before a rename moves the stored values. The moved
    values are committed with the descriptor: if the update fails, they stay
    under their old key.
    """
    descriptor = get_metadata_descriptor_raw(metadata_descriptor_id)
    if not changes.get("name"):
        # If no new name is given, the column keeps its name.
        changes.pop("name", None)

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

    if "name" in changes:
        changes["field_name"] = slugify.slugify(changes["name"], separator="_")
        _check_metadata_descriptor_rename(
            descriptor, changes["name"], changes["field_name"]
        )
        if descriptor.field_name != changes["field_name"]:
            _migrate_descriptor_field_rename(descriptor, changes["field_name"])

    descriptor.update(changes)
    events.emit(
        "metadata-descriptor:update",
        {"metadata_descriptor_id": str(descriptor.id)},
        project_id=descriptor.project_id,
    )
    projects_service.clear_project_cache(str(descriptor.project_id))
    return descriptor.serialize(relations=True)


def reorder_metadata_descriptors(project_id, entity_type, descriptor_ids):
    """
    Reorder the metadata descriptors for the given project and entity type.
    Update the position field from the order of the given descriptor IDs. Add
    the descriptors that are not in the list at the end, ordered by name. If
    an ID is not a descriptor of this project and entity type, raise
    WrongParameterException. Return the descriptors in their new order.
    """
    descriptors = MetadataDescriptor.query.filter(
        MetadataDescriptor.project_id == project_id,
        MetadataDescriptor.entity_type == entity_type,
    ).all()

    descriptor_map = {str(desc.id): desc for desc in descriptors}

    for descriptor_id in descriptor_ids:
        if descriptor_id not in descriptor_map:
            raise WrongParameterException(
                f"Descriptor {descriptor_id} not found for project {project_id} and entity type {entity_type}"
            )

    for position, descriptor_id in enumerate(descriptor_ids, start=1):
        descriptor = descriptor_map[descriptor_id]
        descriptor.update({"position": position})

    descriptors_not_in_list = [
        desc for desc in descriptors if not str(desc.id) in descriptor_ids
    ]
    descriptors_not_in_list.sort(key=lambda d: d.name)
    start_position = len(descriptor_ids) + 1
    for position_offset, descriptor in enumerate(descriptors_not_in_list):
        descriptor.update({"position": start_position + position_offset})

    projects_service.clear_project_cache(project_id)

    query = MetadataDescriptor.query.filter(
        MetadataDescriptor.project_id == project_id,
        MetadataDescriptor.entity_type == entity_type,
    ).order_by(MetadataDescriptor.position, MetadataDescriptor.name)
    # Load the departments now to prevent N+1 queries in serialization
    query = query.options(joinedload(MetadataDescriptor.departments))
    return fields.serialize_models(query.all(), relations=True)


def remove_metadata_descriptor(metadata_descriptor_id):
    """
    Delete the metadata descriptor and remove its values from the project
    data, the task data or the entity data.
    """
    descriptor = get_metadata_descriptor_raw(metadata_descriptor_id)
    _remove_stored_values_for_metadata_descriptor(descriptor)
    try:
        descriptor.delete()
    except ObjectDeletedError:
        pass
    events.emit(
        "metadata-descriptor:delete",
        {"metadata_descriptor_id": str(descriptor.id)},
        project_id=descriptor.project_id,
    )
    projects_service.clear_project_cache(str(descriptor.project_id))
    return descriptor.serialize()


def add_metadata_descriptor_to_projects(
    project_ids,
    entity_type,
    name,
    data_type,
    choices,
    for_client,
    departments=None,
):
    """
    Create the same metadata descriptor in each given project that does not
    have one with the same field name and entity type. Return the list of
    created descriptors.
    """
    field_name = slugify.slugify(name, separator="_")
    created = []
    for project_id in project_ids:
        exists = (
            MetadataDescriptor.query.filter(
                MetadataDescriptor.project_id == project_id,
                MetadataDescriptor.entity_type == entity_type,
                MetadataDescriptor.field_name == field_name,
            ).count()
            > 0
        )
        if not exists:
            created.append(
                add_metadata_descriptor(
                    project_id,
                    entity_type,
                    name,
                    data_type,
                    choices,
                    for_client,
                    departments,
                )
            )
    return created


def copy_project_metadata_descriptors(project_id):
    """
    Copy the Project-scoped metadata descriptors (the all-projects columns)
    of the open projects to the given project. Thus its cells are editable
    immediately. Make one copy for each distinct field name. Do not change the
    field names that the project already has. Return the created descriptors.
    """
    descriptors = (
        MetadataDescriptor.query.join(
            Project, MetadataDescriptor.project_id == Project.id
        )
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(ProjectStatus.name.in_(("Active", "open", "Open")))
        .filter(MetadataDescriptor.entity_type == "Project")
        .filter(MetadataDescriptor.project_id != project_id)
        .order_by(MetadataDescriptor.position, MetadataDescriptor.name)
        .all()
    )
    owned_field_names = {
        descriptor.field_name
        for descriptor in MetadataDescriptor.query.filter(
            MetadataDescriptor.project_id == project_id,
            MetadataDescriptor.entity_type == "Project",
        )
    }
    created = []
    for descriptor in descriptors:
        if descriptor.field_name in owned_field_names:
            continue
        owned_field_names.add(descriptor.field_name)
        created.append(
            add_metadata_descriptor(
                project_id,
                "Project",
                descriptor.name,
                descriptor.data_type,
                descriptor.choices,
                descriptor.for_client,
                [str(department.id) for department in descriptor.departments],
            )
        )
    return created


def update_metadata_descriptor_on_projects(
    project_ids, entity_type, field_name, changes
):
    """
    Update each metadata descriptor that has the given field name and entity
    type in the given projects. Check a new name on each project first, thus
    a refusal leaves all of them unchanged. Return the list of updated
    descriptors.
    """
    descriptors = _find_descriptors_by_field(
        project_ids, entity_type, field_name
    )
    name = changes.get("name")
    if name:
        new_field_name = slugify.slugify(name, separator="_")
        for descriptor in descriptors:
            _check_metadata_descriptor_rename(descriptor, name, new_field_name)
    return [
        update_metadata_descriptor(str(descriptor.id), dict(changes))
        for descriptor in descriptors
    ]


def remove_metadata_descriptor_from_projects(
    project_ids, entity_type, field_name
):
    """
    Remove each metadata descriptor that has the given field name and entity
    type in the given projects. Return the list of removed IDs.
    """
    descriptors = _find_descriptors_by_field(
        project_ids, entity_type, field_name
    )
    removed_ids = []
    for descriptor in descriptors:
        descriptor_id = str(descriptor.id)
        remove_metadata_descriptor(descriptor_id)
        removed_ids.append(descriptor_id)
    return removed_ids


def reorder_metadata_descriptors_on_projects(
    project_ids, entity_type, field_order
):
    """
    Apply the same column order, given as a list of field names, to each
    given project. The descriptors whose field name is not in the list keep
    the last positions (reorder_metadata_descriptors does this). Return the
    list of updated descriptors of all projects.
    """
    updated = []
    for project_id in project_ids:
        descriptors = MetadataDescriptor.query.filter(
            MetadataDescriptor.project_id == project_id,
            MetadataDescriptor.entity_type == entity_type,
        ).all()
        by_field = {desc.field_name: str(desc.id) for desc in descriptors}
        ordered_ids = [
            by_field[field_name]
            for field_name in field_order
            if field_name in by_field
        ]
        if ordered_ids:
            updated.extend(
                reorder_metadata_descriptors(
                    project_id, entity_type, ordered_ids
                )
            )
    return updated


def get_not_allowed_descriptors_fields_for_vendor(
    entity_type="Asset", departments=None, projects_ids=None
):
    """
    Return, for each project, the metadata field names that a vendor of the
    given departments must not see: the descriptors restricted to departments
    that the vendor is not a member of.
    """
    if departments is None:
        departments = []
    if projects_ids is None:
        projects_ids = []
    not_allowed_descriptors_field_names = {}
    for project_id in projects_ids:
        not_allowed_descriptors_field_names[project_id] = [
            descriptor["field_name"]
            for descriptor in get_metadata_descriptors(project_id)
            if descriptor["entity_type"] == entity_type
            and descriptor["departments"] != []
            and len(set(departments) & set(descriptor["departments"])) == 0
        ]
    return not_allowed_descriptors_field_names


def remove_not_allowed_fields_from_metadata(
    not_allowed_descriptors_field_names=None, data=None
):
    """
    Return the given metadata without the fields that the caller must not
    see.
    """
    if not_allowed_descriptors_field_names is None:
        not_allowed_descriptors_field_names = []
    if data is None:
        data = {}
    return {
        key: value
        for key, value in data.items()
        if key not in not_allowed_descriptors_field_names
    }


def remove_not_allowed_metadata_for_vendor(
    entity_type, departments, entities, project_id=None
):
    """
    Remove from a serialized listing, in place, the metadata that a vendor of
    the given departments must not see. If departments is None, remove
    nothing.

    The listings that carry the tasks select their columns one by one and
    mask them while they build their rows. These listings return full
    serialized entities, thus the restricted descriptors stay in them unless
    this function removes them. Some of these listings remove the project
    from the entities, thus the caller gives a default project_id.
    """
    if departments is None:
        return entities
    not_allowed_map = get_not_allowed_descriptors_fields_for_vendor(
        entity_type,
        departments,
        set(entity.get("project_id") or project_id for entity in entities),
    )
    for entity in entities:
        entity["data"] = remove_not_allowed_fields_from_metadata(
            not_allowed_map[entity.get("project_id") or project_id],
            entity["data"],
        )
    return entities
