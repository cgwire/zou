from sqlalchemy import func, or_
from sqlalchemy.orm import aliased, subqueryload
from sqlalchemy.sql.expression import case

from zou.app import db
from zou.app.models.entity import Entity, EntityLink
from zou.app.models.entity_type import EntityType
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task, TaskPersonLink
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.services import (
    permissions_service,
    persons_service,
    projects_service,
    tasks_service,
    user_service,
)
from zou.app.utils import fields, permissions, query as query_utils


def get_person_done_tasks(person_id, projects):
    """
    Return all finished tasks that the given person did.
    """
    return get_person_tasks(person_id, projects, is_done=True)


def get_person_related_tasks(person_id, task_type_id, projects):
    """
    Return all tasks of the given task type on the entities where the
    given person has at least one assigned task, in the given projects.
    """
    person = Person.get(person_id)
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
    Return the tasks assigned to the given person in the given projects.
    If is_done is True, return the finished tasks, most recent end date
    first. Else, return the unfinished tasks.
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

    query_results = query.all()

    # Add the episodes linked to the assets
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
    scope=None,
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
    Return all tasks that wait for feedback in the given projects. Use a
    task filter, for example the filter that
    user_service.build_supervision_scope_filter returns. If a page number
    is given, return a pagination envelope instead of a plain list.
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

    if scope is not None:
        query = query.filter(scope)

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
        # match all the ways that a row gets its episode: the sequence
        # chain, an episode scoped entity (source_id) and a sequence level
        # task (parent_id)
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
    # the unpaginated legacy path never had an order: do not slow it with
    # a sort on six columns that its callers do not need
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


def get_person_tasks_to_check_filter_values(project_ids=None, scope=None):
    """
    Return the distinct IDs of these items in the tasks that wait for
    feedback in the given projects:
    - projects
    - task types
    - task statuses
    - episodes
    - assignees.
    Use a task filter, for example the filter that
    user_service.build_supervision_scope_filter returns.
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
        if scope is not None:
            query = query.filter(scope)
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
        # get the episode as the rows show it: the sequence chain, then
        # the entity source id, then the parent of a sequence level task
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
    Apply the scope and the filters of the open tasks pool. The listing,
    its stats and the burndown aggregates share this function. Thus the
    three queries always agree on the tasks in the pool.
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
    Return a page of the tasks of open projects that match the given
    filters. The page is a dict with data, stats, limit, is_more and page.
    If no task type is given, leave out the concept tasks.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

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
    Return the burndown aggregates for the tasks of open projects that
    match the given filters:
    - totals
    - schedule bounds
    - the number of tasks done each day.
    The schedule bounds come from the task dates. If the tasks have no
    dates, use the project dates. If a start date exists, fold the
    activity days before that window onto its first day. Activity days
    after the window extend it.
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

    # each bound uses the project dates separately, so the two raw values
    # can be in the wrong order: sort them before other code reads them
    # as a window
    schedule_start = first_start_date or first_project_start
    planning_dates = [
        date
        for date in (schedule_start, last_due_date or last_project_end)
        if date is not None
    ]
    # the fold needs a start date as an anchor. Else, for a pool with only
    # due dates, all the days of its activity go onto the due date
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
    Return the number of tasks, the number of done tasks, the estimation
    and the duration for each status in open projects. Calculate the
    totals for each project.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

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
    Fold the activity days before the schedule window onto its first day.
    Else, a task with an imported done date (1899-12-31 or similar) moves
    the start of the burndown window back to that date. Do not remove these
    days: their tasks count in the total. Without their done amount, the
    curve stays above zero.
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
    project_id,
    page=0,
    task_type_id=None,
    episode_id=None,
    only_assigned=False,
    limit=None,
    cursor_id=None,
):
    """
    Return all tasks of the given project. If only_assigned is True,
    return only the tasks assigned to the current user. Return all of them,
    a page of them, or the tasks after a cursor (see
    query_utils.get_paginated_results).
    """
    query = (
        # subqueryload: one query for all sizes. selectinload sends one IN
        # of 500 ids for each batch on large projects.
        Task.query.options(subqueryload(Task.assignees).load_only(Person.id))
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
        if not (only_assigned or permissions.has_admin_permissions()):
            query = query.join(Project).filter(
                user_service.build_related_projects_filter()
            )

    if only_assigned:
        query = query.filter(persons_service.build_assignee_filter())

    return query_utils.get_paginated_results(
        query, page, limit, relations=True, cursor_id=cursor_id
    )


def get_todos():
    """
    Return all unfinished tasks assigned to the current user.
    """
    current_user = persons_service.get_current_user()
    projects = user_service.related_projects()
    return get_person_tasks(current_user["id"], projects)


def get_done_tasks():
    """
    Return all finished tasks assigned to the current user in open
    projects.
    """
    current_user = persons_service.get_current_user()
    projects = user_service.related_projects()
    return get_person_done_tasks(current_user["id"], projects)


def _get_tasks_to_check_scope():
    """
    Return (allowed, project_ids, scope). The tasks-to-check queries use
    this tuple as their scope. It depends on the role of the current user
    in each project.
    """
    if permissions.has_admin_permissions():
        return True, None, None
    # Read the roles per project: the role on each project of the team.
    roles = user_service.get_team_project_roles()
    project_ids = [
        project_id
        for project_id, role in roles.items()
        if role in ("manager", "supervisor")
    ]
    # Allow a global manager or supervisor who is not on a team yet, with
    # an empty scope.
    if not project_ids and not (
        permissions.has_manager_permissions()
        or permissions.has_supervisor_permissions()
    ):
        return False, None, None
    department_ids = []
    if "supervisor" in roles.values():
        department_ids = persons_service.get_current_user(relations=True)[
            "departments"
        ]
    scope = user_service.build_supervision_scope_filter(roles, department_ids)
    return True, project_ids, scope


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
    Return all tasks that wait for feedback and that the current user
    supervises:
    - all tasks for an admin
    - all tasks of a managed project
    - the tasks of the departments of the user on a supervised project.
    If a page number is given, return a pagination envelope instead of a
    plain list.
    """
    allowed, project_ids, scope = _get_tasks_to_check_scope()
    if not allowed:
        # an empty project scope gives the same empty list or envelope
        # shape as the allowed path, clamping included
        project_ids, scope = [], None

    return get_person_tasks_to_check(
        project_ids,
        scope,
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
    Return the distinct filter values of the tasks that wait for feedback
    and that the current user supervises.
    """
    allowed, project_ids, scope = _get_tasks_to_check_scope()
    if not allowed:
        return {
            "project_ids": [],
            "task_type_ids": [],
            "task_status_ids": [],
            "episode_ids": [],
            "person_ids": [],
        }
    return get_person_tasks_to_check_filter_values(project_ids, scope)
