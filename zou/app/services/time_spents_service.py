import collections
import datetime
from collections import defaultdict

from dateutil import relativedelta
from sqlalchemy import func
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import ObjectDeletedError, StaleDataError

from zou.app.exceptions import (
    TaskNotFoundException,
    TimeSpentNotFoundException,
    WrongDateFormatException,
)
from zou.app.models.day_off import DayOff
from zou.app.models.department import Department
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.models.time_spent import TimeSpent
from zou.app.services import (
    base_service,
    persons_service,
    projects_service,
    tasks_service,
)
from zou.app.utils import date_helpers, events, fields, query as query_utils


def _apply_time_spent_filters(
    query,
    person_id=None,
    project_id=None,
    department_ids=None,
    studio_id=None,
    scope=None,
):
    """
    Apply the scope filters that the yearly and monthly time spent queries
    share. project_id accepts a single ID or a list of IDs. scope is a task
    filter, for example the filter that
    user_service.build_supervision_scope_filter returns.
    """
    if person_id is not None:
        query = query.filter(TimeSpent.person_id == person_id)

    if project_id is not None or department_ids or scope is not None:
        query = query.join(Task)

    if project_id is not None:
        if isinstance(project_id, list):
            query = query.filter(Task.project_id.in_(project_id))
        else:
            query = query.filter(Task.project_id == project_id)

    if department_ids or scope is not None:
        query = query.join(TaskType)

    if department_ids:
        query = query.filter(TaskType.department_id.in_(department_ids))

    if scope is not None:
        query = query.filter(scope)

    if studio_id is not None:
        query = query.join(Person, Person.id == TimeSpent.person_id).filter(
            Person.studio_id == studio_id
        )

    return query


def _get_interval_time_spents(
    person_id, start, end, project_id=None, department_ids=None, scope=None
):
    """
    Return the time spents aggregated at task level for the given person, in
    the [start, end[ interval.
    """
    entries = get_person_time_spent_entries(
        person_id,
        TimeSpent.date >= func.cast(start, TimeSpent.date.type),
        TimeSpent.date < func.cast(end, TimeSpent.date.type),
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
    )
    return build_results(entries)


def get_time_spents_for_entity(entity_id):
    """
    Return all time spents related to the given entity.
    """
    query = (
        TimeSpent.query.join(Task)
        .filter(Task.entity_id == entity_id)
        .order_by(TimeSpent.date.desc())
    )
    return TimeSpent.serialize_list(query.all())


def get_open_projects_time_spents_query():
    """
    Return a query on the time spents of the open projects, joined with
    the names of their project, entity type, entity, task type and person.
    """
    return (
        TimeSpent.query.order_by(
            TimeSpent.date,
            Person.last_name,
            Project.name,
            EntityType.name,
            Entity.name,
        )
        .join(Task, TimeSpent.task_id == Task.id)
        .join(Entity, Task.entity_id == Entity.id)
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .join(Project, Task.project_id == Project.id)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(Person, TimeSpent.person_id == Person.id)
        .add_columns(Project.name)
        .add_columns(EntityType.name)
        .add_columns(Entity.id)
        .add_columns(Entity.name)
        .add_columns(TaskType.name)
        .add_columns(Person.first_name)
        .add_columns(Person.last_name)
        .filter(ProjectStatus.name.in_(("Active", "open", "Open")))
    )


def get_year_table(
    person_id=None,
    project_id=None,
    department_ids=None,
    scope=None,
    studio_id=None,
):
    """
    Return a table that gives the time spent by user and by year, for all
    years.
    """
    return get_yearly_table(
        None,
        detail_level="year",
        person_id=person_id,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
        studio_id=studio_id,
    )


def get_month_table(
    year,
    person_id=None,
    project_id=None,
    department_ids=None,
    scope=None,
    studio_id=None,
):
    """
    Return a table that gives the time spent by user and by month for the
    given year.
    """
    return get_yearly_table(
        year,
        person_id=person_id,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
        studio_id=studio_id,
    )


