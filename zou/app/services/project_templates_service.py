import slugify

from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.models.entity_type import EntityType
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project_template import (
    ProjectTemplate,
    ProjectTemplateAssetTypeLink,
    ProjectTemplateStatusAutomationLink,
    ProjectTemplateTaskStatusLink,
    ProjectTemplateTaskTypeLink,
)
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType

from zou.app.services import projects_service
from zou.app.services.exception import (
    ProjectNotFoundException,
    ProjectTemplateNotFoundException,
    WrongParameterException,
)

from zou.app.utils import events, fields


# Production-setting fields that are copied between Project and
# ProjectTemplate. Excluded on purpose: name, description (set explicitly),
# any team / dates / production-data fields, and the JSONB columns
# file_tree / data which are handled separately.
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
]


def clear_project_template_cache():
    """
    Stub kept so call sites are stable. Template reads are not cached for
    now because templates are admin-only and updated infrequently — adding
    a memoize layer is easy if/when access patterns change.
    """
    pass


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def get_project_template_raw(template_id):
    """
    Return template ORM instance for given id, or raise.
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
    Return template dict for given id, or raise.
    """
    return get_project_template_raw(template_id).serialize()


def get_project_templates():
    """
    Return all templates as a list of dicts.
    """
    templates = ProjectTemplate.query.order_by(ProjectTemplate.name).all()
    return fields.serialize_models(templates)


def get_project_template_by_name(name):
    template = ProjectTemplate.query.filter(
        ProjectTemplate.name.ilike(name)
    ).first()
    if template is None:
        raise ProjectTemplateNotFoundException()
    return template.serialize()


def create_project_template(name, description=None, **settings):
    """
    Create a new empty template. Extra keyword arguments are forwarded as
    production settings.
    """
    if not name:
        raise WrongParameterException("name is required")
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
    clear_project_template_cache()
    events.emit(
        "project-template:new", {"project_template_id": str(template.id)}
    )
    return template.serialize()


def update_project_template(template_id, changes):
    """
    Update template fields.
    """
    template = get_project_template_raw(template_id)
    # Filter out fields the caller can't change directly.
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
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template.id)},
    )
    return template.serialize()


def delete_project_template(template_id):
    """
    Delete a template (and its link rows via the link tables).
    """
    template = get_project_template_raw(template_id)
    template_dict = template.serialize()
    template.delete()
    clear_project_template_cache()
    events.emit(
        "project-template:delete",
        {"project_template_id": template_dict["id"]},
    )
    return template_dict


# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------


def _ensure_template_exists(template_id):
    return get_project_template_raw(template_id)


def get_template_task_types(template_id):
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
        result.append(data)
    result.sort(key=lambda t: (t.get("priority") or 0, t.get("name", "")))
    return result


def add_task_type_to_template(template_id, task_type_id, priority=None):
    if not task_type_id or not fields.is_valid_id(task_type_id):
        raise WrongParameterException(
            "task_type_id is required and must be a valid UUID"
        )
    if TaskType.get(task_type_id) is None:
        raise WrongParameterException(
            f"Task type {task_type_id} does not exist"
        )
    _ensure_template_exists(template_id)
    if priority is not None:
        priority = int(priority)
    link = ProjectTemplateTaskTypeLink.get_by(
        project_template_id=template_id, task_type_id=task_type_id
    )
    if link is None:
        link = ProjectTemplateTaskTypeLink.create(
            project_template_id=template_id,
            task_type_id=task_type_id,
            priority=priority,
        )
    elif priority is not None:
        link.update({"priority": priority})
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template_id)},
    )
    return link.serialize()


def remove_task_type_from_template(template_id, task_type_id):
    link = ProjectTemplateTaskTypeLink.get_by(
        project_template_id=template_id, task_type_id=task_type_id
    )
    if link is not None:
        link.delete()
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template_id)},
    )


def get_template_task_statuses(template_id):
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
        result.append(data)
    result.sort(key=lambda s: (s.get("priority") or 0, s.get("name", "")))
    return result


