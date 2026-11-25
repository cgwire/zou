from collections import defaultdict

import slugify
from sqlalchemy.exc import IntegrityError, StatementError

from zou.app import db
from zou.app.exceptions import (
    ProjectTemplateNotFoundException,
    WrongParameterException,
)
from zou.app.models.entity_type import EntityType
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.project_template import (
    ProjectTemplate,
    ProjectTemplateAssetTypeLink,
    ProjectTemplateAssetTypeTaskTypeLink,
    ProjectTemplatePreviewBackgroundFileLink,
    ProjectTemplateStatusAutomationLink,
    ProjectTemplateTaskStatusLink,
    ProjectTemplateTaskTypeLink,
)
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.services import (
    metadata_descriptors_service,
    projects_service,
)
from zou.app.utils import events, fields

# The production setting fields that the code copies between Project and
# ProjectTemplate. These fields are not in the list on purpose:
# - name and description, which the code sets explicitly,
# - the team, date and production data fields,
# - the JSONB columns file_tree and data, which have their own code.
PRODUCTION_SETTING_FIELDS = [
    "fps",
    "ratio",
    "resolution",
    "production_type",
    "production_style",
    "max_retakes",
    "is_clients_isolated",
    "is_preview_download_allowed",
    "is_set_preview_automated",
    "is_publish_default_for_artists",
    "homepage",
    "hd_bitrate_compression",
    "ld_bitrate_compression",
    "is_client_stats_visible",
    "is_client_task_list_visible",
    "is_client_task_panel_visible",
]


def clear_project_template_cache():
    """
    Do nothing. This stub keeps the call sites stable. The template reads are
    not cached for now, because only admins use templates and templates change
    rarely. If the access patterns change, it is easy to add a memoize layer.
    """