def get_week_table(
    year,
    person_id=None,
    project_id=None,
    department_ids=None,
    scope=None,
    studio_id=None,
):
    """
    Return a table that gives the time spent by user and by week for the
    given year.
    """
    return get_yearly_table(
        year,
        "week",
        person_id=person_id,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
        studio_id=studio_id,
    )


def get_day_table(
    year,
    month,
    person_id=None,
    project_id=None,
    department_ids=None,
    scope=None,
    studio_id=None,
):
    """
    Return a table that gives the time spent by user and by day for the given
    year and month.
    """
    time_spents = get_time_spents_for_month(
        year,
        month,
        person_id=person_id,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
        studio_id=studio_id,
    )
    return get_table_from_time_spents(time_spents, "day")


def get_yearly_table(
    year=None,
    detail_level="month",
    person_id=None,
    project_id=None,
    department_ids=None,
    scope=None,
    studio_id=None,
):
    """
    Return a table that gives the time spent by user and by year, month or
    week for the given year, or for all years if year is None. The
    *detail_level* argument selects the detail level.
    """
    time_spents = get_time_spents_for_year(
        year=year,
        person_id=person_id,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
        studio_id=studio_id,
    )
    return get_table_from_time_spents(time_spents, detail_level)


def get_time_spents_for_year(
    year=None,
    person_id=None,
    project_id=None,
    department_ids=None,
    scope=None,
    studio_id=None,
):
    """
    Return all time spents for the given year, or for all years if year is
    None.
    """
    query = TimeSpent.query

    if person_id is not None:
        query = query.filter(TimeSpent.person_id == person_id)

    if year is not None:
        query = query.filter(
            TimeSpent.date.between(
                datetime.datetime(int(year), 1, 1),
                datetime.datetime(int(year), 12, 31),
            )
        )

    query = _apply_time_spent_filters(
        query,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
        studio_id=studio_id,
    )
    return query.all()


def get_time_spents_for_month(
    year,
    month,
    person_id=None,
    project_id=None,
    department_ids=None,
    scope=None,
    studio_id=None,
):
    """
    Return all time spents for the given month. If the month is not between
    1 and 12, raise WrongDateFormatException.
    """
    month_int = int(month)
    if month_int < 1 or month_int > 12:
        raise WrongDateFormatException
    date = datetime.datetime(int(year), month_int, 1)
    next_month = date + relativedelta.relativedelta(months=1)
    query = TimeSpent.query.filter(TimeSpent.date >= date).filter(
        TimeSpent.date < next_month
    )

    query = _apply_time_spent_filters(
        query,
        person_id=person_id,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
        studio_id=studio_id,
    )
    return query.all()


def get_table_from_time_spents(time_spents, detail_level="month"):
    """
    Build a time spent table from the given time spents and the given level
    of detail (year, month, week or day).
    """
    result = {}
    for time_spent in time_spents:
        if detail_level == "week":
            unit = str(time_spent.date.isocalendar()[1])
        elif detail_level == "day":
            unit = str(time_spent.date.day)
        elif detail_level == "year":
            unit = str(time_spent.date.year)
        else:
            unit = str(time_spent.date.month)

        person_id = str(time_spent.person_id)
        if unit not in result:
            result[unit] = defaultdict(int)
        result[unit][person_id] += time_spent.duration
    return result


def get_time_spents(person_id, date=None, project_ids=None, scope=None):
    """
    Return the time spents for the given person and date, or for all dates if
    no date is given. The rows can be limited to some projects and to a task
    filter, for example the filter that
    user_service.build_supervision_scope_filter returns.
    """
    try:
        query = TimeSpent.query.filter_by(person_id=person_id)
        if date is not None:
            query = query.filter_by(date=func.cast(date, TimeSpent.date.type))

        if project_ids is not None or scope is not None:
            query = query.join(Task)

        if project_ids is not None:
            query = query.filter(Task.project_id.in_(project_ids))

        if scope is not None:
            query = query.join(TaskType).filter(scope)

        # Keep this inside the try: the query is lazy, thus a date that the
        # driver rejects raises here, not when the filters are added.
        time_spents = query.all()
    except DataError:
        raise WrongDateFormatException
    return fields.serialize_list(time_spents)


