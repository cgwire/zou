import datetime
import isoweek

from dateutil import relativedelta

from sqlalchemy import func
from sqlalchemy.exc import DataError
from sqlalchemy.orm import aliased

from zou.app.models.day_off import DayOff
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType

from zou.app.utils import fields, date_helpers

from zou.app.services import user_service
from zou.app.services.exception import WrongDateFormatException


def get_year_table(person_id=None, project_id=None):
    """
    Return a table giving time spent by user and by month for given year.
    """
    return get_yearly_table(
        None, detail_level="year", person_id=person_id, project_id=project_id
    )


def get_month_table(year, person_id=None, project_id=None):
    """
    Return a table giving time spent by user and by month for given year.
    """
    return get_yearly_table(year, person_id=person_id, project_id=project_id)


def get_week_table(year, person_id=None, project_id=None):
    """
    Return a table giving time spent by user and by week for given year.
    """
    return get_yearly_table(
        year, "week", person_id=person_id, project_id=project_id
    )


def get_day_table(year, month, person_id=None, project_id=None):
    """
    Return a table giving time spent by user and by day for given year and
    month.
    """
    time_spents = get_time_spents_for_month(
        year, month, person_id=person_id, project_id=project_id
    )
    return get_table_from_time_spents(time_spents, "day")


def get_yearly_table(
    year=None, detail_level="month", person_id=None, project_id=None
):
    """
    Return a table giving time spent by user and by week or month for given
    year. Week or month detail level can be selected through *detail_level*
    argument.
    """
    time_spents = get_time_spents_for_year(
        year=year, person_id=person_id, project_id=project_id
    )
    return get_table_from_time_spents(time_spents, detail_level)


def get_time_spents_for_year(year=None, person_id=None, project_id=None):
    """
    Return all time spents for given year.
    """
    query = TimeSpent.query

    if person_id is not None:
        query = query.filter(TimeSpent.person_id == person_id)

    if year is not None:
        query = query.filter(
            TimeSpent.date.between("%s-01-01" % year, "%s-12-31" % year)
        )

    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
        query = query.join(Task)

    return query.all()


def get_time_spents_for_month(year, month, person_id=None, project_id=None):
    """
    Return all time spents for given month.
    """
    date = datetime.datetime(int(year), int(month), 1)
    next_month = date + relativedelta.relativedelta(months=1)
    query = TimeSpent.query.filter(
        TimeSpent.date >= date.strftime("%Y-%m-%d")
    ).filter(TimeSpent.date < next_month.strftime("%Y-%m-%d"))

    if person_id is not None:
        query = query.filter(TimeSpent.person_id == person_id)

    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
        query = query.join(Task)

    return query.all()


def get_table_from_time_spents(time_spents, detail_level="month"):
    """
    Buid a time spent table based on given time spents and given level
    of detail (week, day or month).
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
            result[unit] = {}
        if person_id not in result[unit]:
            result[unit][person_id] = 0
        result[unit][person_id] += time_spent.duration
    return result


def get_time_spents(person_id, date):
    """
    Return time spents for given person and date.
    """
    try:
        time_spents = TimeSpent.query.filter_by(
            person_id=person_id, date=date
        ).all()
    except DataError:
        raise WrongDateFormatException
    return fields.serialize_list(time_spents)


def get_day_off(person_id, date):
    """
    Return day off for given person and date.
    """
    try:
        day_off = DayOff.get_by(person_id=person_id, date=date)
    except DataError:
        raise WrongDateFormatException
    if day_off is not None:
        return day_off.serialize()
    else:
        return {}


def get_year_time_spents(person_id, year, project_id=None):
    """
    Return aggregated time spents at task level for given person and month.
    """
    start, end = date_helpers.get_year_interval(year)
    print(start, end)
    start, end = get_timezoned_interval(start, end)
    entries = get_person_time_spent_entries(
        person_id,
        TimeSpent.date >= start,
        TimeSpent.date < end,
        project_id=project_id,
    )
    return build_results(entries)


def get_month_time_spents(person_id, year, month, project_id=None):
    """
    Return aggregated time spents at task level for given person and month.
    """
    start, end = date_helpers.get_month_interval(year, month)
    start, end = get_timezoned_interval(start, end)
    entries = get_person_time_spent_entries(
        person_id,
        TimeSpent.date >= start,
        TimeSpent.date < end,
        project_id=project_id,
    )
    return build_results(entries)


def get_week_time_spents(person_id, year, week, project_id=None):
    """
    Return aggregated time spents at task level for given person and week.
    """
    start, end = date_helpers.get_week_interval(year, week)
    start, end = get_timezoned_interval(start, end)
    entries = get_person_time_spent_entries(
        person_id,
        TimeSpent.date >= start,
        TimeSpent.date < end,
        project_id=project_id,
    )
    return build_results(entries)


def get_day_time_spents(person_id, year, month, day, project_id=None):
    """
    Return aggregated time spents at task level for given person and day.
    """
    start, end = date_helpers.get_day_interval(year, month, day)
    start, end = get_timezoned_interval(start, end)
    entries = get_person_time_spent_entries(
        person_id,
        TimeSpent.date >= start,
        TimeSpent.date < end,
        project_id=project_id,
    )
    return build_results(entries)


def get_person_time_spent_entries(person_id, *args, project_id=None):
    """
    Return aggregated time spents at task level for given person and
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
        query = query.filter(Project.id == project_id)

    for arg in args:
        query = query.filter(arg)

    return query.all()


def build_results(entries):
    """
    Build results with information to build a time sheet based on given entries
    (tasks + time spent duration aggregate)
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


def get_day_offs_for_month(year, month):
    """
    Get all day off entries for given year and month.
    """
    start, end = date_helpers.get_month_interval(year, month)
    start, end = get_timezoned_interval(start, end)
    return get_day_offs_between(start, end)


def get_person_day_offs_for_week(person_id, year, week):
    """
    Get all day off entries for given person, year and week.
    """
    start, end = date_helpers.get_week_interval(year, week)
    start, end = get_timezoned_interval(start, end)
    return get_day_offs_between(start, end, person_id=person_id)


def get_person_day_offs_for_month(person_id, year, month):
    """
    Get all day off entries for given person, year and week.
    """
    start, end = date_helpers.get_month_interval(year, month)
    start, end = get_timezoned_interval(start, end)
    return get_day_offs_between(start, end, person_id=person_id)


def get_person_day_offs_for_year(person_id, year):
    """
    Get all day off entries for given person, year.
    """
    start, end = date_helpers.get_year_interval(year)
    start, end = get_timezoned_interval(start, end)
    return get_day_offs_between(start, end, person_id=person_id)


def get_day_offs_between(start, end, person_id=None):
    """
    Get all day off entries for given person, year.
    """
    query = DayOff.query
    if person_id is not None:
        query = query.filter(DayOff.person_id == person_id)

    return DayOff.serialize_list(
        query.filter(DayOff.date >= start).filter(DayOff.date < end).all()
    )


def get_timezoned_interval(start, end):
    """
    Get all day off entries for given person, year.
    """
    timezone = user_service.get_timezone()
    return (
        date_helpers.get_string_with_timezone_from_date(start, timezone),
        date_helpers.get_string_with_timezone_from_date(end, timezone),
    )
