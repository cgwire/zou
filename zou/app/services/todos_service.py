from sqlalchemy import or_, func
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import case
from sqlalchemy.orm import aliased, selectinload

from zou.app import db
from zou.app.utils import fields, query as query_utils, permissions
from zou.app.models.entity import Entity, EntityLink
from zou.app.models.entity_type import EntityType
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task, TaskPersonLink
from zou.app.models.task_type import TaskType
from zou.app.models.task_status import TaskStatus
from zou.app.services import (
    persons_service,
    projects_service,
    permissions_service,
    user_service,
    tasks_service,
)


def get_person_done_tasks(person_id, projects):
    """
    Return all finished tasks performed by a person.
    """
    return get_person_tasks(person_id, projects, is_done=True)


def get_person_related_tasks(person_id, task_type_id):
    """
    Retrieve all tasks for given task types and to entiities
    that have at least one person assignation.
    """
    person = Person.get(person_id)
    projects = projects_service.open_projects()
    project_ids = [project["id"] for project in projects]

    entities = (
        Entity.query.join(Task, Entity.id == Task.entity_id)
        .filter(Task.assignees.contains(person))
        .filter(Entity.project_id.in_(project_ids))
    ).all()

    entity_ids = [entity.id for entity in entities]
    tasks = (
        Task.query.filter(Task.entity_id.in_(entity_ids)).filter(
            Task.task_type_id == task_type_id
        )
    ).all()

    return fields.serialize_models(tasks)


def get_person_tasks(person_id, projects, is_done=None):
    """
    Retrieve all tasks for given person and projects.
    """
    Person.get(person_id)
    project_ids = [project["id"] for project in projects]

    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    query = (
        Task.query.join(TaskPersonLink, Task.id == TaskPersonLink.task_id)
        .join(Project, Task.project_id == Project.id)
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
        .filter(TaskPersonLink.person_id == person_id)
        .filter(Project.id.in_(project_ids))
        .add_columns(
            Project.name,
            Project.has_avatar,
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.preview_file_id,
            EntityType.name,
            Entity.canceled,
            Entity.parent_id,
            Entity.source_id,
            Sequence.name,
            Episode.id,
            Episode.name,
            TaskType.name,
            TaskType.for_entity,
            TaskStatus.name,
            TaskType.color,
            TaskStatus.color,
            TaskStatus.short_name,
        )
    )

    if is_done:
        query = query.filter(TaskStatus.is_done == True).order_by(
            Task.end_date.desc(), TaskType.name, Entity.name
        )
    else:
        query = query.filter(TaskStatus.is_done == False)

    # Execute query once and reuse results
    query_results = query.all()

    # Add episodes linked to assets
    asset_ids = []
    for row in query_results:
        asset_ids.append(str(row[0].entity_id))

    cast_in_episode_ids = {}
    cast_in_episode_names = {}
    episode_links_query = (
        EntityLink.query.join(Episode, EntityLink.entity_in_id == Episode.id)
        .join(EntityType, EntityType.id == Episode.entity_type_id)
        .filter(EntityType.name == "Episode")
        .filter(EntityLink.entity_out_id.in_(asset_ids))
        .add_columns(Episode.id, Episode.name)
        .order_by(Episode.name)
    )
    for link, episode_id, episode_name in episode_links_query.all():
        asset_id = str(link.entity_out_id)
        if asset_id not in cast_in_episode_ids:
            cast_in_episode_ids[asset_id] = []
            cast_in_episode_names[asset_id] = []
        cast_in_episode_ids[asset_id].append(episode_id)
        cast_in_episode_names[asset_id].append(episode_name)

    # Build the result

    tasks = []
    for row in query_results:
        (
            task_dict,
            task,
            task_type_name,
            task_status_name,
            task_type_color,
            task_status_color,
            task_status_short_name,
        ) = tasks_service.resolve_episode_and_build_task_dict(*row)
        task_dict.update(
            {
                "task_estimation": task.estimation,
                "task_duration": task.duration,
                "task_start_date": fields.serialize_value(task.start_date),
                "task_due_date": fields.serialize_value(task.due_date),
                "task_type_name": task_type_name,
                "task_status_name": task_status_name,
                "task_type_color": task_type_color,
                "task_status_color": task_status_color,
                "task_status_short_name": task_status_short_name,
            }
        )

        if str(task.entity_id) in cast_in_episode_ids:
            task_dict["episode_ids"] = cast_in_episode_ids[str(task.entity_id)]
            task_dict["episode_names"] = cast_in_episode_names[
                str(task.entity_id)
            ]
        tasks.append(task_dict)

    if tasks:
        tasks_service.attach_assignee_ids(tasks)
    tasks_service.add_last_comments_to_tasks(tasks)
    return tasks


