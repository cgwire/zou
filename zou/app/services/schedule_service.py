from datetime import date, timedelta

from sqlalchemy import Text, and_, cast, delete, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from zou.app import db
from zou.app.exceptions import (
    ProductionScheduleVersionNotFoundException,
    WrongParameterException,
)
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.milestone import Milestone
from zou.app.models.person import Person
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
    ProductionScheduleVersionTaskLinkPersonLink,
)
from zou.app.models.project import Project
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.task import Task, TaskPersonLink
from zou.app.models.task_type import TaskType
from zou.app.services import (
    assets_service,
    base_service,
    edits_service,
    entity_types_service,
    projects_service,
    shots_service,
    tasks_service,
)
from zou.app.utils import cache, events, fields


def clear_production_schedule_version_cache(production_schedule_version_id):
    """
    Remove all the memoized dicts of the given production schedule
    version.
    """
    cache.cache.delete_memoized(
        get_production_schedule_version, production_schedule_version_id
    )
    cache.cache.delete_memoized(
        get_production_schedule_version, production_schedule_version_id, True
    )


def get_schedule_items(project_id):
    """
    Return all schedule items of the given project (mainly for
    synchronization).
    """
    schedule_items = ScheduleItem.query.filter_by(project_id=project_id).all()
    return fields.serialize_list(schedule_items)


def get_task_types_schedule_items(project_id):
    """
    Return the schedule items of the task types that have tasks in the
    given project. If one of these task types has no schedule item, create
    one. If the project settings list task types, leave out the other task
    types. A task type that you remove from the settings keeps its tasks
    and its schedule item. The item comes back if you add the task type
    again.
    """
    project_task_type_ids = {
        str(task_type.id)
        for task_type in projects_service.get_project_task_types_raw(
            project_id
        )
    }
    task_types = tasks_service.get_task_types_for_project(project_id)
    task_types = [
        task_type
        for task_type in task_types
        if task_type["for_entity"]
        in ["Asset", "Shot", "Sequence", "Episode", "Edit"]
        and (
            not project_task_type_ids
            or task_type["id"] in project_task_type_ids
        )
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
    left_out_schedule_items = {
        schedule_item
        for schedule_item in schedule_items
        if schedule_item.task_type_id is not None
        and str(schedule_item.task_type_id) not in task_type_map
    }

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
        schedule_items.union(new_schedule_items) - left_out_schedule_items
    )
    return sorted(
        [schedule_item.present() for schedule_item in schedule_items],
        key=lambda x: x["start_date"],
    )


def _entity_schedule_items_query(project_id, task_type_id, entity_type_id):
    """
    Return the base query for the schedule items linked to the entities of
    the given type, in the given project and for the given task type.
    """
    return (
        ScheduleItem.query.join(Entity, ScheduleItem.object_id == Entity.id)
        .filter(ScheduleItem.project_id == project_id)
        .filter(Entity.entity_type_id == entity_type_id)
        .filter(ScheduleItem.task_type_id == task_type_id)
    )


def get_asset_types_schedule_items(project_id, task_type_id, episode_id=None):
    """
    Return the schedule items of all asset types of the given project. If
    an asset type has no schedule item, create one. If an episode is given,
    return only the asset types that have assets in that episode.
    """
    if episode_id is not None:
        asset_types = assets_service.get_asset_types_for_episode(
            project_id, episode_id
        )
    else:
        asset_types = assets_service.get_asset_types_for_project(project_id)
    asset_type_map = base_service.get_model_map_from_array(asset_types)

    query = (
        ScheduleItem.query.join(
            EntityType, ScheduleItem.object_id == EntityType.id
        )
        .filter(ScheduleItem.project_id == project_id)
        .filter(ScheduleItem.task_type_id == task_type_id)
    )
    if episode_id is not None:
        query = query.filter(
            ScheduleItem.object_id.in_(list(asset_type_map.keys()))
        )
    existing_schedule_items = set(query.all())

    return get_entity_schedule_items(
        project_id,
        task_type_id,
        asset_types,
        asset_type_map,
        existing_schedule_items,
    )


