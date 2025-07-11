from datetime import date, timedelta
from sqlalchemy.exc import StatementError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import update


from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.milestone import Milestone
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.utils import events, fields, cache
from zou.app.services import (
    assets_service,
    base_service,
    shots_service,
    tasks_service,
    projects_service,
)
from zou.app import db

from zou.app.services.exception import (
    ProductionScheduleVersionNotFoundException,
)


def clear_production_schedule_version_cache(production_schedule_version_id):
    cache.cache.delete_memoized(
        get_production_schedule_version, production_schedule_version_id
    )
    cache.cache.delete_memoized(
        get_production_schedule_version, production_schedule_version_id, True
    )


def get_schedule_items(project_id):
    """
    Get all project schedule items (mainly for sync purpose).
    """
    schedule_items = ScheduleItem.query.filter_by(project_id=project_id).all()
    return fields.serialize_list(schedule_items)


def get_task_types_schedule_items(project_id):
    """
    Return all schedule items for given project. If no schedule item exists
    for a given task type, it creates one.
    """
    task_types = tasks_service.get_task_types_for_project(project_id)
    task_types = [
        task_type
        for task_type in task_types
        if task_type["for_entity"] in ["Asset", "Shot"]
    ]
    task_type_map = base_service.get_model_map_from_array(task_types)
    schedule_items = set(
        ScheduleItem.query.filter_by(project_id=project_id)
        .filter(ScheduleItem.object_id == None)
        .all()
    )
    schedule_item_map = {
        str(schedule_item.task_type_id): schedule_item
        for schedule_item in schedule_items
    }

    new_schedule_items = set()
    schedule_item_to_remove = set()
    for schedule_item in schedule_items:
        if schedule_item.task_type_id is not None:
            if str(schedule_item.task_type_id) not in task_type_map:
                schedule_item_to_remove.add(schedule_item)

    for task_type in task_types:
        if task_type["id"] not in schedule_item_map:
            new_schedule_item = ScheduleItem.create(
                project_id=project_id,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=1),
                task_type_id=task_type["id"],
            )
            new_schedule_items.add(new_schedule_item)
            events.emit(
                "schedule-item:new",
                {"schedule_item_id": str(new_schedule_item.id)},
                project_id=project_id,
            )

    schedule_items = (
        schedule_items.union(new_schedule_items) - schedule_item_to_remove
    )
    return sorted(
        [schedule_item.present() for schedule_item in schedule_items],
        key=lambda x: x["start_date"],
    )


def get_asset_types_schedule_items(project_id, task_type_id):
    """
    Return all asset type schedule items for given project. If no schedule item
    exists for a given asset type, it creates one.
    """
    asset_types = assets_service.get_asset_types_for_project(project_id)
    asset_type_map = base_service.get_model_map_from_array(asset_types)
    existing_schedule_items = set(
        ScheduleItem.query.join(
            EntityType, ScheduleItem.object_id == EntityType.id
        )
        .filter(ScheduleItem.project_id == project_id)
        .filter(ScheduleItem.task_type_id == task_type_id)
        .all()
    )
    return get_entity_schedule_items(
        project_id,
        task_type_id,
        asset_types,
        asset_type_map,
        existing_schedule_items,
    )


def get_episodes_schedule_items(project_id, task_type_id):
    """
    Return all episode schedule items for given project. If no schedule item
    exists for a given asset type, it creates one.
    """
    episode_type = shots_service.get_episode_type()
    episodes = shots_service.get_episodes_for_project(project_id)
    episodes_map = base_service.get_model_map_from_array(episodes)
    existing_schedule_items = set(
        ScheduleItem.query.join(Entity, ScheduleItem.object_id == Entity.id)
        .filter(ScheduleItem.project_id == project_id)
        .filter(Entity.entity_type_id == episode_type["id"])
        .filter(ScheduleItem.task_type_id == task_type_id)
        .all()
    )
    return get_entity_schedule_items(
        project_id,
        task_type_id,
        episodes,
        episodes_map,
        existing_schedule_items,
    )