def get_person_tasks_to_check(
    project_ids=None,
    department_ids=None,
    project_id=None,
    task_type_id=None,
    task_status_id=None,
    person_id=None,
    episode_id=None,
    due_date_since=None,
    due_date_until=None,
    order_by=None,
    page=None,
    limit=100,
):
    """
    Retrieve all tasks requiring a feedback for given departments and projects.
    When a page number is given, return a pagination envelope instead of a
    bare list.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    query = (
        Task.query.join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .join(TaskType, TaskType.id == Task.task_type_id)
        .join(TaskStatus, TaskStatus.id == Task.task_status_id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
        .filter(TaskStatus.is_feedback_request)
        .add_columns(
            Project.name,
            Project.has_avatar,
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.preview_file_id,
            EntityType.name,
            Entity.canceled,
            Entity.parent_id,
            Entity.source_id,
            Sequence.name,
            Episode.id,
            Episode.name,
            TaskType.name,
            TaskType.for_entity,
            TaskStatus.name,
            TaskType.color,
            TaskStatus.color,
            TaskStatus.short_name,
        )
    )

    if project_ids is not None:
        query = query.filter(Project.id.in_(project_ids))
    else:
        query = query.filter(projects_service.build_open_project_filter())

    if department_ids:
        query = query.filter(TaskType.department_id.in_(department_ids))

    if project_id is not None:
        query = query.filter(Project.id == project_id)

    if task_type_id is not None:
        query = query.filter(TaskType.id == task_type_id)

    if task_status_id is not None:
        query = query.filter(TaskStatus.id == task_status_id)

    if person_id is not None:
        if person_id == "unassigned":
            query = query.filter(Task.assignees == None)
        else:
            query = query.filter(
                Task.assignees.any(Person.id.in_(person_id.split(",")))
            )

    if episode_id is not None:
        # match every way a row resolves its episode: the sequence chain,
        # an episode scoped entity (source_id) and a sequence level task
        # (parent_id)
        query = query.filter(
            or_(
                Episode.id == episode_id,
                Entity.source_id == episode_id,
                Entity.parent_id == episode_id,
            )
        )

    if due_date_since is not None:
        due_date_since = func.cast(due_date_since, Task.due_date.type)
        query = query.filter(Task.due_date >= due_date_since)

    if due_date_until is not None:
        due_date_until = func.cast(due_date_until, Task.due_date.type)
        query = query.filter(Task.due_date <= due_date_until)

    stats = None
    if page is not None:
        page = max(page, 1)
        limit = max(limit, 1)
        total, total_duration, total_estimation = query.with_entities(
            func.count(Task.id),
            func.sum(Task.duration),
            func.sum(Task.estimation),
        ).one()
        stats = {
            "total": total,
            "total_duration": total_duration or 0,
            "total_estimation": total_estimation or 0,
        }

    name_order = [
        Project.name,
        Episode.name,
        Sequence.name,
        EntityType.name,
        Entity.name,
        TaskType.name,
    ]
    order_columns = {
        "priority": [
            Task.priority.desc().nullslast(),
            Task.due_date.asc().nullslast(),
        ]
        + name_order,
        "due_date": [Task.due_date.asc().nullslast()] + name_order,
        "estimation": [Task.estimation.desc().nullslast()] + name_order,
        "entity_name": [
            Project.name,
            TaskType.name,
            Episode.name,
            Sequence.name,
            Entity.name,
        ],
    }
    # the unpaginated legacy path never had an ordering: do not tax it
    # with a six column sort its callers do not need
    if page is not None or order_by is not None:
        query = query.order_by(
            *order_columns.get(order_by, name_order), Task.id
        )

    if page is not None:
        query = query.offset((page - 1) * limit).limit(limit)

    tasks = []
    for row in query.all():
        (
            task_dict,
            task,
            task_type_name,
            task_status_name,
            task_type_color,
            task_status_color,
            task_status_short_name,
        ) = tasks_service.resolve_episode_and_build_task_dict(*row)
        task_dict.update(
            {
                "task_estimation": task.estimation,
                "task_duration": task.duration,
                "task_start_date": fields.serialize_value(task.start_date),
                "task_due_date": fields.serialize_value(task.due_date),
                "task_type_name": task_type_name,
                "task_status_name": task_status_name,
                "task_type_color": task_type_color,
                "task_status_color": task_status_color,
                "task_status_short_name": task_status_short_name,
            }
        )
        tasks.append(task_dict)

    if tasks:
        tasks_service.attach_assignee_ids(tasks)
    tasks_service.add_last_comments_to_tasks(tasks)

    if page is None:
        return tasks

    return {
        "data": tasks,
        "stats": stats,
        "page": page,
        "limit": limit,
        "is_more": page * limit < stats["total"],
    }


def get_person_tasks_to_check_filter_values(
    project_ids=None, department_ids=None
):
    """
    Return the distinct project, task type, task status, episode and
    assignee ids present in the tasks requiring a feedback for given
    departments and projects.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

    def scope_query(query):
        query = (
            query.join(Project, Project.id == Task.project_id)
            .join(TaskType, TaskType.id == Task.task_type_id)
            .join(TaskStatus, TaskStatus.id == Task.task_status_id)
            .filter(TaskStatus.is_feedback_request)
        )
        if project_ids is not None:
            query = query.filter(Project.id.in_(project_ids))
        else:
            query = query.filter(projects_service.build_open_project_filter())
        if department_ids:
            query = query.filter(TaskType.department_id.in_(department_ids))
        return query

    rows = scope_query(
        db.session.query(
            Task.project_id,
            Task.task_type_id,
            Task.task_status_id,
            Episode.id,
            Entity.source_id,
            Entity.parent_id,
            EntityType.name,
        )
        .select_from(Task)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
    ).distinct()

    persons = scope_query(
        db.session.query(TaskPersonLink.person_id)
        .select_from(Task)
        .join(Entity, Entity.id == Task.entity_id)
        .join(TaskPersonLink, TaskPersonLink.task_id == Task.id)
    ).distinct()

    values = {
        "project_ids": set(),
        "task_type_ids": set(),
        "task_status_ids": set(),
        "episode_ids": set(),
    }
    for (
        project_id,
        task_type_id,
        task_status_id,
        episode_id,
        source_id,
        parent_id,
        entity_type_name,
    ) in rows.all():
        values["project_ids"].add(project_id)
        values["task_type_ids"].add(task_type_id)
        values["task_status_ids"].add(task_status_id)
        # resolve the episode the way the rows display it: the sequence
        # chain, then the entity source id, then the parent of a
        # sequence level task
        if episode_id is None:
            episode_id = source_id
        if entity_type_name == "Sequence" and parent_id is not None:
            episode_id = parent_id
        if episode_id is not None:
            values["episode_ids"].add(episode_id)
    values["person_ids"] = {row[0] for row in persons.all()}

    return {
        key: sorted(str(value_id) for value_id in ids)
        for key, ids in values.items()
    }