def get_episodes_schedule_items(project_id, task_type_id, episode_id=None):
    """
    Return the schedule items of all episodes of the given project. If an
    episode has no schedule item, create one. If an episode is given,
    return only that episode.
    """
    episode_type = entity_types_service.get_episode_type()
    episodes = shots_service.get_episodes_for_project(project_id)
    if episode_id is not None:
        episodes = [
            episode for episode in episodes if episode["id"] == str(episode_id)
        ]
    episodes_map = base_service.get_model_map_from_array(episodes)

    query = _entity_schedule_items_query(
        project_id, task_type_id, episode_type["id"]
    )
    if episode_id is not None:
        query = query.filter(ScheduleItem.object_id == episode_id)
    existing_schedule_items = set(query.all())

    return get_entity_schedule_items(
        project_id,
        task_type_id,
        episodes,
        episodes_map,
        existing_schedule_items,
    )


def get_sequences_schedule_items(project_id, task_type_id, episode_id=None):
    """
    Return the schedule items of all sequences of the given project. If a
    sequence has no schedule item, create one. If an episode is given,
    return only the sequences of that episode.
    """
    sequences = shots_service.get_sequences_for_project(project_id)
    if episode_id is not None:
        sequences = [
            sequence
            for sequence in sequences
            if sequence["parent_id"] == str(episode_id)
        ]
    sequence_map = base_service.get_model_map_from_array(sequences)
    sequence_type = entity_types_service.get_sequence_type()

    query = _entity_schedule_items_query(
        project_id, task_type_id, sequence_type["id"]
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


def get_edits_schedule_items(project_id, task_type_id, episode_id=None):
    """
    Return the schedule items of all edits of the given project. If an
    edit has no schedule item, create one. Ignore the canceled edits. If an
    episode is given, return only the edits of that episode.
    """
    edits = edits_service.get_edits_for_project(project_id)
    edits = [edit for edit in edits if not edit["canceled"]]
    if episode_id is not None:
        edits = [
            edit for edit in edits if edit["parent_id"] == str(episode_id)
        ]
    edit_map = base_service.get_model_map_from_array(edits)
    edit_type = entity_types_service.get_edit_type()

    query = _entity_schedule_items_query(
        project_id, task_type_id, edit_type["id"]
    )
    if episode_id is not None:
        query = query.filter(Entity.parent_id == episode_id)
    existing_schedule_items = set(query.all())

    return get_entity_schedule_items(
        project_id,
        task_type_id,
        edits,
        edit_map,
        existing_schedule_items,
    )


def _is_untouched(schedule_item):
    """
    Return True if nobody moved the schedule item after its creation. On
    creation, two separate clock reads set the two timestamps. They are one
    second apart at most.
    """
    return (
        schedule_item.updated_at is None
        or schedule_item.updated_at - schedule_item.created_at
        < timedelta(seconds=1)
    )


def get_entity_schedule_items(
    project_id, task_type_id, to_create, to_create_map, existing_schedule_items
):
    """
    Complete the existing schedule items with one item for each entity
    that has no item yet. Remove the items whose entity is not there
    anymore. Return all the items, sorted by entity name. An item that
    nobody moved yet, new or old, gets the dates of the bar of its task
    type. Thus the schedule shows it where the task type is planned. If
    there is no such bar, a new item starts today and ends tomorrow.
    """
    schedule_item_map = {
        str(schedule_item.object_id): schedule_item
        for schedule_item in existing_schedule_items
    }
    task_type_schedule_item = ScheduleItem.get_by(
        project_id=project_id, task_type_id=task_type_id, object_id=None
    )
    if task_type_schedule_item is not None:
        start_date = task_type_schedule_item.start_date
        end_date = task_type_schedule_item.end_date
    else:
        start_date = date.today()
        end_date = date.today() + timedelta(days=1)

    new_schedule_items = set()
    left_out_schedule_items = {
        schedule_item
        for schedule_item in existing_schedule_items
        if schedule_item.object_id is not None
        and str(schedule_item.object_id) not in to_create_map
    }

    for entity in to_create:
        if entity["id"] not in schedule_item_map:
            new_schedule_item = ScheduleItem.create(
                project_id=project_id,
                start_date=start_date,
                end_date=end_date,
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
        - left_out_schedule_items
    )

    results = []
    for schedule_item in schedule_items:
        result = schedule_item.present()
        result["name"] = to_create_map[result["object_id"]]["name"]
        if task_type_schedule_item is not None and _is_untouched(
            schedule_item
        ):
            result["start_date"] = start_date.isoformat()
            result["end_date"] = end_date.isoformat()
        results.append(result)

    return sorted(results, key=lambda x: x["name"])


def get_milestones_for_project(project_id):
    """
    Return all milestones of the given project.
    """
    query = Milestone.query.filter_by(project_id=project_id)
    return [milestone.present() for milestone in query.all()]


def get_production_schedule_version_raw(production_schedule_version_id):
    """
    Return the production schedule version that has the given ID as an
    active record.
    """
    return base_service.get_instance(
        ProductionScheduleVersion,
        production_schedule_version_id,
        ProductionScheduleVersionNotFoundException,
    )


@cache.memoize_function(120)
def get_production_schedule_version(
    production_schedule_version_id, relations=False
):
    """
    Return the production schedule version that has the given ID as a
    dict.
    """
    return get_production_schedule_version_raw(
        production_schedule_version_id
    ).serialize(relations=relations)


def get_production_schedule_version_task_links(
    production_schedule_version_id, task_type_id=None, relations=False
):
    """
    Return all task links of the given production schedule version.
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


def filter_version_task_links_by_project(query, project_id):
    """
    Return the given production schedule version task link query limited to
    the task links of the versions of the given project.
    """
    return query.join(
        ProductionScheduleVersion,
        ProductionScheduleVersion.id
        == ProductionScheduleVersionTaskLink.production_schedule_version_id,
    ).filter(ProductionScheduleVersion.project_id == project_id)


def detach_production_schedule_version(production_schedule_version_id):
    """
    Clear the references to the given production schedule version in
    other rows and in their memoized copies. Do this before you delete the
    version. These rows are the versions copied from it and the project
    that it was applied to.
    """
    derived_ids = [
        str(row.id)
        for row in ProductionScheduleVersion.query.with_entities(
            ProductionScheduleVersion.id
        )
        .filter_by(production_schedule_from=production_schedule_version_id)
        .all()
    ]
    if derived_ids:
        ProductionScheduleVersion.query.filter(
            ProductionScheduleVersion.id.in_(derived_ids)
        ).update({"production_schedule_from": None}, synchronize_session=False)
        db.session.commit()
        for derived_id in derived_ids:
            clear_production_schedule_version_cache(derived_id)

    project_ids = [
        str(row.id)
        for row in Project.query.with_entities(Project.id)
        .filter_by(from_schedule_version_id=production_schedule_version_id)
        .all()
    ]
    for project_id in project_ids:
        projects_service.update_project(
            project_id, {"from_schedule_version_id": None}
        )


def update_production_schedule_version(production_schedule_version_id, data):
    """
    Update the production schedule version that has the given ID with the
    given data.
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


def _generate_task_link_id():
    """
    Return a UUID expression for each row of the INSERT ... SELECT copies.
    gen_random_uuid() is a core built-in only from PostgreSQL 13, and the
    CI matrix still covers PostgreSQL 12. If we use a Python-side default
    (fields.gen_uuid), Python evaluates it one time for each from_select
    batch. Then all rows get the same primary key. md5(text) is a core
    function in all the PostgreSQL versions that we support. On
    random() || clock_timestamp(), it gives a different uuid for each
    row.
    """
    return cast(
        func.md5(
            func.concat(
                cast(func.random(), Text),
                cast(func.clock_timestamp(), Text),
            )
        ),
        ProductionScheduleVersionTaskLink.id.type,
    )


def _upsert_task_links_from_select(source_select):
    """
    Upsert the task links of the target version from a select. The select
    gives these columns, in this order:
    - the generated id
    - the ID of the target production schedule version
    - the task ID
    - the copied start_date, due_date and estimation.
    The full copy runs in the database (INSERT ... SELECT). Thus it scales
    to productions with tens of thousands of tasks, and it does not load
    them into Python. Return the number of copied task links, from the
    RETURNING rows of the statement. rowcount is not reliable for
    INSERT ... SELECT.
    """
    tl = ProductionScheduleVersionTaskLink
    insert_stmt = insert(tl).from_select(
        [
            tl.id,
            tl.production_schedule_version_id,
            tl.task_id,
            tl.start_date,
            tl.due_date,
            tl.estimation,
        ],
        source_select,
    )
    insert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["production_schedule_version_id", "task_id"],
        set_={
            "start_date": insert_stmt.excluded.start_date,
            "due_date": insert_stmt.excluded.due_date,
            "estimation": insert_stmt.excluded.estimation,
        },
    ).returning(tl.id)
    result = db.session.execute(insert_stmt)
    return len(result.all())


