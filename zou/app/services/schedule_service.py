from datetime import date, timedelta
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased
from sqlalchemy import Text, and_, cast, delete, func, literal, select, update


from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.milestone import Milestone
from zou.app.models.project import Project
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.task import Task, TaskPersonLink
from zou.app.models.task_type import TaskType
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
    ProductionScheduleVersionTaskLinkPersonLink,
)
from zou.app.utils import events, fields, cache
from zou.app.services import (
    assets_service,
    base_service,
    edits_service,
    shots_service,
    tasks_service,
    projects_service,
    entity_types_service,
)
from zou.app import db

from zou.app.exceptions import (
    ProductionScheduleVersionNotFoundException,
    WrongParameterException,
)
from zou.app.models.person import Person


def clear_production_schedule_version_cache(production_schedule_version_id):
    """
    Drop every memoized serialization of given production schedule version.
    """
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
        if task_type["for_entity"]
        in ["Asset", "Shot", "Sequence", "Episode", "Edit"]
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
    schedule_item_to_remove = {
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
        schedule_items.union(new_schedule_items) - schedule_item_to_remove
    )
    return sorted(
        [schedule_item.present() for schedule_item in schedule_items],
        key=lambda x: x["start_date"],
    )


def _entity_schedule_items_query(project_id, task_type_id, entity_type_id):
    """
    Base query for the schedule items attached to the entities of given type,
    in given project and for given task type.
    """
    return (
        ScheduleItem.query.join(Entity, ScheduleItem.object_id == Entity.id)
        .filter(ScheduleItem.project_id == project_id)
        .filter(Entity.entity_type_id == entity_type_id)
        .filter(ScheduleItem.task_type_id == task_type_id)
    )


def get_asset_types_schedule_items(project_id, task_type_id, episode_id=None):
    """
    Return all asset type schedule items for given project. If no schedule item
    exists for a given asset type, it creates one. When an episode is given,
    results are restricted to the asset types having assets in that episode.
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
    Return all episode schedule items for given project. If no schedule item
    exists for a given episode, it creates one. When an episode is given,
    results are restricted to that episode.
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
    Return all sequence schedule items for given project. If no schedule item
    exists for a given sequence, it creates one. When an episode is given,
    results are restricted to the sequences of that episode.
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
    Return all edit schedule items for given project. If no schedule item
    exists for a given edit, it creates one. Canceled edits are ignored.
    When an episode is given, results are restricted to the edits of that
    episode.
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


def get_entity_schedule_items(
    project_id, task_type_id, to_create, to_create_map, existing_schedule_items
):
    """
    Complete the existing schedule items with one item per entity that has
    none yet, drop the ones whose entity is gone, and return the whole set
    sorted by entity name.
    """
    schedule_item_map = {
        str(schedule_item.object_id): schedule_item
        for schedule_item in existing_schedule_items
    }

    new_schedule_items = set()
    schedule_item_to_remove = {
        schedule_item
        for schedule_item in existing_schedule_items
        if schedule_item.object_id is not None
        and str(schedule_item.object_id) not in to_create_map
    }

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


def detach_production_schedule_version(production_schedule_version_id):
    """
    Clear the references other rows keep to given production schedule
    version before it is deleted, memoized copies included: the versions
    copied from it and the project it was applied to.
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


def _generate_task_link_id():
    """
    Per-row UUID expression for the INSERT ... SELECT copies. gen_random_uuid()
    is a core built-in only from PostgreSQL 13 (the CI matrix still covers
    PostgreSQL 12), and a Python-side default (fields.gen_uuid) is evaluated
    once per from_select batch, so every row would share the same primary key.
    md5(text) has been core since well before any PostgreSQL version we
    support, and applied to random() || clock_timestamp() it yields a
    distinct uuid per row.
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
    Upsert the target version task links from a select yielding, in order, the
    generated id, the target production schedule version id, the task id and
    the copied start_date, due_date and estimation. The whole copy runs in the
    database (INSERT ... SELECT), so it scales to productions with tens of
    thousands of tasks without loading them into Python. Returns the number
    of task links copied, taken from the statement RETURNING rows (rowcount
    is unreliable for INSERT ... SELECT).
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
    Refresh the assignees of the task links selected by refreshed_link_ids
    (a select of task link ids) with the rows from person_source, a select
    yielding (task_link_id, person_id). The delete is scoped to the refreshed
    links only, so task links left untouched by the copy keep their assignees.
    Runs in the database so it stays cheap whatever the number of assignees.
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
    Lightweight response for the set-task-links actions: the clients discard
    the payload, so avoid serializing the (possibly tens of thousands of) task
    links and just report the number of copied links.
    """
    return {"success": True, "task_link_count": task_link_count}


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

    # Every project task is a copy source, so all target links are refreshed.
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
    Set task links for given production schedule version from another.
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

    # Only the links whose task exists in the source version are refreshed;
    # target links absent from the source keep their assignees.
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
        .returning(Task.id, Task.project_id)
    )

    updated_tasks = db.session.execute(stmt).all()

    db.session.commit()

    for task_id, project_id in updated_tasks:
        # The dates and estimation are written by a bulk UPDATE that the ORM
        # never sees, so the memoized tasks must be dropped by hand. The event
        # below makes every client refetch at once: without this they would
        # all cache the pre-schedule dates for the rest of the TTL.
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
    For schedule usages, for each active person, it returns the first start
    date of all tasks of assigned to this person and the last end date.

    Scoping (project_id takes precedence over project_ids):
    - project_id, when set, scopes the lookup to that single project and
      nothing else. It is honoured directly -- including closed projects --
      instead of being intersected with the open-project list, otherwise a
      closed but legitimately accessible project would yield an empty result.
      The caller is responsible for checking access to it.
    - project_ids restricts the lookup to a set of projects. Only None (not an
      empty list) triggers the studio-wide fallback below. An empty list is
      honoured as-is and matches no project, which is how a manager with no
      project gets an empty result -- the guard must stay an `is None` identity
      test and never become `if not project_ids:`, otherwise such a manager
      would leak the studio-wide view.
    - busy_project_ids lists the projects the caller must not see in detail:
      tasks found there come back as anonymous busy_periods, merged date
      pairs carrying no production or task information, so a schedule can
      show that a person is taken without leaking what they work on. A
      person with only such tasks is listed with null
      min_date / max_date.
    """
    if project_id is not None:
        # An explicit, access-checked project scopes the lookup directly. This
        # short-circuits the open-project fallback so a closed project the
        # caller may legitimately see is not filtered out to an empty result.
        project_ids = [project_id]
    elif project_ids is None:
        # Studio-wide fallback. Note this is the project-scoped helper, not
        # user_service.get_open_project_ids() which is limited to the current
        # user's projects.
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
    Merge overlapping (start, end) pairs into the smallest set of disjoint
    intervals, so anonymous busy periods reveal neither the task count nor
    how the underlying work is split.
    """
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]