def _apply_open_tasks_filters(query, filters):
    """
    Apply the open tasks pool scoping and filters. Shared by the listing,
    its stats and the burndown aggregates so the three queries always
    agree on which tasks are in the pool.
    """
    if (
        filters.project_id is not None
        and permissions_service.check_project_access(filters.project_id)
    ):
        query = query.filter(Project.id == filters.project_id)
    elif permissions.has_admin_permissions():
        query = query.filter(ProjectStatus.name == "Open")
    else:
        query = query.filter(user_service.build_related_projects_filter())

    if filters.task_type_id is not None:
        query = query.filter(TaskType.id == filters.task_type_id)
    else:
        query = query.filter(TaskType.for_entity != "Concept")

    if filters.task_status_id is not None:
        query = query.filter(TaskStatus.id == filters.task_status_id)

    if filters.person_id is not None:
        if filters.person_id == "unassigned":
            query = query.filter(Task.assignees == None)
        else:
            query = query.filter(
                Task.assignees.any(Person.id.in_(filters.person_id.split(",")))
            )

    if filters.studio_id is not None:
        query = query.filter(Task.assignees.any(studio_id=filters.studio_id))

    if filters.department_id is not None:
        query = query.filter(
            Task.assignees.any(
                Person.departments.any(id=filters.department_id)
            )
        )

    if filters.start_date is not None:
        query = query.filter(
            Task.start_date
            >= func.cast(filters.start_date, Task.start_date.type)
        )

    if filters.due_date is not None:
        query = query.filter(
            Task.due_date <= func.cast(filters.due_date, Task.due_date.type)
        )

    if filters.priority is not None:
        query = query.filter(TaskType.priority == filters.priority)

    return query