def _replace_task_link_assignees(refreshed_link_ids, person_source):
    """
    Refresh the assignees of the task links that refreshed_link_ids
    selects (a select of task link IDs). Use the rows from person_source, a
    select that gives (task_link_id, person_id). The delete applies only to
    the refreshed links. Thus the task links that the copy did not change
    keep their assignees. This runs in the database, so the cost stays low
    for all numbers of assignees.
    """
    pl = ProductionScheduleVersionTaskLinkPersonLink
    db.session.execute(
        delete(pl).where(
            pl.production_schedule_version_task_link_id.in_(refreshed_link_ids)
        )
    )
    db.session.execute(
        insert(pl)
        .from_select(
            [pl.production_schedule_version_task_link_id, pl.person_id],
            person_source,
        )
        .on_conflict_do_nothing()
    )


def _build_task_links_summary(task_link_count):
    """
    Return a small response for the set-task-links actions. The clients
    ignore the payload. Thus do not serialize the task links (there can be
    tens of thousands). Give only the number of copied links.
    """
    return {"success": True, "task_link_count": task_link_count}


def set_production_schedule_version_task_links_from_production(
    production_schedule_version_id,
):
    """
    Set the task links of the given production schedule version from the
    tasks of the production. Return a summary with the number of copied
    links.
    """
    production_schedule_version = get_production_schedule_version(
        production_schedule_version_id
    )

    tl = ProductionScheduleVersionTaskLink
    copied_count = _upsert_task_links_from_select(
        select(
            _generate_task_link_id(),
            literal(
                production_schedule_version_id,
                tl.production_schedule_version_id.type,
            ),
            Task.id,
            Task.start_date,
            Task.due_date,
            Task.estimation,
        ).where(Task.project_id == production_schedule_version["project_id"])
    )

    # All project tasks are copy sources, so refresh all target links.
    _replace_task_link_assignees(
        select(tl.id).where(
            tl.production_schedule_version_id == production_schedule_version_id
        ),
        select(tl.id, TaskPersonLink.person_id)
        .join(TaskPersonLink, TaskPersonLink.task_id == tl.task_id)
        .where(
            tl.production_schedule_version_id == production_schedule_version_id
        ),
    )

    db.session.commit()

    return _build_task_links_summary(copied_count)


