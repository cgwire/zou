from zou.app.services import (
    base_service,
    projects_service,
    notifications_service,
)
from zou.app.utils import (
    date_helpers,
    cache,
    events,
    fields,
    query as query_utils,
)

from zou.app.models.entity import Entity, EntityLink, EntityConceptLink
from zou.app.models.entity_type import EntityType
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import assignees_table
from zou.app.models.task import Task

from zou.app import db

from zou.app.services.exception import (
    PreviewFileNotFoundException,
    EntityLinkNotFoundException,
    EntityNotFoundException,
    EntityTypeNotFoundException,
)


def clear_entity_cache(entity_id):
    cache.cache.delete_memoized(get_entity, entity_id)


def clear_entity_type_cache(entity_type_id):
    cache.cache.delete_memoized(get_entity_type, entity_type_id)
    cache.cache.delete_memoized(get_entity_type_by_name)


def get_temporal_entity_type_by_name(name):
    entity_type = get_entity_type_by_name(name)
    if entity_type is None:
        cache.cache.delete_memoized(get_entity_type_by_name, name)
        entity_type = get_entity_type_by_name(name)
    return entity_type


@cache.memoize_function(240)
def get_entity_type(entity_type_id):
    """
    Return an entity type matching given id, as a dict. Raises an exception
    if nothing is found.
    """
    return base_service.get_instance(
        EntityType, entity_type_id, EntityTypeNotFoundException
    ).serialize()


@cache.memoize_function(240)
def get_entity_type_by_name(name):
    """
    Return entity type maching *name*. If it doesn't exist, it creates it.
    """
    entity_type = EntityType.get_by(name=name)
    if entity_type is None:
        entity_type = EntityType.create(name=name)
    return entity_type.serialize()


@cache.memoize_function(240)
def get_entity_type_by_name_or_not_found(name):
    """
    Return entity type maching *name*. If it doesn't exist, it creates it.
    """
    entity_type = EntityType.get_by(name=name)
    if entity_type is None:
        raise EntityTypeNotFoundException
    return entity_type.serialize()


def get_entity_raw(entity_id):
    """
    Return an entity type matching given id, as an active record. Raises an
    exception if nothing is found.
    """
    return base_service.get_instance(
        Entity, entity_id, EntityNotFoundException
    )


@cache.memoize_function(120)
def get_entity(entity_id):
    """
    Return an entity type matching given id, as a dict. Raises an exception if
    nothing is found.
    """
    return base_service.get_instance(
        Entity, entity_id, EntityNotFoundException
    ).serialize()


def update_entity_preview(entity_id, preview_file_id):
    """
    Update given entity main preview. If entity or preview is not found, it
    raises an exception.
    """
    entity = Entity.get(entity_id)
    if entity is None:
        raise EntityNotFoundException

    preview_file = PreviewFile.get(preview_file_id)
    if preview_file is None:
        raise PreviewFileNotFoundException

    entity.update({"preview_file_id": preview_file.id})
    clear_entity_cache(str(entity.id))
    events.emit(
        "preview-file:set-main",
        {"entity_id": entity_id, "preview_file_id": preview_file_id},
        project_id=str(entity.project_id),
    )
    entity_type = EntityType.get(entity.entity_type_id)
    entity_type_name = "asset"
    if entity_type.name in ["Shot", "Scene", "Sequence", "Episode", "Concept"]:
        entity_type_name = entity_type.name.lower()
    events.emit(
        "%s:update" % entity_type_name,
        {"%s_id" % entity_type_name: str(entity.id)},
        project_id=str(entity.project_id),
    )
    return entity.serialize()


def get_entities_for_project(
    project_id,
    entity_type_id,
    obj_type="Entity",
    episode_id=None,
    only_assigned=False,
):
    """
    Retrieve all entities related to given project of which entity is entity
    type.
    """
    from zou.app.services import user_service

    query = (
        Entity.query.filter(Entity.entity_type_id == entity_type_id)
        .filter(Entity.project_id == project_id)
        .order_by(Entity.name)
    )

    if episode_id is not None:
        query = query.filter(Entity.parent_id == episode_id)

    if only_assigned:
        query = query.outerjoin(Task).filter(
            user_service.build_assignee_filter()
        )
    result = query.all()
    return Entity.serialize_list(result, obj_type=obj_type)