def get_open_tasks(filters, order_by=None, limit=200, page=None):
    """
    Return all tasks matching given filters from open projects.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

    from zou.app import db

    query_stats = (
        db.session.query(
            func.count().label("amount"),
            func.sum(Task.duration).label("total_duration"),
            func.sum(Task.estimation).label("total_estimation"),
        )
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
    )
    query = (
        Task.query.join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
        .add_columns(
            Project.name,
            Project.has_avatar,
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.preview_file_id,
            EntityType.name,
            Entity.canceled,
            Entity.parent_id,
            Entity.source_id,
            Sequence.name,
            Episode.id,
            Episode.name,
            TaskType.name,
            TaskType.for_entity,
            TaskStatus.name,
            TaskType.color,
            TaskStatus.color,
            TaskStatus.short_name,
        )
    ).order_by(
        Project.name,
        Episode.name,
        Sequence.name,
        EntityType.name,
        Entity.name,
        TaskType.name,
    )

    query = _apply_open_tasks_filters(query, filters)
    query_stats = _apply_open_tasks_filters(query_stats, filters)

    limit = max(limit, 1)
    if page is not None and int(page) > 0:
        query = query.offset((page - 1) * limit)

    if order_by is not None:
        query = query.order_by(order_by)

    query_stats_status = query_stats.group_by(TaskStatus.id).add_columns(
        TaskStatus.id
    )

    tasks = []

    for row in query.limit(limit).all():
        (
            task_dict,
            task,
            task_type_name,
            task_status_name,
            task_type_color,
            task_status_color,
            task_status_short_name,
        ) = tasks_service.resolve_episode_and_build_task_dict(*row)
        task_dict.update(
            {
                "estimation": task.estimation,
                "duration": task.duration,
                "start_date": fields.serialize_value(task.start_date),
                "due_date": fields.serialize_value(task.due_date),
                "done_date": fields.serialize_value(task.done_date),
                "type_name": task_type_name,
                "status_name": task_status_name,
                "type_color": task_type_color,
                "status_color": task_status_color,
                "status_short_name": task_status_short_name,
            }
        )
        tasks.append(task_dict)

    if tasks:
        tasks_service.attach_assignee_ids(tasks)

    result = {
        "data": [],
        "stats": {
            "total_duration": 0,
            "total_estimation": 0,
            "total": 0,
            "status": [],
        },
        "limit": limit,
        "is_more": False,
        "page": page or 1,
    }

    if len(tasks) > 0:
        count = query.count()
        stats = query_stats.one()
        stats_status = query_stats_status.all()
        statuses_stats = [
            {"task_status_id": stat.id, "amount": stat.amount}
            for stat in stats_status
        ]

        result = {
            "data": tasks,
            "stats": {
                "total_duration": stats.total_duration,
                "total_estimation": stats.total_estimation,
                "total": count,
                "status": statuses_stats,
            },
            "limit": limit,
            "is_more": (page or 1) * limit < count,
            "page": page or 1,
        }
    return result


def get_open_tasks_burndown(filters):
    """
    Return burndown aggregates for tasks matching given filters from open
    projects: totals, schedule bounds and the amount of tasks done per day.
    Schedule bounds come from the task dates and fall back to the
    project dates when the tasks carry none. Activity days preceding that
    window are folded onto its first day, as long as a start date exists
    to anchor them, late ones extend it.
    """
    query = (
        db.session.query(
            Task.id,
            Task.estimation,
            Task.start_date,
            Task.due_date,
            Task.done_date,
            Project.start_date.label("project_start_date"),
            Project.end_date.label("project_end_date"),
        )
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
    )

    query = _apply_open_tasks_filters(query, filters)

    tasks = query.subquery()

    (
        total,
        total_estimation,
        first_start_date,
        last_due_date,
        first_project_start,
        last_project_end,
    ) = db.session.query(
        func.count(),
        func.sum(tasks.c.estimation),
        func.cast(func.min(tasks.c.start_date), db.Date),
        func.cast(func.max(tasks.c.due_date), db.Date),
        func.min(tasks.c.project_start_date),
        func.max(tasks.c.project_end_date),
    ).one()

    done_day = func.cast(tasks.c.done_date, db.Date)
    done_rows = (
        db.session.query(done_day, func.count(), func.sum(tasks.c.estimation))
        .filter(tasks.c.done_date != None)
        .group_by(done_day)
        .order_by(done_day)
        .all()
    )

    # each bound falls back to the project dates independently, so the
    # two raw values can come out inverted: order them before anything
    # reads them as a window
    schedule_start = first_start_date or first_project_start
    planning_dates = [
        date
        for date in (schedule_start, last_due_date or last_project_end)
        if date is not None
    ]
    # the fold needs a start date to anchor on: a pool carrying due dates
    # alone would otherwise see every day of its activity collapse onto
    # the due date
    window_start = min(planning_dates) if schedule_start is not None else None

    done_rows = _fold_done_rows_before(done_rows, window_start)

    bounds = list(planning_dates)
    if done_rows:
        bounds += [done_rows[0][0], done_rows[-1][0]]

    return {
        "total": total,
        "total_estimation": total_estimation or 0,
        "start_date": fields.serialize_value(min(bounds) if bounds else None),
        "end_date": fields.serialize_value(max(bounds) if bounds else None),
        "done_by_day": [
            {
                "date": fields.serialize_value(day),
                "done": done,
                "done_estimation": done_estimation or 0,
            }
            for day, done, done_estimation in done_rows
        ],
    }


def get_open_tasks_stats():
    """
    Return the amount of tasks, done tasks, estimation, and duration for each
    status in open projects. Aggregate the amounts for each project.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

    from zou.app import db

    query_stats = (
        db.session.query(
            func.count().label("amount"),
            func.count(case({TaskStatus.is_done: Task.id})).label(
                "amount_done"
            ),
            func.sum(Task.duration).label("total_duration"),
            func.sum(Task.estimation).label("total_estimation"),
        )
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .filter(TaskType.for_entity != "Concept")
        .group_by(Project.id, TaskType.id, TaskStatus.id)
        .add_columns(
            Project.id.label("project_id"),
            TaskType.id.label("task_type_id"),
            TaskStatus.id.label("task_status_id"),
        )
    )

    if permissions.has_admin_permissions():
        query_stats = query_stats.filter(ProjectStatus.name == "Open")
    else:
        query_stats = query_stats.filter(
            user_service.build_related_projects_filter()
        )

    stats_status = query_stats.all()

    statuses_stats = [
        {
            "task_status_id": stat.task_status_id,
            "task_type_id": stat.task_type_id,
            "project_id": stat.project_id,
            "amount": stat.amount,
            "amount_done": stat.amount_done,
            "total_duration": stat.total_duration,
            "total_estimation": stat.total_estimation,
        }
        for stat in stats_status
    ]

    stats_map = {}
    for stat in statuses_stats:
        project_id = stat["project_id"]
        if project_id not in stats_map:
            stats_map[project_id] = {
                "amount": 0,
                "amount_done": 0,
                "total_duration": 0,
                "total_estimation": 0,
                "task_types": [],
            }
        project_stats = stats_map[project_id]
        project_stats["amount"] += stat["amount"]
        project_stats["amount_done"] += stat["amount_done"]
        project_stats["total_duration"] += stat["total_duration"]
        project_stats["total_estimation"] += stat["total_estimation"]
        project_stats["task_types"].append(stat)

    return stats_map


