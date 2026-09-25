import slugify

from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.utils import cache

from zou.app.services import (
    entities_service,
    files_service,
    projects_service,
    tasks_service,
    shots_service,
    persons_service,
)


def get_full_entity_name(entity_id):
    """
    Full name of an entity ("Episode / Sequence / Shot", "Type / Asset").
    Computed by entities_service, which owns the entity cache the
    memoization is keyed on; looked up at call time, not at import time,
    since that module is still loading when this one is imported from it.
    """
    return entities_service.get_full_entity_name(entity_id)


def get_full_entity_names(entity_ids):
    """
    Batch version of get_full_entity_name, see entities_service.
    """
    return entities_service.get_full_entity_names(entity_ids)


def get_preview_file_name(preview_file_id):
    """
    Build unique and human readable file name for preview downloads. The
    convention followed is:
    [project_name]_[entity_name]_[task_type_name]_v[revivision].[extension].
    """
    organisation = persons_service.get_organisation()
    preview_file = files_service.get_preview_file(preview_file_id)
    task = tasks_service.get_task(preview_file["task_id"])
    task_type = tasks_service.get_task_type(task["task_type_id"])
    project = projects_service.get_project(task["project_id"])
    entity_name, _, _ = get_full_entity_name(task["entity_id"])

    if (
        organisation["use_original_file_name"]
        and preview_file.get("original_name", None) is not None
    ):
        name = preview_file["original_name"]
    else:
        name = (
            f"{project['name']}_{entity_name}_{task_type['name']}_v"
            f"{preview_file['revision']}"
        )
        name = slugify.slugify(name, separator="_")
    if (preview_file.get("position", 0) or 0) > 1:
        name = f"{name}-{preview_file['position']}"
    return f"{name}.{preview_file['extension']}"