def _notify_template_change(template_id, action="update"):
    """
    Remove the template cache and tell the clients that the template changed.
    """
    clear_project_template_cache()
    events.emit(
        f"project-template:{action}",
        {"project_template_id": str(template_id)},
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def get_project_template_raw(template_id):
    """
    Return the template that has the given ID, as an active record. If it does
    not exist, raise ProjectTemplateNotFoundException.
    """
    try:
        template = ProjectTemplate.get(template_id)
    except StatementError:
        raise ProjectTemplateNotFoundException()
    if template is None:
        raise ProjectTemplateNotFoundException()
    return template


def get_project_template(template_id):
    """
    Return the template that has the given ID, as a dict. If it does not exist,
    raise ProjectTemplateNotFoundException.
    """
    return get_project_template_raw(template_id).serialize()


def create_project_template(name, description=None, **settings):
    """
    Create a new empty template. If other keyword arguments are production
    settings, file_tree, data or metadata_descriptors, send them to the
    template. Ignore all other arguments. If the name is empty or already in
    use, raise WrongParameterException.
    """
    if not name:
        raise WrongParameterException("name is required")
    projects_service.validate_movie_bitrates(settings)
    data = {"name": name, "description": description}
    for key, value in settings.items():
        if key in PRODUCTION_SETTING_FIELDS or key in (
            "file_tree",
            "data",
            "metadata_descriptors",
        ):
            data[key] = value
    try:
        template = ProjectTemplate.create(**data)
    except IntegrityError:
        raise WrongParameterException(
            "A project template with this name already exists"
        )
    _notify_template_change(template.id, action="new")
    return template.serialize()


def update_project_template(template_id, changes):
    """
    Update the fields of the template.
    """
    template = get_project_template_raw(template_id)
    projects_service.validate_movie_bitrates(
        changes or {}, current=template.serialize()
    )
    # Remove the fields that the caller cannot change directly.
    safe_changes = {
        key: value
        for key, value in (changes or {}).items()
        if key
        not in (
            "id",
            "type",
            "created_at",
            "updated_at",
            "task_types",
            "task_statuses",
            "asset_types",
            "status_automations",
        )
    }
    try:
        template.update(safe_changes)
    except IntegrityError:
        raise WrongParameterException(
            "A project template with this name already exists"
        )
    _notify_template_change(template.id)
    return template.serialize()


def delete_project_template(template_id):
    """
    Delete a template and its rows in the link tables.
    """
    template = get_project_template_raw(template_id)
    template_dict = template.serialize()
    template.delete()
    _notify_template_change(template_dict["id"], action="delete")
    return template_dict


# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------


def _ensure_template_exists(template_id):
    """
    Return the template that has the given ID, as an active record. If it does
    not exist, raise ProjectTemplateNotFoundException.
    """
    return get_project_template_raw(template_id)


def _check_required_id(model, value, field_name, label):
    """
    Return the row that has the given ID. If the id is not a valid UUID of an
    existing row, raise WrongParameterException.
    """
    if not value or not fields.is_valid_id(value):
        raise WrongParameterException(
            f"{field_name} is required and must be a valid UUID"
        )
    instance = model.get(value)
    if instance is None:
        raise WrongParameterException(f"{label} {value} does not exist")
    return instance


def get_template_task_types(template_id):
    """
    Return the task types of the given template, sorted by priority, then by
    name. Each task type has the priority stored on its link.
    """
    template = _ensure_template_exists(template_id)
    links = ProjectTemplateTaskTypeLink.get_all_by(
        project_template_id=template_id
    )
    link_map = {str(link.task_type_id): link for link in links}
    result = []
    for task_type in template.task_types:
        data = task_type.serialize()
        link = link_map.get(str(task_type.id))
        if link:
            data["priority"] = link.priority
            data["hd_bitrate_compression"] = link.hd_bitrate_compression
            data["ld_bitrate_compression"] = link.ld_bitrate_compression
            data["is_client_visible"] = link.is_client_visible
        result.append(data)
    result.sort(key=lambda t: (t.get("priority") or 0, t.get("name", "")))
    return result


UNSET = object()


def add_task_type_to_template(
    template_id,
    task_type_id,
    priority=None,
    bitrates=None,
    is_client_visible=None,
):
    """
    Link a task type to the given template. If the link already exists, update
    its priority, its movie bitrates and its client visibility. The values left
    to None do not change, so a reorder keeps them.
    """
    _check_required_id(TaskType, task_type_id, "task_type_id", "Task type")
    template = _ensure_template_exists(template_id)
    if bitrates is not None:
        projects_service.validate_movie_bitrates(
            bitrates, inherited=template.serialize()
        )
    if priority is not None:
        priority = int(priority)
    visibility = (
        {}
        if is_client_visible is None
        else {"is_client_visible": is_client_visible}
    )
    link = ProjectTemplateTaskTypeLink.get_by(
        project_template_id=template_id, task_type_id=task_type_id
    )
    if link is None:
        link = ProjectTemplateTaskTypeLink.create(
            project_template_id=template_id,
            task_type_id=task_type_id,
            priority=priority,
            **(bitrates or {}),
            **visibility,
        )
    else:
        update_data = {**(bitrates or {}), **visibility}
        if priority is not None:
            update_data["priority"] = priority
        if update_data:
            link.update(update_data)
    _notify_template_change(template_id)
    return link.serialize()


def remove_task_type_from_template(template_id, task_type_id):
    """
    Unlink a task type from the given template and from its workflows. If the
    task type is not linked, do nothing.
    """
    link = ProjectTemplateTaskTypeLink.get_by(
        project_template_id=template_id, task_type_id=task_type_id
    )
    if link is not None:
        ProjectTemplateAssetTypeTaskTypeLink.query.filter_by(
            project_template_id=template_id, task_type_id=task_type_id
        ).delete()
        link.delete()
    _notify_template_change(template_id)


def get_template_task_statuses(template_id):
    """
    Return the task statuses of the given template, sorted by priority, then by
    name. Each task status has the priority and the board roles stored on its
    link.
    """
    template = _ensure_template_exists(template_id)
    links = ProjectTemplateTaskStatusLink.get_all_by(
        project_template_id=template_id
    )
    link_map = {str(link.task_status_id): link for link in links}
    result = []
    for task_status in template.task_statuses:
        data = task_status.serialize()
        link = link_map.get(str(task_status.id))
        if link:
            data["priority"] = link.priority
            data["roles_for_board"] = [
                role.code if hasattr(role, "code") else str(role)
                for role in (link.roles_for_board or [])
            ]
            data["link_is_client_allowed"] = link.is_client_allowed
        result.append(data)
    result.sort(key=lambda s: (s.get("priority") or 0, s.get("name", "")))
    return result


def add_task_status_to_template(
    template_id,
    task_status_id,
    priority=None,
    roles_for_board=None,
    is_client_allowed=UNSET,
):
    """
    Link a task status to the given template. If the link already exists,
    update the given fields. The fields left to None do not change. If
    is_client_allowed is UNSET, it does not change. If it is None, it goes back
    to the studio value.
    """
    _check_required_id(
        TaskStatus, task_status_id, "task_status_id", "Task status"
    )
    _ensure_template_exists(template_id)
    if priority is not None:
        priority = int(priority)
    link = ProjectTemplateTaskStatusLink.get_by(
        project_template_id=template_id, task_status_id=task_status_id
    )
    if link is None:
        link = ProjectTemplateTaskStatusLink.create(
            project_template_id=template_id,
            task_status_id=task_status_id,
            priority=priority,
            roles_for_board=roles_for_board,
            is_client_allowed=(
                None if is_client_allowed is UNSET else is_client_allowed
            ),
        )
    else:
        update_data = {}
        if priority is not None:
            update_data["priority"] = priority
        if roles_for_board is not None:
            update_data["roles_for_board"] = roles_for_board
        if is_client_allowed is not UNSET:
            update_data["is_client_allowed"] = is_client_allowed
        if update_data:
            link.update(update_data)
    _notify_template_change(template_id)
    return link.serialize()


def remove_task_status_from_template(template_id, task_status_id):
    """
    Unlink a task status from the given template. If the task status is not
    linked, do nothing.
    """
    link = ProjectTemplateTaskStatusLink.get_by(
        project_template_id=template_id, task_status_id=task_status_id
    )
    if link is not None:
        link.delete()
    _notify_template_change(template_id)


def set_template_task_type_priorities(template_id, task_type_ids):
    """
    Set the priority of the task type links of the template from the given
    sorted id list (priority = position, 1-based) in a single pass. Return the
    updated links.
    """
    return [
        add_task_type_to_template(template_id, task_type_id, priority)
        for priority, task_type_id in enumerate(task_type_ids, start=1)
    ]


def set_template_task_status_priorities(template_id, task_status_ids):
    """
    Set the priority of the task status links of the template from the given
    sorted id list (priority = position, 1-based). The board roles do not
    change, because the function gives only the priority. Return the updated
    links.
    """
    return [
        add_task_status_to_template(template_id, task_status_id, priority)
        for priority, task_status_id in enumerate(task_status_ids, start=1)
    ]


def get_template_asset_types(template_id):
    """
    Return the asset types of the given template: id, name and the workflow of
    the template. If the studio workflow applies, the workflow is empty.
    """
    template = _ensure_template_exists(template_id)
    workflows = defaultdict(list)
    for link in ProjectTemplateAssetTypeTaskTypeLink.query.filter_by(
        project_template_id=template.id
    ).all():
        workflows[link.asset_type_id].append(str(link.task_type_id))
    return [
        {
            "id": str(asset_type.id),
            "name": asset_type.name,
            "workflow": workflows.get(asset_type.id, []),
        }
        for asset_type in template.asset_types
    ]


def set_template_asset_type_workflow(
    template_id, asset_type_id, task_type_ids
):
    """
    Replace the workflow of an asset type for the given template. An empty list
    removes the workflow, so the asset type uses the studio workflow again.
    """
    template = _ensure_template_exists(template_id)
    if asset_type_id not in {str(at.id) for at in template.asset_types}:
        raise WrongParameterException(
            f"Asset type {asset_type_id} is not in template {template_id}."
        )
    asset_task_type_ids = {
        str(task_type.id)
        for task_type in template.task_types
        if task_type.for_entity == "Asset"
    }
    wanted_ids = set(task_type_ids)
    invalid_ids = wanted_ids - asset_task_type_ids
    if invalid_ids:
        raise WrongParameterException(
            f"Not asset task types of template {template_id}: "
            f"{', '.join(sorted(invalid_ids))}."
        )
    ProjectTemplateAssetTypeTaskTypeLink.query.filter_by(
        project_template_id=template_id, asset_type_id=asset_type_id
    ).delete()
    db.session.add_all(
        ProjectTemplateAssetTypeTaskTypeLink(
            project_template_id=template_id,
            asset_type_id=asset_type_id,
            task_type_id=task_type_id,
        )
        for task_type_id in wanted_ids
    )
    db.session.commit()
    _notify_template_change(template_id)
    return {"id": asset_type_id, "workflow": sorted(wanted_ids)}


def _links_in_settings(workflow_links, settings):
    """
    Return the workflow links whose asset type and task type are both in the
    settings of the given project or template. Do not copy a stale link.
    """
    asset_type_ids = {asset_type.id for asset_type in settings.asset_types}
    task_type_ids = {task_type.id for task_type in settings.task_types}
    return [
        link
        for link in workflow_links
        if link.asset_type_id in asset_type_ids
        and link.task_type_id in task_type_ids
    ]


def add_asset_type_to_template(template_id, asset_type_id):
    """
    Link an asset type to the given template. If it is already linked, do
    nothing.
    """
    asset_type = _check_required_id(
        EntityType, asset_type_id, "asset_type_id", "Asset type"
    )
    template = _ensure_template_exists(template_id)
    if str(asset_type.id) not in [str(at.id) for at in template.asset_types]:
        template.asset_types.append(asset_type)
        template.save()
    _notify_template_change(template_id)
    return {"id": str(asset_type.id), "name": asset_type.name}


def remove_asset_type_from_template(template_id, asset_type_id):
    """
    Unlink an asset type from the given template, with its workflow. If it is
    not linked, do nothing.
    """
    template = _ensure_template_exists(template_id)
    asset_type = EntityType.get(asset_type_id)
    if asset_type is not None:
        ProjectTemplateAssetTypeTaskTypeLink.query.filter_by(
            project_template_id=template_id, asset_type_id=asset_type_id
        ).delete()
        try:
            template.asset_types.remove(asset_type)
        except ValueError:
            pass
        template.save()
    _notify_template_change(template_id)


def get_template_status_automations(template_id):
    """
    Return the status automations of the given template.
    """
    template = _ensure_template_exists(template_id)
    return ProjectTemplate.serialize_list(template.status_automations)


def add_status_automation_to_template(template_id, status_automation_id):
    """
    Link a status automation to the given template. If it is already linked, do
    nothing.
    """
    automation = _check_required_id(
        StatusAutomation,
        status_automation_id,
        "status_automation_id",
        "Status automation",
    )
    template = _ensure_template_exists(template_id)
    if str(automation.id) not in [
        str(a.id) for a in template.status_automations
    ]:
        template.status_automations.append(automation)
        template.save()
    _notify_template_change(template_id)
    return automation.serialize()


def remove_status_automation_from_template(template_id, status_automation_id):
    """
    Unlink a status automation from the given template. If it is not linked, do
    nothing.
    """
    template = _ensure_template_exists(template_id)
    automation = StatusAutomation.get(status_automation_id)
    if automation is not None:
        try:
            template.status_automations.remove(automation)
            template.save()
        except ValueError:
            pass
    _notify_template_change(template_id)


def get_template_preview_background_files(template_id):
    """
    Return the preview background files of the given template, with the flag
    that shows which file is the default.
    """
    template = _ensure_template_exists(template_id)
    return [
        {
            "id": str(bg.id),
            "name": bg.name,
            "is_default": bool(bg.is_default),
        }
        for bg in template.preview_background_files
    ]


def add_preview_background_file_to_template(
    template_id, preview_background_file_id
):
    """
    Link a preview background file to the given template. If it is already
    linked, do nothing.
    """
    background = _check_required_id(
        PreviewBackgroundFile,
        preview_background_file_id,
        "preview_background_file_id",
        "Preview background file",
    )
    template = _ensure_template_exists(template_id)
    if str(background.id) not in [
        str(b.id) for b in template.preview_background_files
    ]:
        template.preview_background_files.append(background)
        template.save()
    _notify_template_change(template_id)
    return {
        "id": str(background.id),
        "name": background.name,
        "is_default": bool(background.is_default),
    }


def remove_preview_background_file_from_template(
    template_id, preview_background_file_id
):
    """
    Unlink a preview background file from the given template. If this file is
    the template default, clear the default.
    """
    template = _ensure_template_exists(template_id)
    background = PreviewBackgroundFile.get(preview_background_file_id)
    if background is not None:
        try:
            template.preview_background_files.remove(background)
            template.save()
        except ValueError:
            pass
    if str(template.default_preview_background_file_id or "") == str(
        preview_background_file_id
    ):
        template.update({"default_preview_background_file_id": None})
    _notify_template_change(template_id)


def set_template_default_preview_background_file(
    template_id, preview_background_file_id
):
    """
    Set which preview background file of the template is the default.
    """
    template = _ensure_template_exists(template_id)
    if preview_background_file_id is not None:
        linked_ids = [str(b.id) for b in template.preview_background_files]
        if str(preview_background_file_id) not in linked_ids:
            raise WrongParameterException(
                "Preview background file is not linked to this template"
            )
    template.update(
        {"default_preview_background_file_id": preview_background_file_id}
    )
    _notify_template_change(template_id)
    return template.serialize()


def set_template_metadata_descriptors(template_id, descriptors):
    """
    Replace the JSONB snapshot of the metadata descriptors on the template.
    """
    template = _ensure_template_exists(template_id)
    if descriptors is None:
        descriptors = []
    if not isinstance(descriptors, list):
        raise WrongParameterException("metadata_descriptors must be a list")
    cleaned = []
    for entry in descriptors:
        if not isinstance(entry, dict):
            raise WrongParameterException(
                "Each metadata descriptor must be an object"
            )
        cleaned.append(_clean_descriptor_dict(entry))
    template.update({"metadata_descriptors": cleaned})
    _notify_template_change(template.id)
    return template.serialize()


def _clean_descriptor_dict(descriptor):
    """
    Normalize a metadata descriptor dict, so that the snapshot has a stable
    shape. The shape does not change with the form that the caller sent.
    """
    name = descriptor.get("name", "")
    field_name = descriptor.get("field_name") or slugify.slugify(
        name, separator="_"
    )
    task_type_id = descriptor.get("task_type_id")
    return {
        "name": name,
        "field_name": field_name,
        "entity_type": descriptor.get("entity_type"),
        "task_type_id": str(task_type_id) if task_type_id else None,
        "data_type": descriptor.get("data_type"),
        "choices": descriptor.get("choices") or [],
        "for_client": bool(descriptor.get("for_client", False)),
        "departments": [
            str(dep_id)
            for dep_id in (descriptor.get("departments") or [])
            if dep_id is not None
        ],
        "position": descriptor.get("position"),
    }


# ---------------------------------------------------------------------------
# Snapshot a project into a template
# ---------------------------------------------------------------------------


def create_template_from_project(project_id, name, description=None):
    """
    Copy the configuration of an existing project into a new template.

    The function copies:
    - the production settings,
    - the task type links, with priorities, bitrates and client visibility,
    - the task status links, with priorities, roles_for_board and client
      permission,
    - the asset type links and their workflows,
    - the status automation links,
    - the preview background links and the default background,
    - the metadata descriptors, serialized to JSONB,
    - file_tree and data (free metadata).

    The function does NOT copy team members, dates, man_days, nb_episodes,
    episode_span, project_status, or production data.
    """
    project = projects_service.get_project_raw(project_id)

    template_data = {"name": name, "description": description}
    for field in PRODUCTION_SETTING_FIELDS:
        template_data[field] = getattr(project, field)
    template_data["file_tree"] = (
        dict(project.file_tree) if project.file_tree else None
    )
    template_data["data"] = dict(project.data) if project.data else None
    template_data["metadata_descriptors"] = _snapshot_descriptors(project_id)

    try:
        template = ProjectTemplate.create(**template_data)
    except IntegrityError:
        raise WrongParameterException(
            "A project template with this name already exists"
        )

    # Make a snapshot of the link tables.
    from zou.app.models.project import (
        ProjectAssetTypeTaskTypeLink,
        ProjectTaskStatusLink,
        ProjectTaskTypeLink,
    )

    task_type_links = ProjectTaskTypeLink.get_all_by(project_id=project_id)
    for link in task_type_links:
        ProjectTemplateTaskTypeLink.create(
            project_template_id=template.id,
            task_type_id=link.task_type_id,
            priority=link.priority,
            hd_bitrate_compression=link.hd_bitrate_compression,
            ld_bitrate_compression=link.ld_bitrate_compression,
            is_client_visible=link.is_client_visible,
        )

    task_status_links = ProjectTaskStatusLink.get_all_by(project_id=project_id)
    for link in task_status_links:
        ProjectTemplateTaskStatusLink.create(
            project_template_id=template.id,
            task_status_id=link.task_status_id,
            priority=link.priority,
            roles_for_board=link.roles_for_board,
            is_client_allowed=link.is_client_allowed,
        )

    for asset_type in project.asset_types:
        db.session.add(
            ProjectTemplateAssetTypeLink(
                project_template_id=template.id,
                asset_type_id=asset_type.id,
            )
        )

    for link in _links_in_settings(
        ProjectAssetTypeTaskTypeLink.query.filter_by(project_id=project_id),
        project,
    ):
        db.session.add(
            ProjectTemplateAssetTypeTaskTypeLink(
                project_template_id=template.id,
                asset_type_id=link.asset_type_id,
                task_type_id=link.task_type_id,
            )
        )

    for automation in project.status_automations:
        db.session.add(
            ProjectTemplateStatusAutomationLink(
                project_template_id=template.id,
                status_automation_id=automation.id,
            )
        )

    for background in project.preview_background_files:
        db.session.add(
            ProjectTemplatePreviewBackgroundFileLink(
                project_template_id=template.id,
                preview_background_file_id=background.id,
            )
        )
    if project.default_preview_background_file_id is not None:
        template.default_preview_background_file_id = (
            project.default_preview_background_file_id
        )
    db.session.commit()

    _notify_template_change(template.id, action="new")
    return template.serialize()


def _snapshot_descriptors(project_id):
    """
    Serialize the MetadataDescriptor rows of the project into the JSONB shape
    of the template.
    """
    descriptors = MetadataDescriptor.query.filter(
        MetadataDescriptor.project_id == project_id
    ).all()
    snapshot = []
    for descriptor in descriptors:
        snapshot.append(
            {
                "name": descriptor.name,
                "field_name": descriptor.field_name,
                "entity_type": descriptor.entity_type,
                "task_type_id": (
                    str(descriptor.task_type_id)
                    if descriptor.task_type_id is not None
                    else None
                ),
                "data_type": (
                    descriptor.data_type.code
                    if descriptor.data_type is not None
                    else None
                ),
                "choices": descriptor.choices or [],
                "for_client": bool(descriptor.for_client),
                "departments": [str(dep.id) for dep in descriptor.departments],
                "position": descriptor.position,
            }
        )
    return snapshot


# ---------------------------------------------------------------------------
# Apply a template to a project
# ---------------------------------------------------------------------------


def apply_template_to_project(project_id, template_id, override_settings=None):
    """
    Apply the configuration of a template to a project. Keep the existing links
    and skip the duplicates (additive strategy). Write the production settings
    to the project. If `override_settings` gives an explicit value for a field,
    write that value instead. The template also adds its asset type workflows,
    preview backgrounds, default background and metadata descriptors. Clear the
    project cache, emit project:update and return the project as a dict.
    """
    project = projects_service.get_project_raw(project_id)
    template = get_project_template_raw(template_id)

    override_settings = override_settings or {}

    # Build the field map: the explicit overrides have priority, and the
    # template gives the other values. Then write the result to the project in
    # a single update.
    settings_to_apply = {}
    for field in PRODUCTION_SETTING_FIELDS:
        if field in override_settings and override_settings[field] is not None:
            settings_to_apply[field] = override_settings[field]
        else:
            value = getattr(template, field)
            if value is not None:
                settings_to_apply[field] = value
    if "file_tree" in override_settings and override_settings["file_tree"]:
        settings_to_apply["file_tree"] = override_settings["file_tree"]
    elif template.file_tree is not None:
        settings_to_apply["file_tree"] = dict(template.file_tree)
    if "data" in override_settings and override_settings["data"]:
        settings_to_apply["data"] = override_settings["data"]
    elif template.data is not None:
        settings_to_apply["data"] = dict(template.data)

    if settings_to_apply:
        project.update(settings_to_apply)

    from zou.app.models.project import (
        ProjectAssetTypeLink,
        ProjectAssetTypeTaskTypeLink,
        ProjectStatusAutomationLink,
        ProjectTaskStatusLink,
        ProjectTaskTypeLink,
    )

    for link in ProjectTemplateTaskTypeLink.get_all_by(
        project_template_id=template.id
    ):
        existing = ProjectTaskTypeLink.get_by(
            project_id=project.id, task_type_id=link.task_type_id
        )
        if existing is None:
            ProjectTaskTypeLink.create(
                project_id=project.id,
                task_type_id=link.task_type_id,
                priority=link.priority,
                hd_bitrate_compression=link.hd_bitrate_compression,
                ld_bitrate_compression=link.ld_bitrate_compression,
                is_client_visible=link.is_client_visible,
            )

    for link in ProjectTemplateTaskStatusLink.get_all_by(
        project_template_id=template.id
    ):
        existing = ProjectTaskStatusLink.get_by(
            project_id=project.id, task_status_id=link.task_status_id
        )
        if existing is None:
            ProjectTaskStatusLink.create(
                project_id=project.id,
                task_status_id=link.task_status_id,
                priority=link.priority,
                roles_for_board=link.roles_for_board,
                is_client_allowed=link.is_client_allowed,
            )

    for link in ProjectTemplateAssetTypeLink.query.filter_by(
        project_template_id=template.id
    ).all():
        existing = ProjectAssetTypeLink.query.filter_by(
            project_id=project.id, asset_type_id=link.asset_type_id
        ).first()
        if existing is None:
            new_link = ProjectAssetTypeLink(
                project_id=project.id, asset_type_id=link.asset_type_id
            )
            db.session.add(new_link)

    # Additive, like the other links: if the project already sets a workflow
    # for an asset type, this workflow does not change.
    asset_types_with_workflow = {
        link.asset_type_id
        for link in ProjectAssetTypeTaskTypeLink.query.filter_by(
            project_id=project.id
        ).all()
    }
    for link in _links_in_settings(
        ProjectTemplateAssetTypeTaskTypeLink.query.filter_by(
            project_template_id=template.id
        ),
        template,
    ):
        if link.asset_type_id not in asset_types_with_workflow:
            db.session.add(
                ProjectAssetTypeTaskTypeLink(
                    project_id=project.id,
                    asset_type_id=link.asset_type_id,
                    task_type_id=link.task_type_id,
                )
            )

    for link in ProjectTemplateStatusAutomationLink.query.filter_by(
        project_template_id=template.id
    ).all():
        existing = ProjectStatusAutomationLink.query.filter_by(
            project_id=project.id,
            status_automation_id=link.status_automation_id,
        ).first()
        if existing is None:
            new_link = ProjectStatusAutomationLink(
                project_id=project.id,
                status_automation_id=link.status_automation_id,
            )
            db.session.add(new_link)

    from zou.app.models.project import ProjectPreviewBackgroundFileLink

    for link in ProjectTemplatePreviewBackgroundFileLink.query.filter_by(
        project_template_id=template.id
    ).all():
        existing = ProjectPreviewBackgroundFileLink.query.filter_by(
            project_id=project.id,
            preview_background_file_id=link.preview_background_file_id,
        ).first()
        if existing is None:
            new_link = ProjectPreviewBackgroundFileLink(
                project_id=project.id,
                preview_background_file_id=link.preview_background_file_id,
            )
            db.session.add(new_link)

    db.session.commit()

    # If the template has a default background and the target does not, apply
    # it.
    if (
        template.default_preview_background_file_id is not None
        and "default_preview_background_file_id" not in override_settings
        and project.default_preview_background_file_id is None
    ):
        project.update(
            {
                "default_preview_background_file_id": (
                    template.default_preview_background_file_id
                )
            }
        )

    descriptors_snapshot = template.metadata_descriptors or []
    for descriptor in descriptors_snapshot:
        _create_descriptor_from_snapshot(project.id, descriptor)

    projects_service.clear_project_cache(str(project.id))
    events.emit("project:update", {}, project_id=str(project.id))
    return project.serialize()


def _create_descriptor_from_snapshot(project_id, descriptor):
    """
    Create a MetadataDescriptor on the target project from the JSONB snapshot
    and return it as a dict. If a descriptor with the same (entity_type, name,
    task_type_id) already exists, return it as an active record. If the
    snapshot is incomplete or not valid, return None.
    """
    name = descriptor.get("name") or ""
    entity_type = descriptor.get("entity_type")
    if not name or not entity_type:
        return None
    task_type_id = descriptor.get("task_type_id")
    if entity_type == "Task" and task_type_id is None:
        return None

    existing = MetadataDescriptor.query.filter_by(
        project_id=project_id,
        entity_type=entity_type,
        name=name,
        task_type_id=task_type_id,
    ).first()
    if existing is not None:
        return existing

    try:
        return metadata_descriptors_service.add_metadata_descriptor(
            project_id=project_id,
            entity_type=entity_type,
            name=name,
            data_type=descriptor.get("data_type"),
            choices=descriptor.get("choices") or [],
            for_client=bool(descriptor.get("for_client", False)),
            departments=descriptor.get("departments") or [],
            task_type_id=task_type_id,
        )
    except WrongParameterException:
        return None