def _fold_done_rows_before(done_rows, window_start):
    """
    Fold the activity days preceding the schedule window onto its first
    day. A task carrying an imported done date (1899-12-31 and the like)
    would otherwise drag the whole burndown window back to that date.
    Folding rather than dropping them: those tasks count in the total, so
    losing their done amount would keep the curve above zero.
    """
    if window_start is None:
        return done_rows

    early = [row for row in done_rows if row[0] < window_start]
    if not early:
        return done_rows

    folded = early + [row for row in done_rows if row[0] == window_start]
    return [
        (
            window_start,
            sum(row[1] for row in folded),
            sum(row[2] or 0 for row in folded),
        )
    ] + [row for row in done_rows if row[0] > window_start]


def get_tasks_for_project(
    project_id, page=0, task_type_id=None, episode_id=None
):
    """
    Return all tasks for given project.
    """
    query = (
        Task.query.options(selectinload(Task.assignees).load_only(Person.id))
        .filter(Task.project_id == project_id)
        .order_by(Task.updated_at.desc())
    )
    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)
    if episode_id is not None:
        Sequence = aliased(Entity, name="sequence")
        query = (
            query.join(Entity, Entity.id == Task.entity_id)
            .join(Sequence, Sequence.id == Entity.parent_id)
            .filter(Sequence.parent_id == episode_id)
        )

        if permissions.has_vendor_permissions():
            query = query.filter(persons_service.build_assignee_filter())
        elif not permissions.has_admin_permissions():
            query = query.join(Project).filter(
                user_service.build_related_projects_filter()
            )

    return query_utils.get_paginated_results(query, page, relations=True)