def set_production_schedule_version_task_links_from_production_schedule_version(
    production_schedule_version_id, other_production_schedule_version_id
):
    """
    Set the task links of the given production schedule version from
    another version. Record the source version in production_schedule_from.
    Return a summary with the number of copied links. If the two versions
    are the same, raise WrongParameterException.
    """
    if production_schedule_version_id == other_production_schedule_version_id:
        raise WrongParameterException(
            "A production schedule version cannot be copied onto itself."
        )

    tl = ProductionScheduleVersionTaskLink
    other_tl = aliased(ProductionScheduleVersionTaskLink)
    pl = ProductionScheduleVersionTaskLinkPersonLink

    copied_count = _upsert_task_links_from_select(
        select(
            _generate_task_link_id(),
            literal(
                production_schedule_version_id,
                tl.production_schedule_version_id.type,
            ),
            other_tl.task_id,
            other_tl.start_date,
            other_tl.due_date,
            other_tl.estimation,
        ).where(
            other_tl.production_schedule_version_id
            == other_production_schedule_version_id
        )
    )

    # Refresh only the links whose task exists in the source version. The
    # target links that are not in the source keep their assignees.
    source_task_ids = select(other_tl.task_id).where(
        other_tl.production_schedule_version_id
        == other_production_schedule_version_id
    )
    _replace_task_link_assignees(
        select(tl.id).where(
            tl.production_schedule_version_id
            == production_schedule_version_id,
            tl.task_id.in_(source_task_ids),
        ),
        select(tl.id, pl.person_id)
        .join(
            other_tl,
            and_(
                other_tl.task_id == tl.task_id,
                other_tl.production_schedule_version_id
                == other_production_schedule_version_id,
            ),
        )
        .join(pl, pl.production_schedule_version_task_link_id == other_tl.id)
        .where(
            tl.production_schedule_version_id == production_schedule_version_id
        ),
    )

    db.session.commit()

    update_production_schedule_version(
        production_schedule_version_id,
        {"production_schedule_from": other_production_schedule_version_id},
    )

    return _build_task_links_summary(copied_count)