def add_task_status_to_template(
    template_id, task_status_id, priority=None, roles_for_board=None
):
    if not task_status_id or not fields.is_valid_id(task_status_id):
        raise WrongParameterException(
            "task_status_id is required and must be a valid UUID"
        )
    if TaskStatus.get(task_status_id) is None:
        raise WrongParameterException(
            f"Task status {task_status_id} does not exist"
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
        )
    else:
        update_data = {}
        if priority is not None:
            update_data["priority"] = priority
        if roles_for_board is not None:
            update_data["roles_for_board"] = roles_for_board
        if update_data:
            link.update(update_data)
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template_id)},
    )
    return link.serialize()


def remove_task_status_from_template(template_id, task_status_id):
    link = ProjectTemplateTaskStatusLink.get_by(
        project_template_id=template_id, task_status_id=task_status_id
    )
    if link is not None:
        link.delete()
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template_id)},
    )


def get_template_asset_types(template_id):
    template = _ensure_template_exists(template_id)
    return [
        {"id": str(asset_type.id), "name": asset_type.name}
        for asset_type in template.asset_types
    ]


def add_asset_type_to_template(template_id, asset_type_id):
    if not asset_type_id or not fields.is_valid_id(asset_type_id):
        raise WrongParameterException(
            "asset_type_id is required and must be a valid UUID"
        )
    asset_type = EntityType.get(asset_type_id)
    if asset_type is None:
        raise WrongParameterException(
            f"Asset type {asset_type_id} does not exist"
        )
    template = _ensure_template_exists(template_id)
    if str(asset_type.id) not in [str(at.id) for at in template.asset_types]:
        template.asset_types.append(asset_type)
        template.save()
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template_id)},
    )
    return {"id": str(asset_type.id), "name": asset_type.name}


def remove_asset_type_from_template(template_id, asset_type_id):
    template = _ensure_template_exists(template_id)
    asset_type = EntityType.get(asset_type_id)
    if asset_type is not None:
        try:
            template.asset_types.remove(asset_type)
            template.save()
        except ValueError:
            pass
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template_id)},
    )


def get_template_status_automations(template_id):
    template = _ensure_template_exists(template_id)
    return ProjectTemplate.serialize_list(template.status_automations)


def add_status_automation_to_template(template_id, status_automation_id):
    if not status_automation_id or not fields.is_valid_id(
        status_automation_id
    ):
        raise WrongParameterException(
            "status_automation_id is required and must be a valid UUID"
        )
    automation = StatusAutomation.get(status_automation_id)
    if automation is None:
        raise WrongParameterException(
            f"Status automation {status_automation_id} does not exist"
        )
    template = _ensure_template_exists(template_id)
    if str(automation.id) not in [
        str(a.id) for a in template.status_automations
    ]:
        template.status_automations.append(automation)
        template.save()
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template_id)},
    )
    return automation.serialize()


def remove_status_automation_from_template(template_id, status_automation_id):
    template = _ensure_template_exists(template_id)
    automation = StatusAutomation.get(status_automation_id)
    if automation is not None:
        try:
            template.status_automations.remove(automation)
            template.save()
        except ValueError:
            pass
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template_id)},
    )


def set_template_metadata_descriptors(template_id, descriptors):
    """
    Replace the JSONB metadata descriptor snapshot on the template.
    """
    template = _ensure_template_exists(template_id)
    if descriptors is None:
        descriptors = []
    if not isinstance(descriptors, list):
        raise WrongParameterException(
            "metadata_descriptors must be a list"
        )
    cleaned = []
    for entry in descriptors:
        if not isinstance(entry, dict):
            raise WrongParameterException(
                "Each metadata descriptor must be an object"
            )
        cleaned.append(_clean_descriptor_dict(entry))
    template.update({"metadata_descriptors": cleaned})
    clear_project_template_cache()
    events.emit(
        "project-template:update",
        {"project_template_id": str(template.id)},
    )
    return template.serialize()