def get_entity_links_for_project(
    project_id,
    page=None,
    limit=None,
    cursor_created_at=None,
):
    """
    Retrieve entity links for given project.
    """
    query = EntityLink.query.filter(Entity.project_id == project_id).join(
        Entity, EntityLink.entity_in_id == Entity.id
    )

    results = []
    if page is not None and page > 0:
        if limit < 1:
            limit = None
        query = query.order_by(EntityLink.created_at, EntityLink.id)
        results = query_utils.get_paginated_results(query, page, limit=limit)
    elif cursor_created_at is not None:
        if limit < 1:
            limit = None
        created_at = date_helpers.get_datetime_from_string(
            cursor_created_at, milliseconds=True
        )
        results = query_utils.get_cursor_results(
            EntityLink, query, created_at, limit=limit
        )
    else:
        query = query.order_by(EntityLink.created_at, EntityLink.id)
        if limit is not None and limit > 0:
            query = query.limit(limit)
        for entity_link in query.all():
            results.append(
                {
                    "id": entity_link.id,
                    "entity_in_id": entity_link.entity_in_id,
                    "entity_out_id": entity_link.entity_out_id,
                    "nb_occurences": entity_link.nb_occurences,
                    "label": entity_link.label,
                    "data": entity_link.data,
                    "created_at": date_helpers.get_date_string(
                        entity_link.created_at, milliseconds=True
                    ),
                    "type": "EntityLink",
                }
            )
    return results


def get_entities_and_tasks(criterions={}):
    """
    Get all entities for given criterions with related tasks for each entity.
    """
    if "episode_id" in criterions and criterions["episode_id"] == "all":
        return []

    entity_map = {}
    task_map = {}
    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None),
        criterions.get("entity_type_id", None),
    )

    query = (
        Entity.query.outerjoin(Task, Task.entity_id == Entity.id)
        .outerjoin(assignees_table)
        .add_columns(
            Task.id,
            Task.task_type_id,
            Task.task_status_id,
            Task.priority,
            Task.estimation,
            Task.duration,
            Task.retake_count,
            Task.real_start_date,
            Task.end_date,
            Task.start_date,
            Task.due_date,
            Task.last_comment_date,
            assignees_table.columns.person,
        )
    )

    if "entity_type_id" in criterions:
        query = query.filter(
            Entity.entity_type_id == criterions["entity_type_id"]
        )

    if "project_id" in criterions:
        query = query.filter(Entity.project_id == criterions["project_id"])

    if "episode_id" in criterions:
        query = query.filter(Entity.parent_id == criterions["episode_id"])

    for (
        entity,
        task_id,
        task_type_id,
        task_status_id,
        task_priority,
        task_estimation,
        task_duration,
        task_retake_count,
        task_real_start_date,
        task_end_date,
        task_start_date,
        task_due_date,
        task_last_comment_date,
        person_id,
    ) in query.all():
        entity_id = str(entity.id)

        entity.data = entity.data or {}

        if entity_id not in entity_map:
            status = "running"
            if entity.status is not None:
                status = str(entity.status.code)
            entity_map[entity_id] = {
                "id": str(entity.id),
                "name": entity.name,
                "status": status,
                "episode_id": str(entity.parent_id),
                "description": entity.description,
                "frame_in": entity.data.get("frame_in", None),
                "frame_out": entity.data.get("frame_out", None),
                "fps": entity.data.get("fps", None),
                "preview_file_id": str(entity.preview_file_id or ""),
                "canceled": entity.canceled,
                "data": fields.serialize_value(entity.data),
                "tasks": [],
            }

        if task_id is not None:
            task_id = str(task_id)
            if task_id not in task_map:
                task_dict = fields.serialize_dict(
                    {
                        "id": task_id,
                        "estimation": task_estimation,
                        "entity_id": entity_id,
                        "end_date": task_end_date,
                        "due_date": task_due_date,
                        "duration": task_duration,
                        "is_subscribed": subscription_map.get(task_id, False),
                        "last_comment_date": task_last_comment_date,
                        "priority": task_priority or 0,
                        "real_start_date": task_real_start_date,
                        "retake_count": task_retake_count,
                        "start_date": task_start_date,
                        "task_status_id": str(task_status_id),
                        "task_type_id": str(task_type_id),
                        "assignees": [],
                    }
                )
                task_map[task_id] = task_dict
                entity_dict = entity_map[entity_id]
                entity_dict["tasks"].append(task_dict)

            if person_id:
                task_map[task_id]["assignees"].append(str(person_id))

    return list(entity_map.values())


def remove_entity_link(link_id):
    try:
        link = EntityLink.get_by(id=link_id)
        link.delete()
        return link.serialize()
    except BaseException:
        raise EntityLinkNotFoundException