def apply_production_schedule_version_to_production(
    production_schedule_version_id,
):
    """
    Apply the given production schedule version to the production:
    - copy the dates and estimations of its task links to the tasks
    - lock the version
    - mark the project as built from it.
    Emit a task:update event for each task.
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
        .returning(Task.id, Task.project_id)
    )

    updated_tasks = db.session.execute(stmt).all()

    db.session.commit()

    for task_id, project_id in updated_tasks:
        # A bulk UPDATE writes the dates and estimation, and the ORM does
        # not see it. Thus remove the memoized tasks manually. The event
        # below makes all clients get the tasks again at the same time.
        # Without this, they all keep the old dates in cache until the TTL
        # ends.
        tasks_service.clear_task_cache(str(task_id))
        events.emit(
            "task:update",
            {"task_id": str(task_id)},
            project_id=str(project_id),
        )

    production_schedule_version = update_production_schedule_version(
        production_schedule_version_id, {"locked": True}
    )

    projects_service.update_project(
        production_schedule_version["project_id"],
        {"from_schedule_version_id": production_schedule_version_id},
    )

    return {"success": True, "task_count": len(updated_tasks)}


def get_persons_tasks_dates(
    project_id=None, project_ids=None, busy_project_ids=None
):
    """
    For the schedule, return for each active person the first start date
    of all the tasks assigned to this person, and the last due date.

    Scoping (project_id has priority over project_ids):
    - If project_id is set, the lookup uses only that project. The function
      uses it directly, closed projects included. It does not intersect it
      with the list of open projects. Else, a closed project that the
      caller can access gives an empty result. The caller must check the
      access to it.
    - project_ids limits the lookup to a set of projects. Only None (not
      an empty list) starts the studio-wide default below. An empty list
      matches no project. Thus a manager with no project gets an empty
      result. Keep the guard as an `is None` identity test. Do not change
      it to `if not project_ids:`. Else, such a manager sees the
      studio-wide view.
    - busy_project_ids lists the projects that the caller must not see in
      detail. The tasks of these projects come back as anonymous
      busy_periods. These are merged date pairs with no production or task
      data. Thus a schedule can show that a person is busy and not show
      what the person works on. A person with only such tasks has null
      min_date / max_date.
    """
    if project_id is not None:
        # An explicit project with a checked access is the scope of the
        # lookup. This skips the default to open projects. Thus a closed
        # project that the caller can see does not give an empty result.
        project_ids = [project_id]
    elif project_ids is None:
        # Studio-wide default. This is the project-scoped helper, not
        # user_service.get_open_project_ids(), which gives only the projects
        # of the current user.
        project_ids = projects_service.open_project_ids()
    query = (
        Task.query.with_entities(
            Person.id, func.min(Task.start_date), func.max(Task.due_date)
        )
        .filter(Person.active)
        .filter(Task.project_id.in_(project_ids))
        .group_by(Person.id)
        .join(Task.assignees)
    )

    entries = {}
    for person_id, min_date, max_date in query.all():
        entries[str(person_id)] = {
            "person_id": str(person_id),
            "min_date": fields.serialize_value(min_date),
            "max_date": fields.serialize_value(max_date),
            "busy_periods": [],
        }

    if busy_project_ids:
        busy_query = (
            Task.query.with_entities(Person.id, Task.start_date, Task.due_date)
            .filter(Person.active)
            .filter(Task.project_id.in_(busy_project_ids))
            .filter(Task.start_date != None)
            .filter(Task.due_date != None)
            .join(Task.assignees)
        )
        intervals_by_person = {}
        for person_id, start_date, due_date in busy_query.all():
            intervals_by_person.setdefault(str(person_id), []).append(
                (start_date, due_date)
            )
        for person_id, intervals in intervals_by_person.items():
            if person_id not in entries:
                entries[person_id] = {
                    "person_id": person_id,
                    "min_date": None,
                    "max_date": None,
                    "busy_periods": [],
                }
            entries[person_id]["busy_periods"] = [
                {"start_date": str(start), "end_date": str(end)}
                for start, end in _merge_date_intervals(intervals)
            ]

    return list(entries.values())


def _merge_date_intervals(intervals):
    """
    Merge the overlapping (start, end) pairs into the smallest set of
    disjoint intervals. Thus the anonymous busy periods do not show the
    task count or how the work is divided.
    """
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]