def get_sequences_schedule_items(project_id, task_type_id, episode_id=None):
    """
    Return all asset type schedule items for given project. If no schedule item
    exists for a given asset type, it creates one.
    """
    if episode_id is not None:
        sequences = shots_service.get_sequences_for_episode(episode_id)
    else:
        sequences = shots_service.get_sequences_for_project(project_id)
    sequence_map = base_service.get_model_map_from_array(sequences)
    sequence_type = shots_service.get_sequence_type()

    query = (
        ScheduleItem.query.join(Entity, ScheduleItem.object_id == Entity.id)
        .filter(ScheduleItem.project_id == project_id)
        .filter(Entity.entity_type_id == sequence_type["id"])
        .filter(ScheduleItem.task_type_id == task_type_id)
    )
    if episode_id is not None:
        query = query.filter(Entity.parent_id == episode_id)
    existing_schedule_items = set(query.all())

    return get_entity_schedule_items(
        project_id,
        task_type_id,
        sequences,
        sequence_map,
        existing_schedule_items,
    )


def get_entity_schedule_items(
    project_id, task_type_id, to_create, to_create_map, existing_schedule_items
):
    schedule_item_map = {
        str(schedule_item.object_id): schedule_item
        for schedule_item in existing_schedule_items
    }

    new_schedule_items = set()
    schedule_item_to_remove = set()
    for schedule_item in existing_schedule_items:
        if schedule_item.object_id is not None:
            if str(schedule_item.object_id) not in to_create_map:
                schedule_item_to_remove.add(schedule_item)

    for entity in to_create:
        if entity["id"] not in schedule_item_map:
            new_schedule_item = ScheduleItem.create(
                project_id=project_id,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=1),
                object_id=entity["id"],
                task_type_id=task_type_id,
            )
            events.emit(
                "schedule-item:new",
                {"schedule_item_id": str(new_schedule_item.id)},
                project_id=project_id,
            )
            new_schedule_items.add(new_schedule_item)

    schedule_items = (
        existing_schedule_items.union(new_schedule_items)
        - schedule_item_to_remove
    )

    results = []
    for schedule_item in schedule_items:
        result = schedule_item.present()
        result["name"] = to_create_map[result["object_id"]]["name"]
        results.append(result)

    return sorted(results, key=lambda x: x["name"])


def get_milestones_for_project(project_id):
    """
    Return all milestones related to given project.
    """
    query = Milestone.query.filter_by(project_id=project_id)
    return [milestone.present() for milestone in query.all()]


def get_production_schedule_version_raw(production_schedule_version_id):
    """
    Get production schedule version matching given id.
    """
    try:
        production_schedule_version = ProductionScheduleVersion.get(
            production_schedule_version_id
        )
    except StatementError:
        raise ProductionScheduleVersionNotFoundException

    if production_schedule_version is None:
        raise ProductionScheduleVersionNotFoundException

    return production_schedule_version


@cache.memoize_function(120)
def get_production_schedule_version(
    production_schedule_version_id, relations=False
):
    """
    Get production schedule version matching given id and serialize it.
    """
    return get_production_schedule_version_raw(
        production_schedule_version_id
    ).serialize(relations=relations)


def get_production_schedule_version_task_links(
    production_schedule_version_id, task_type_id=None, relations=False
):
    """
    Get all task links for given production schedule version.
    """
    query = ProductionScheduleVersionTaskLink.query.filter_by(
        production_schedule_version_id=production_schedule_version_id
    )

    if task_type_id is not None:
        query = (
            query.join(Task)
            .join(TaskType)
            .filter(Task.task_type_id == task_type_id)
        )

    return fields.serialize_models(query.all(), relations=relations)


def update_production_schedule_version(production_schedule_version_id, data):
    """
    Update production schedule version with given id with data.
    """
    production_schedule_version = get_production_schedule_version_raw(
        production_schedule_version_id
    )

    production_schedule_version.update(data)
    clear_production_schedule_version_cache(production_schedule_version_id)
    events.emit(
        "production_schedule_version:update",
        {"production_schedule_version_id": production_schedule_version_id},
        project_id=str(production_schedule_version.project_id),
    )
    return production_schedule_version.serialize()