def get_todos():
    """
    Get all unfinished tasks assigned to current user.
    """
    current_user = persons_service.get_current_user()
    projects = user_service.related_projects()
    return get_person_tasks(current_user["id"], projects)


def get_done_tasks():
    """
    Get all finished tasks assigned to current user for open projects.
    """
    current_user = persons_service.get_current_user()
    projects = user_service.related_projects()
    return get_person_done_tasks(current_user["id"], projects)


def _get_tasks_to_check_scope():
    """
    Return (allowed, project_ids, department_ids) used to scope the
    tasks-to-check queries depending on the current user role.
    """
    if permissions.has_admin_permissions():
        return True, None, None
    if permissions.has_manager_permissions():
        return (
            True,
            [project["id"] for project in user_service.related_projects()],
            None,
        )
    if permissions.has_supervisor_permissions():
        current_user = persons_service.get_current_user(relations=True)
        return (
            True,
            [project["id"] for project in user_service.related_projects()],
            current_user["departments"],
        )
    return False, None, None


def get_tasks_to_check(
    project_id=None,
    task_type_id=None,
    task_status_id=None,
    person_id=None,
    episode_id=None,
    due_date_since=None,
    due_date_until=None,
    order_by=None,
    page=None,
    limit=100,
):
    """
    Get all tasks waiting for feedback in the user department. When a page
    number is given, return a pagination envelope instead of a bare list.
    """
    allowed, project_ids, departments_ids = _get_tasks_to_check_scope()
    if not allowed:
        # an empty project scope yields the same empty list or envelope
        # shape as the allowed path, clamping included
        project_ids, departments_ids = [], None

    return get_person_tasks_to_check(
        project_ids,
        departments_ids,
        project_id=project_id,
        task_type_id=task_type_id,
        task_status_id=task_status_id,
        person_id=person_id,
        episode_id=episode_id,
        due_date_since=due_date_since,
        due_date_until=due_date_until,
        order_by=order_by,
        page=page,
        limit=limit,
    )


def get_tasks_to_check_filter_values():
    """
    Return the distinct filter values available for the tasks waiting for
    feedback in the user department.
    """
    allowed, project_ids, departments_ids = _get_tasks_to_check_scope()
    if not allowed:
        return {
            "project_ids": [],
            "task_type_ids": [],
            "task_status_ids": [],
            "episode_ids": [],
            "person_ids": [],
        }
    return get_person_tasks_to_check_filter_values(
        project_ids, departments_ids
    )