def get_time_spents_range(
    person_id,
    start_date,
    end_date,
    project_ids=None,
    scope=None,
):
    """
    Return the time spents for the person and date range, with the project
    and the task type of their task. The rows can be limited to some projects
    and to a task filter, for example the filter that
    user_service.build_supervision_scope_filter returns.
    """
    try:
        query = (
            TimeSpent.query.join(Task, Task.id == TimeSpent.task_id)
            .add_columns(Task.project_id, Task.task_type_id)
            .filter(TimeSpent.person_id == person_id)
            .filter(
                TimeSpent.date.between(
                    func.cast(start_date, TimeSpent.date.type),
                    func.cast(end_date, TimeSpent.date.type),
                )
            )
        )

        if project_ids is not None:
            query = query.filter(Task.project_id.in_(project_ids))

        if scope is not None:
            query = query.join(TaskType, TaskType.id == Task.task_type_id)
            query = query.filter(scope)

        rows = query.all()
    except DataError:
        raise WrongDateFormatException
    return [
        {
            **time_spent.serialize(),
            "project_id": str(project_id),
            "task_type_id": str(task_type_id),
        }
        for time_spent, project_id, task_type_id in rows
    ]


def get_time_spent(person_id, task_id, date):
    """
    Return the time spent for the given person, task and date.
    """
    try:
        time_spent = TimeSpent.query.filter_by(
            person_id=person_id,
            task_id=task_id,
            date=func.cast(date, TimeSpent.date.type),
        ).first()
    except DataError:
        raise WrongDateFormatException
    return time_spent.serialize() if time_spent is not None else None


def get_day_off(person_id, date):
    """
    Return the day off for the given person and date.
    """
    try:
        day_off = DayOff.get_by(
            func.cast(date, DayOff.date.type).between(
                DayOff.date, DayOff.end_date
            ),
            person_id=person_id,
        )
    except DataError:
        raise WrongDateFormatException
    return day_off.serialize() if day_off is not None else {}


def get_year_time_spents(
    person_id, year, project_id=None, department_ids=None, scope=None
):
    """
    Return the time spents aggregated at task level for the given person and
    year.
    """
    start, end = date_helpers.get_year_interval(year)
    return _get_interval_time_spents(
        person_id,
        start,
        end,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
    )


def get_month_time_spents(
    person_id, year, month, project_id=None, department_ids=None, scope=None
):
    """
    Return the time spents aggregated at task level for the given person and
    month.
    """
    start, end = date_helpers.get_month_interval(year, month)
    return _get_interval_time_spents(
        person_id,
        start,
        end,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
    )


def get_week_time_spents(
    person_id, year, week, project_id=None, department_ids=None, scope=None
):
    """
    Return the time spents aggregated at task level for the given person and
    week.
    """
    start, end = date_helpers.get_week_interval(year, week)
    return _get_interval_time_spents(
        person_id,
        start,
        end,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
    )


def get_day_time_spents(
    person_id,
    year,
    month,
    day,
    project_id=None,
    department_ids=None,
    scope=None,
):
    """
    Return the time spents aggregated at task level for the given person and
    day.
    """
    start, end = date_helpers.get_day_interval(year, month, day)
    return _get_interval_time_spents(
        person_id,
        start,
        end,
        project_id=project_id,
        department_ids=department_ids,
        scope=scope,
    )