def set_production_schedule_version_task_links_from_production(
    production_schedule_version_id,
):
    """
    Set task links for given production schedule version from tasks in the
    production.
    """
    production_schedule_version = get_production_schedule_version(
        production_schedule_version_id
    )

    tasks = (
        db.session.query(Task)
        .filter(Task.project_id == production_schedule_version["project_id"])
        .all()
    )

    rows = [
        {
            "id": fields.gen_uuid(),
            "production_schedule_version_id": production_schedule_version_id,
            "task_id": task.id,
            "start_date": task.start_date,
            "due_date": task.due_date,
            "estimation": task.estimation,
        }
        for task in tasks
    ]
    insert_stmt = insert(ProductionScheduleVersionTaskLink).values(rows)
    insert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["production_schedule_version_id", "task_id"],
        set_={
            "start_date": insert_stmt.excluded.start_date,
            "due_date": insert_stmt.excluded.due_date,
            "estimation": insert_stmt.excluded.estimation,
        },
    ).returning(ProductionScheduleVersionTaskLink)

    results = db.session.execute(insert_stmt).scalars().all()

    tasks_map = {task.id: task for task in tasks}

    for task_link in results:
        task_link.assignees = tasks_map[task_link.task_id].assignees

    db.session.commit()

    return fields.serialize_models(results, relations=True)


def set_production_schedule_version_task_links_from_production_schedule_version(
    production_schedule_version_id, other_production_schedule_version_id
):
    """
    Set task links for given production schedule version from another.
    """

    other_links = (
        db.session.query(ProductionScheduleVersionTaskLink)
        .filter(
            ProductionScheduleVersionTaskLink.production_schedule_version_id
            == other_production_schedule_version_id
        )
        .all()
    )

    rows = [
        {
            "id": fields.gen_uuid(),
            "production_schedule_version_id": production_schedule_version_id,
            "task_id": links.task_id,
            "start_date": links.start_date,
            "due_date": links.due_date,
            "estimation": links.estimation,
        }
        for links in other_links
    ]

    insert_stmt = insert(ProductionScheduleVersionTaskLink).values(rows)
    insert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["production_schedule_version_id", "task_id"],
        set_={
            "start_date": insert_stmt.excluded.start_date,
            "due_date": insert_stmt.excluded.due_date,
            "estimation": insert_stmt.excluded.estimation,
        },
    ).returning(ProductionScheduleVersionTaskLink)

    results = db.session.execute(insert_stmt).scalars().all()

    tasks_map = {link.task_id: link for link in other_links}

    for task_link in results:
        task_link.assignees = tasks_map[task_link.task_id].assignees

    db.session.commit()

    update_production_schedule_version(
        production_schedule_version_id,
        {"production_schedule_from": other_production_schedule_version_id},
    )

    return fields.serialize_models(results, relations=True)


def apply_production_schedule_version_to_production(
    production_schedule_version_id,
):
    """
    Apply production schedule version to production.
    """

    stmt = (
        update(Task)
        .values(
            start_date=ProductionScheduleVersionTaskLink.start_date,
            due_date=ProductionScheduleVersionTaskLink.due_date,
            estimation=ProductionScheduleVersionTaskLink.estimation,
        )
        .where(Task.id == ProductionScheduleVersionTaskLink.task_id)
        .where(
            ProductionScheduleVersionTaskLink.production_schedule_version_id
            == production_schedule_version_id
        )
        .returning(Task)
    )

    results = db.session.execute(stmt).scalars().all()

    db.session.commit()

    for task in results:
        events.emit(
            "task:update",
            {"task_id": str(task.id)},
            project_id=str(task.project_id),
        )

    production_schedule_version = update_production_schedule_version(
        production_schedule_version_id, {"locked": True}
    )

    projects_service.update_project(
        production_schedule_version["project_id"],
        {"from_schedule_version_id": production_schedule_version_id},
    )

    return fields.serialize_models(results, relations=True)