def get_not_allowed_descriptors_fields_for_vendor(
    entity_type="Asset", departments=[], projects_ids=[]
):
    not_allowed_descriptors_field_names = {}
    for project_id in projects_ids:
        not_allowed_descriptors_field_names[project_id] = [
            descriptor["field_name"]
            for descriptor in projects_service.get_metadata_descriptors(
                project_id
            )
            if descriptor["entity_type"] == entity_type
            and descriptor["departments"] != []
            and len(set(departments) & set(descriptor["departments"])) == 0
        ]
    return not_allowed_descriptors_field_names


def remove_not_allowed_fields_from_metadata(
    not_allowed_descriptors_field_names=[], data={}
):
    return {
        key: data[key]
        for key in data.keys()
        if key not in not_allowed_descriptors_field_names
    }


def get_linked_entities_with_tasks(entity_id):
    """
    Return all entities and their tasks linked to given entity.
    """
    entities_in = (
        db.session.query(EntityConceptLink.entity_in_id)
        .filter(EntityConceptLink.entity_out_id == entity_id)
        .distinct()
    )

    entity_map = {}
    task_map = {}

    query = (
        Entity.query.join(Project, Project.id == Entity.project_id)
        .outerjoin(Task, Task.entity_id == Entity.id)
        .outerjoin(assignees_table)
        .join(EntityType)
        .add_columns(
            Task.id,
            Task.task_type_id,
            Task.task_status_id,
            Task.priority,
            Task.estimation,
            Task.duration,
            Task.retake_count,
            Task.real_start_date,
            Task.end_date,
            Task.start_date,
            Task.due_date,
            Task.last_comment_date,
            Task.nb_assets_ready,
            Task.assigner_id,
            assignees_table.columns.person,
            Project.id,
            Project.name,
            EntityType.name,
        )
        .filter(Entity.id.in_(entities_in))
    )
    query_result = query.all()

    for (
        entity,
        task_id,
        task_type_id,
        task_status_id,
        task_priority,
        task_estimation,
        task_duration,
        task_retake_count,
        task_real_start_date,
        task_end_date,
        task_start_date,
        task_due_date,
        task_last_comment_date,
        task_nb_assets_ready,
        task_assigner_id,
        person_id,
        project_id,
        project_name,
        entity_type_name,
    ) in query_result:
        entity_id = str(entity.id)

        if entity_id not in entity_map:
            data = fields.serialize_value(entity.data or {})

            entity_map[entity_id] = fields.serialize_dict(
                {
                    "canceled": entity.canceled,
                    "data": data,
                    "description": entity.description,
                    "entity_type_id": entity.entity_type_id,
                    "fps": data.get("fps", None),
                    "frame_in": data.get("frame_in", None),
                    "frame_out": data.get("frame_out", None),
                    "id": entity.id,
                    "name": entity.name,
                    "nb_frames": entity.nb_frames,
                    "parent_id": entity.parent_id,
                    "preview_file_id": entity.preview_file_id or None,
                    "project_id": project_id,
                    "project_name": project_name,
                    "source_id": entity.source_id,
                    "nb_entities_out": entity.nb_entities_out,
                    "is_casting_standby": entity.is_casting_standby,
                    "tasks": [],
                    "entity_concept_links": entity.entity_concept_links,
                    "type": (
                        entity_type_name
                        if entity_type_name
                        in [
                            "Shot",
                            "Sequence",
                            "Scene",
                            "Edit",
                            "Concept",
                            "Episode",
                        ]
                        else "Asset"
                    ),
                    "updated_at": entity.updated_at,
                    "created_at": entity.created_at,
                    "created_by": entity.created_by,
                }
            )

        if task_id is not None:
            task_id = str(task_id)
            if task_id not in task_map:
                task_dict = fields.serialize_dict(
                    {
                        "id": task_id,
                        "duration": task_duration,
                        "due_date": task_due_date,
                        "end_date": task_end_date,
                        "entity_id": entity_id,
                        "estimation": task_estimation,
                        "last_comment_date": task_last_comment_date,
                        "nb_assets_ready": task_nb_assets_ready,
                        "priority": task_priority or 0,
                        "real_start_date": task_real_start_date,
                        "retake_count": task_retake_count,
                        "start_date": task_start_date,
                        "task_status_id": task_status_id,
                        "task_type_id": task_type_id,
                        "assigner_id": task_assigner_id,
                        "assignees": [],
                    }
                )
                task_map[task_id] = task_dict
                entity_dict = entity_map[entity_id]
                entity_dict["tasks"].append(task_dict)

            if person_id:
                task_map[task_id]["assignees"].append(str(person_id))

    return list(entity_map.values())