def get_person_time_spent_entries(
    person_id, *args, project_id=None, department_ids=None, scope=None
):
    """
    Return the time spents aggregated at task level for the given person and
    query filter (args).
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    query = (
        Task.query.with_entities(Task.id, Task.task_type_id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(TimeSpent)
        .join(EntityType)
        .group_by(
            Task.id,
            Task.task_type_id,
            Project.id,
            Project.name,
            Entity.name,
            EntityType.name,
            Sequence.name,
            Episode.name,
        )
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
        .filter(TimeSpent.person_id == person_id)
        .add_columns(
            Project.id,
            Project.name,
            Entity.name,
            EntityType.name,
            Sequence.name,
            Episode.name,
            func.sum(TimeSpent.duration),
        )
    )

    if project_id is not None:
        if isinstance(project_id, list):
            query = query.filter(Task.project_id.in_(project_id))
        else:
            query = query.filter(Task.project_id == project_id)

    if department_ids or scope is not None:
        query = query.join(TaskType, TaskType.id == Task.task_type_id)

    if department_ids:
        query = query.filter(TaskType.department_id.in_(department_ids))

    if scope is not None:
        query = query.filter(scope)

    for arg in args:
        query = query.filter(arg)

    return query.all()


def build_results(entries):
    """
    Build the results with the data necessary to build a time sheet from the
    given entries (tasks and the aggregate of the time spent durations).
    """
    result = []
    for (
        task_id,
        task_type_id,
        project_id,
        project_name,
        entity_name,
        entity_type_name,
        sequence_name,
        episode_name,
        duration,
    ) in entries:
        result.append(
            {
                "task_id": str(task_id),
                "task_type_id": str(task_type_id),
                "project_id": str(project_id),
                "project_name": project_name,
                "entity_name": entity_name,
                "entity_type_name": entity_type_name,
                "sequence_name": sequence_name,
                "episode_name": episode_name,
                "duration": duration,
            }
        )
    return result


def _last_day_of(interval):
    """
    Return the given interval with the last day of the period as its end.
    The interval helpers end on the first day of the next period, but
    get_day_offs_between includes its end day. It must include it, because
    the overlap check gives it the last day of a day off. Thus, period
    listings give the last day of their period, and a period does not
    include the first day of the next period.
    """
    start, end = interval
    return start, end - datetime.timedelta(days=1)


def get_day_offs_for_month(year, month, person_ids=None):
    """
    Return all day off entries for the given year and month. If persons are
    given, return only the entries of these persons.
    """
    start, end = _last_day_of(date_helpers.get_month_interval(year, month))
    return get_day_offs_between(start, end, person_ids=person_ids)


def get_day_offs_for_year(year, person_ids=None):
    """
    Return all day off entries for the given year. If persons are given,
    return only the entries of these persons.
    """
    start, end = _last_day_of(date_helpers.get_year_interval(year))
    return get_day_offs_between(start, end, person_ids=person_ids)


def get_person_day_offs_for_week(person_id, year, week):
    """
    Return all day off entries for the given person, year and week.
    """
    start, end = _last_day_of(date_helpers.get_week_interval(year, week))
    return get_day_offs_between(start, end, person_id=person_id)


def get_person_day_offs_for_month(person_id, year, month):
    """
    Return all day off entries for the given person, year and month.
    """
    start, end = _last_day_of(date_helpers.get_month_interval(year, month))
    return get_day_offs_between(start, end, person_id=person_id)


def get_person_day_offs_for_year(person_id, year):
    """
    Return all day off entries for the given person and year.
    """
    start, end = _last_day_of(date_helpers.get_year_interval(year))
    return get_day_offs_between(start, end, person_id=person_id)


def get_day_offs_between(
    start=None, end=None, person_id=None, exclude_id=None, person_ids=None
):
    """
    Return all day off entries for the given person or persons, between the
    start date and the end date.
    """
    query = DayOff.query
    if person_id is not None:
        query = query.filter(DayOff.person_id == person_id)
    if person_ids is not None:
        query = query.filter(DayOff.person_id.in_(person_ids))

    if start is not None:
        query = query.filter(
            func.cast(start, DayOff.end_date.type) <= DayOff.end_date
        )
    if end is not None:
        query = query.filter(func.cast(end, DayOff.date.type) >= DayOff.date)

    if exclude_id is not None:
        query = query.filter(DayOff.id != exclude_id)

    return DayOff.serialize_list(query.all())


def remove_time_spents_covered_by_day_off(day_off):
    """
    Delete the time spents of the person of the given day off, on the days
    that the day off covers. Both bounds are read from the column: writing
    them the other way round, as `day_off.date >= TimeSpent.date`, makes
    Python fall back to the reflected operator and silently inverts the
    interval, which then matches nothing beyond a one day long day off.
    """
    TimeSpent.delete_all_by(
        TimeSpent.date >= day_off.date,
        TimeSpent.date <= day_off.end_date,
        person_id=day_off.person_id,
    )


def get_timezoned_interval(start, end):
    """
    Return the time intervals adapted to the timezone of the user.
    """
    timezone = persons_service.get_timezone()
    return date_helpers.get_timezoned_interval(start, end, timezone)


def get_project_month_time_spents(project_id):
    """
    Return the time spents aggregated by department, by person and by month
    for the given project.
    """
    data = {}
    query = (
        TimeSpent.query.join(Task)
        .join(TaskType, TaskType.id == Task.task_type_id)
        .join(Department, Department.id == TaskType.department_id)
        .filter(Task.project_id == project_id)
        .add_columns(Department.id)
        .order_by(TimeSpent.date)
    )

    for time_spent, department_id in query.all():
        # A time spent date is a plain calendar day: it is already the work
        # day it was logged on. The user timezone conversion moved the 1st
        # of a month into the previous month west of UTC.
        date_key = time_spent.date.strftime("%Y-%m")
        department = data.setdefault(department_id, {"total": 0})
        person = department.setdefault(time_spent.person_id, {"total": 0})
        person[date_key] = person.get(date_key, 0) + time_spent.duration
        person["total"] += time_spent.duration
        department["total"] += time_spent.duration
    return data


def get_project_task_type_time_spents(
    project_id, task_type_id, start_date, end_date
):
    """
    Return the time spents for the project and task type in a date range,
    grouped by person ID.
    """
    try:
        query = TimeSpent.query.join(Task).filter(
            Task.project_id == project_id, Task.task_type_id == task_type_id
        )
        if start_date is not None:
            query = query.filter(
                TimeSpent.date >= func.cast(start_date, TimeSpent.date.type)
            )
        if end_date is not None:
            query = query.filter(
                TimeSpent.date <= func.cast(end_date, TimeSpent.date.type)
            )

        time_spents = query.order_by(TimeSpent.date.desc()).all()

        result = defaultdict(list)
        for ts in time_spents:
            result[str(ts.person_id)].append(ts.serialize())

    except DataError:
        raise WrongDateFormatException
    return dict(result)


def get_day_offs_between_for_project(
    project_id,
    start_date=None,
    end_date=None,
    safe=False,
    current_user_id=None,
):
    """
    Return all day off entries of the project team between the start date and
    the end date, grouped by person ID. The day offs of persons other than the
    current user are serialized as safe, unless safe is True.
    """
    project = projects_service.get_project(project_id, relations=True)
    try:
        query = DayOff.query.filter(DayOff.person_id.in_(project["team"]))
        if start_date is not None:
            query = query.filter(
                func.cast(start_date, DayOff.end_date.type) <= DayOff.end_date
            )
        if end_date is not None:
            query = query.filter(
                func.cast(end_date, DayOff.date.type) >= DayOff.date
            )

        days_offs = query.order_by(DayOff.date).all()

        result = defaultdict(list)
        for day_off in days_offs:
            day_off_person_id = str(day_off.person_id)
            result[day_off_person_id].append(
                day_off.serialize()
                if safe or current_user_id == day_off_person_id
                else day_off.serialize_safe()
            )
    except DataError:
        raise WrongDateFormatException
    return dict(result)


def _get_time_spent_raw(task_id, person_id, date):
    """
    Return the time spent recorded for the given task, person and date.
    """
    try:
        return TimeSpent.get_by(
            task_id=task_id,
            person_id=person_id,
            date=func.cast(date, TimeSpent.date.type),
        )
    except DataError:
        raise WrongDateFormatException


def _apply_time_spent_duration(time_spent, duration, add, project_id):
    """
    Set the duration of an existing time spent and notify the clients of the
    change.
    """
    if add:
        duration = time_spent.duration + duration
    time_spent.update({"duration": duration})
    events.emit(
        "time-spent:update",
        {"time_spent_id": str(time_spent.id)},
        project_id=project_id,
    )


def create_or_update_time_spent(task_id, person_id, date, duration, add=False):
    """
    Create a time spent if it does not exist. If it exists, set its duration,
    or add to its duration if add is True. Then compute the task duration
    again and emit the time spent and task events. Return the time spent as a
    dict. If a concurrent request deletes the row, raise
    TimeSpentNotFoundException.
    """
    try:
        return _create_or_update_time_spent(
            task_id, person_id, date, duration, add
        )
    except (ObjectDeletedError, StaleDataError):
        # A concurrent DELETE removed the row. Before the UPDATE, the row
        # matches nothing (StaleDataError). After a commit, the read of the
        # expired row finds nothing (ObjectDeletedError). The request that
        # deletes the row computes the task duration again.
        raise TimeSpentNotFoundException


def _create_or_update_time_spent(task_id, person_id, date, duration, add):
    time_spent = _get_time_spent_raw(task_id, person_id, date)

    task = base_service.get_instance(Task, task_id, TaskNotFoundException)
    project_id = str(task.project_id)
    if time_spent is not None:
        _apply_time_spent_duration(time_spent, duration, add, project_id)
    else:
        try:
            time_spent = TimeSpent.create(
                task_id=task_id,
                person_id=person_id,
                date=date,
                duration=duration,
            )
            persons_service.update_person_last_presence(person_id)
            events.emit(
                "time-spent:new",
                {"time_spent_id": str(time_spent.id)},
                project_id=project_id,
            )
        except IntegrityError:
            # A concurrent request inserted the same (person, task, date)
            # between the read above and this insert. time_spent_uc rejects
            # the second insert, which then updates the first row and does
            # not return a 500 error. BaseMixin.create already rolled the
            # session back.
            time_spent = _get_time_spent_raw(task_id, person_id, date)
            if time_spent is None:
                raise
            _apply_time_spent_duration(time_spent, duration, add, project_id)

    task.duration = sum(
        time_spent.duration
        for time_spent in TimeSpent.get_all_by(task_id=task_id)
    )
    task.save()
    tasks_service.clear_task_cache(task_id)
    events.emit("task:update", {"task_id": task_id}, project_id=project_id)

    return time_spent.serialize()


def delete_time_spent(task_id, person_id, date):
    """
    Delete the time spent for the given task, person and date. Then compute
    the task duration again.
    """
    time_spent = _get_time_spent_raw(task_id, person_id, date)

    if time_spent is None:
        raise TimeSpentNotFoundException

    task = base_service.get_instance(Task, task_id, TaskNotFoundException)
    project_id = str(task.project_id)
    time_spent.duration = 0
    time_spent.delete()
    events.emit(
        "time-spent:delete",
        {"time_spent_id": str(time_spent.id)},
        project_id=project_id,
    )

    task.duration = sum(
        time_spent.duration
        for time_spent in TimeSpent.get_all_by(task_id=task_id)
    )
    task.save()
    tasks_service.clear_task_cache(task_id)
    events.emit("task:update", {"task_id": task_id}, project_id=project_id)

    return time_spent.serialize()


def get_time_spents_for_task(task_id, date=None):
    """
    Return the time spents for the given task and date, or for all dates if
    no date is given, grouped by person ID. The sum of their durations is
    under "total".
    """
    result = collections.defaultdict(list)
    result["total"] = 0
    time_spents = TimeSpent.query.filter_by(task_id=task_id)
    if date is not None:
        time_spents = time_spents.filter_by(
            date=func.cast(date, TimeSpent.date.type)
        )
    for time_spent in time_spents.all():
        result[str(time_spent.person_id)].append(time_spent.serialize())
        result["total"] += time_spent.duration
    return result


def get_time_spents_for_project(
    project_id, page=0, limit=None, cursor_id=None
):
    """
    Return all time spents for the given project, one page of them, or the
    time spents after a cursor (see query_utils.get_paginated_results).
    """
    query = TimeSpent.query.join(Task).filter(Task.project_id == project_id)
    return query_utils.get_paginated_results(
        query, page, limit, cursor_id=cursor_id
    )