def _clean_descriptor_dict(descriptor):
    """
    Normalize a metadata descriptor dict so the snapshot has a stable shape
    regardless of how the caller submitted it.
    """
    name = descriptor.get("name", "")
    field_name = descriptor.get("field_name") or slugify.slugify(
        name, separator="_"
    )
    return {
        "name": name,
        "field_name": field_name,
        "entity_type": descriptor.get("entity_type"),
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
    Extract the configuration of an existing project into a new template.

    Copies: production settings, task type links (with priorities), task
    status links (with priorities and roles_for_board), asset type links,
    status automation links, metadata descriptors (serialized to JSONB),
    file_tree and data (free metadata).

    Does NOT copy: team members, dates, man_days, nb_episodes, episode_span,
    preview backgrounds, project_status, or any production data.
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

    # Snapshot link tables
    from zou.app.models.project import (
        ProjectTaskStatusLink,
        ProjectTaskTypeLink,
    )

    task_type_links = ProjectTaskTypeLink.get_all_by(project_id=project_id)
    for link in task_type_links:
        ProjectTemplateTaskTypeLink.create(
            project_template_id=template.id,
            task_type_id=link.task_type_id,
            priority=link.priority,
        )

    task_status_links = ProjectTaskStatusLink.get_all_by(
        project_id=project_id
    )
    for link in task_status_links:
        ProjectTemplateTaskStatusLink.create(
            project_template_id=template.id,
            task_status_id=link.task_status_id,
            priority=link.priority,
            roles_for_board=link.roles_for_board,
        )

    from zou.app import db

    for asset_type in project.asset_types:
        db.session.add(
            ProjectTemplateAssetTypeLink(
                project_template_id=template.id,
                asset_type_id=asset_type.id,
            )
        )

    for automation in project.status_automations:
        db.session.add(
            ProjectTemplateStatusAutomationLink(
                project_template_id=template.id,
                status_automation_id=automation.id,
            )
        )
    db.session.commit()

    clear_project_template_cache()
    events.emit(
        "project-template:new",
        {"project_template_id": str(template.id)},
    )
    return template.serialize()


def _snapshot_descriptors(project_id):
    """
    Serialize the project's MetadataDescriptor rows into the JSONB shape
    used on the template.
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
                "data_type": (
                    descriptor.data_type.code
                    if descriptor.data_type is not None
                    else None
                ),
                "choices": descriptor.choices or [],
                "for_client": bool(descriptor.for_client),
                "departments": [
                    str(dep.id) for dep in descriptor.departments
                ],
                "position": descriptor.position,
            }
        )
    return snapshot


# ---------------------------------------------------------------------------
# Apply a template to a project
# ---------------------------------------------------------------------------


def apply_template_to_project(
    project_id, template_id, override_settings=None
):
    """
    Apply a template's configuration to a project. Existing links are kept;
    duplicates are skipped (additive strategy). Production settings are
    written to the project unless `override_settings` provides an explicit
    value for that field.
    """
    project = projects_service.get_project_raw(project_id)
    template = get_project_template_raw(template_id)

    override_settings = override_settings or {}

    # Build the field map: explicit overrides win, template fills the rest.
    # The result is then written to the project in a single update.
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
            from zou.app import db

            db.session.add(new_link)

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
            from zou.app import db

            db.session.add(new_link)

    from zou.app import db

    db.session.commit()

    # Apply metadata descriptors snapshot
    descriptors_snapshot = template.metadata_descriptors or []
    for descriptor in descriptors_snapshot:
        _create_descriptor_from_snapshot(project.id, descriptor)

    projects_service.clear_project_cache(str(project.id))
    events.emit(
        "project:update", {}, project_id=str(project.id)
    )
    return project.serialize()


def _create_descriptor_from_snapshot(project_id, descriptor):
    """
    Create a MetadataDescriptor on the target project from the JSONB
    snapshot. Skips silently if a descriptor with the same (entity_type,
    name) already exists.
    """
    name = descriptor.get("name") or ""
    entity_type = descriptor.get("entity_type")
    if not name or not entity_type:
        return None

    existing = MetadataDescriptor.query.filter_by(
        project_id=project_id, entity_type=entity_type, name=name
    ).first()
    if existing is not None:
        return existing

    try:
        return projects_service.add_metadata_descriptor(
            project_id=project_id,
            entity_type=entity_type,
            name=name,
            data_type=descriptor.get("data_type"),
            choices=descriptor.get("choices") or [],
            for_client=bool(descriptor.get("for_client", False)),
            departments=descriptor.get("departments") or [],
        )
    except WrongParameterException:
        return None
