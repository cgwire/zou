import hashlib
from datetime import datetime, timedelta
from itertools import accumulate
from math import floor
from operator import itemgetter

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from zou.app.models.entity import Entity
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.services import (
    entities_service,
    entity_types_service,
    persons_service,
    projects_service,
)
from zou.app.utils import date_helpers


def get_weighted_quotas(
    project_id,
    task_type_id=None,
    person_id=None,
    studio_id=None,
    feedback=True,
):
    """
    Return the quota statistics: the number of frames done for each day. A
    shot is done at the first feedback request or at the last approval.

    If there are time spents, they give the weight of the frame number.
    If there is no time spent, the work occurred from the
    WIP date to the feedback date (or approval date). If the task did not
    go WIP, the work occurred on that end date. The statistics also
    contain the shot count and the number of seconds.

    If the `feedback` flag is True, use the feedback date (real_end_date).
    If the `feedback` flag is False, use the approval date (done_date).
    """
    fps = projects_service.get_project_fps(project_id)
    timezone = persons_service.get_timezone()
    shot_type = entity_types_service.get_shot_type()
    quotas = {}
    query = (
        Task.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        # If the duration is 0 or null after time was logged, there is
        # nothing to divide the shot by.
        .filter(Task.duration > 0)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(TimeSpent, Task.id == TimeSpent.task_id)
        .add_columns(
            Entity.nb_frames,
            TimeSpent.date,
            TimeSpent.duration,
            TimeSpent.person_id,
        )
    )

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    person = None
    if person_id is not None:
        person = persons_service.get_person_raw(person_id)
        # Get all the time spents of the tasks where the person logged
        # time. The shares of a task go together, as on the task type
        # route.
        own_time_spent = aliased(TimeSpent)
        query = query.filter(
            Task.id.in_(
                select(own_time_spent.task_id).where(
                    own_time_spent.person_id == person.id
                )
            )
        )

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    if studio_id is not None:
        # One EXISTS on the assignees: a studio without members matches
        # nothing.
        query = query.filter(Task.assignees.any(Person.studio_id == studio_id))
    result = query.all()

    # The time spents of a task divide its frames together, for all the
    # persons who logged them. Thus the sum of the shares is the shot.
    time_spents = {}
    for task, nb_frames, date, duration, task_person_id in result:
        if task.id not in time_spents:
            time_spents[task.id] = task, nb_frames or 0, []
        time_spents[task.id][2].append((date, str(task_person_id), duration))

    for task, nb_frames, days in time_spents.values():
        # Use one block for each person. If the days of two persons mix,
        # the running sum moves frames from one person to the other. The
        # block order is random for each task. Thus the frame that remains
        # after a tie does not always go to the same person.
        days.sort(key=lambda day: (_get_block_key(task.id, day[1]), day[0]))
        durations = [duration for _, _, duration in days]
        frames = _share_out(nb_frames, durations, task.duration)
        drawings = _share_out(task.nb_drawings or 0, durations, task.duration)
        for index, (date, day_person_id, duration) in enumerate(days):
            if person is None or day_person_id == str(person.id):
                entry_id = day_person_id
                # We get quotas for a specific person split by task types
                if person_id is not None:
                    entry_id = str(task.task_type_id)
                for entry in [entry_id, "total"]:
                    _add_quota_entry(
                        quotas,
                        entry,
                        date,
                        timezone,
                        frames[index],
                        drawings[index],
                        fps,
                        count=duration / task.duration,
                    )

    query = (
        Task.query.filter(Task.project_id == project_id)
        .filter(Entity.entity_type_id == shot_type["id"])
        .filter(TimeSpent.id == None)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(TimeSpent, Task.id == TimeSpent.task_id)
        .join(Task.assignees)
        .add_columns(Entity.nb_frames, Person.id)
    )

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if person is not None:
        # On the assignee the query joins: contains() joins the assignees
        # again and keeps a row for each of them.
        query = query.filter(Person.id == person.id)

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    if studio_id is not None:
        # One EXISTS on the assignees: a studio without members matches
        # nothing.
        query = query.filter(Task.assignees.any(Person.studio_id == studio_id))
    result = query.all()

    tasks_in_total = set()
    for task, nb_frames, task_person_id in result:
        end_date = task.done_date
        if feedback:
            end_date = task.end_date

        # Divide the work between the days when the task was in progress,
        # from the WIP date to the end date.
        days = _get_working_days(task.real_start_date, end_date, timezone)
        frames = _spread(nb_frames or 0, len(days))
        drawings = _spread(task.nb_drawings or 0, len(days))

        entry_id = str(task_person_id)
        # We get quotas for a specific person split by task types
        if person_id is not None:
            entry_id = str(task.task_type_id)
        entries = _get_quota_entries(entry_id, task, tasks_in_total)

        for day, nb_day_frames, nb_day_drawings in zip(days, frames, drawings):
            for entry in entries:
                _add_quota_entry(
                    quotas,
                    entry,
                    day,
                    timezone,
                    nb_day_frames,
                    nb_day_drawings,
                    fps,
                    count=1 / len(days),
                )
    return _round_counts(quotas)


def _round_counts(quotas):
    """
    Round the weighted counts. These counts are shares of shots. Their sum
    has full precision, and they are rounded only after the sum of all the
    shares. Thus the total of a period stays a whole number.
    """
    for entry in quotas.values():
        for period in entry.values():
            period["count"] = {
                key: round(value, 2) for key, value in period["count"].items()
            }
    return quotas


def get_raw_quotas(
    project_id,
    task_type_id=None,
    person_id=None,
    studio_id=None,
    feedback=True,
):
    """
    Return the raw quota statistics: the number of frames done for each
    day. A shot is done at the first feedback request (end date) or at the
    approval date (done_date).

    All the work occurred on the end date. The statistics also contain the
    shot count and the number of seconds.
    """
    fps = projects_service.get_project_fps(project_id)
    timezone = persons_service.get_timezone()
    shot_type = entity_types_service.get_shot_type()
    quotas = {}
    query = (
        Task.query.filter(Task.project_id == project_id)
        .filter(Entity.entity_type_id == shot_type["id"])
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(Task.assignees)
        .add_columns(Entity.nb_frames, Person.id)
    )

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if person_id is not None:
        person = persons_service.get_person_raw(person_id)
        # On the assignee the query joins: contains() joins the assignees
        # again and keeps a row for each of them.
        query = query.filter(Person.id == person.id)

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    if studio_id is not None:
        # One EXISTS on the assignees: a studio without members matches
        # nothing.
        query = query.filter(Task.assignees.any(Person.studio_id == studio_id))

    result = query.all()

    tasks_in_total = set()
    for task, nb_frames, task_person_id in result:
        date = task.done_date
        if feedback:
            date = task.end_date

        if nb_frames is None:
            nb_frames = 0

        nb_drawings = task.nb_drawings or 0

        entry_id = str(task_person_id)
        if person_id is not None:
            entry_id = str(task.task_type_id)

        for entry in _get_quota_entries(entry_id, task, tasks_in_total):
            _add_quota_entry(
                quotas, entry, date, timezone, nb_frames, nb_drawings, fps
            )
    return quotas


def _get_quota_entries(entry_id, task, tasks_in_total):
    """
    Return the entries that a row of a task adds to. The query returns a
    row for each assignee of the task. Each assignee counts the full task,
    and the total counts it one time.
    """
    if task.id in tasks_in_total:
        return [entry_id]
    tasks_in_total.add(task.id)
    return [entry_id, "total"]


def _spread(amount, nb_days):
    """
    Divide a whole amount into whole daily shares. The sum of the shares
    is the amount, and the remainder is divided equally. If each daily
    share is rounded alone, frames are lost or added: 5 frames on 11 days
    gave 0.
    """
    return [
        amount * (day + 1) // nb_days - amount * day // nb_days
        for day in range(nb_days)
    ]


def _share_out(amount, durations, task_duration):
    """
    Divide a whole amount between time spents, by their share of the task
    duration. Each share comes from the running sum, thus the sum of the
    shares is correct. If each share is rounded alone, three equal time
    spents on 10 frames gave 9. The sum is rounded half up: consecutive
    time spents that are worth a whole number of frames get exactly that
    number. The sum is first rounded to 9 decimals: thus a tie stays a
    tie with minutes that are not whole (439.8 for a day of 7.33 hours).
    """
    totals = [
        floor(round(amount * spent / task_duration, 9) + 0.5)
        for spent in accumulate(durations)
    ]
    return [total - previous for previous, total in zip([0] + totals, totals)]


def _get_block_key(task_id, person_id):
    """
    Return the rank of the time spents of a person when a task is divided.
    The rank is the same on all pages, but it is random for each task.
    Thus the frame that remains after a tie does not always go to the
    same person.
    """
    return hashlib.sha1(
        f"{task_id}{person_id}".encode(), usedforsecurity=False
    ).hexdigest()


def _get_working_days(start_date, end_date, timezone):
    """
    Return the business days of a task without time spent, from its WIP
    day to its end day. These days are calendar days of the user: east of
    UTC, a Monday morning is still Sunday in UTC. These tasks count only
    on their end day:
    - a task that did not go WIP
    - a task without a working day, because it ran on a weekend only
    - a task that went WIP after its end.
    """
    end_day = _get_local_day(end_date, timezone)
    if start_date is None:
        return [end_day]
    start_day = _get_local_day(start_date, timezone)
    days = (
        start_day + timedelta(days=offset)
        for offset in range((end_day - start_day).days + 1)
    )
    return [day for day in days if day.weekday() < 5] or [end_day]


def _get_local_day(date_obj, timezone):
    """
    Return the calendar day of the user that contains a UTC instant.
    """
    return date_helpers.get_date_from_string(
        date_helpers.get_simple_string_with_timezone_from_date(
            date_obj, timezone
        )
    ).date()


def _get_day(date_obj):
    """
    Return the calendar day of a period bound, given as a date or a
    datetime.
    """
    if isinstance(date_obj, datetime):
        return date_obj.date()
    return date_obj


def _add_quota_entry(
    quotas, entry_id, date, timezone, nb_frames, nb_drawings, fps, count=1
):
    """
    Add one shot, or the share of it given by count, to the quotas of a
    person. Add it to its day, its week, its month and its year at the
    same time. The seconds come from the frame count and the project fps.
    """
    nb_seconds = nb_frames / fps
    # TimeSpent dates are plain calendar days: they are already the
    # working day of the user. A conversion moves them for users west of
    # UTC. Only real datetimes (end / done dates, stored in UTC) need the
    # user timezone to find their local day. The week bucket uses the same
    # local day. If not, the day and week totals are different near
    # midnight UTC.
    if isinstance(date, datetime):
        date_str = date_helpers.get_simple_string_with_timezone_from_date(
            date, timezone
        )
        local_date = date_helpers.get_date_from_string(date_str)
    else:
        local_date = date
        date_str = date.strftime("%Y-%m-%d")
    year = date_str[:4]
    # A week is part of its ISO year: 2025-12-30 is in the first week of
    # 2026.
    iso_year, iso_week, _ = local_date.isocalendar()
    week = f"{iso_year}-{iso_week}"
    month = date_str[:7]
    if entry_id not in quotas:
        _init_quota_entry(quotas, entry_id)
    _init_quota_date(quotas, entry_id, date_str, week, month)
    quotas[entry_id]["day"]["frames"][date_str] += nb_frames
    quotas[entry_id]["day"]["seconds"][date_str] += nb_seconds
    quotas[entry_id]["day"]["drawings"][date_str] += nb_drawings
    quotas[entry_id]["day"]["count"][date_str] += count
    quotas[entry_id]["week"]["frames"][week] += nb_frames
    quotas[entry_id]["week"]["seconds"][week] += nb_seconds
    quotas[entry_id]["week"]["drawings"][week] += nb_drawings
    quotas[entry_id]["week"]["count"][week] += count
    quotas[entry_id]["month"]["frames"][month] += nb_frames
    quotas[entry_id]["month"]["seconds"][month] += nb_seconds
    quotas[entry_id]["month"]["drawings"][month] += nb_drawings
    quotas[entry_id]["month"]["count"][month] += count
    quotas[entry_id]["year"]["frames"][year] += nb_frames
    quotas[entry_id]["year"]["drawings"][year] += nb_drawings
    quotas[entry_id]["year"]["seconds"][year] += nb_seconds
    quotas[entry_id]["year"]["count"][year] += count


def _init_quota_date(quotas, entry_id, date_str, week, month):
    """
    Make sure that the day, week, month and year buckets of the given
    dates exist before the counts are added to them.
    """
    year = month[:4]
    week_year = week[:4]
    if date_str not in quotas[entry_id]["day"]["frames"]:
        quotas[entry_id]["day"]["frames"][date_str] = 0
        quotas[entry_id]["day"]["seconds"][date_str] = 0
        quotas[entry_id]["day"]["count"][date_str] = 0
        quotas[entry_id]["day"]["drawings"][date_str] = 0
        if month not in quotas[entry_id]["day"]["entries"]:
            quotas[entry_id]["day"]["entries"][month] = 0
        quotas[entry_id]["day"]["entries"][month] += 1
    if week not in quotas[entry_id]["week"]["frames"]:
        quotas[entry_id]["week"]["frames"][week] = 0
        quotas[entry_id]["week"]["seconds"][week] = 0
        quotas[entry_id]["week"]["count"][week] = 0
        quotas[entry_id]["week"]["drawings"][week] = 0
        if week_year not in quotas[entry_id]["week"]["entries"]:
            quotas[entry_id]["week"]["entries"][week_year] = 0
        quotas[entry_id]["week"]["entries"][week_year] += 1
    if month not in quotas[entry_id]["month"]["frames"]:
        quotas[entry_id]["month"]["frames"][month] = 0
        quotas[entry_id]["month"]["seconds"][month] = 0
        quotas[entry_id]["month"]["count"][month] = 0
        quotas[entry_id]["month"]["drawings"][month] = 0
        if year not in quotas[entry_id]["month"]["entries"]:
            quotas[entry_id]["month"]["entries"][year] = 0
        quotas[entry_id]["month"]["entries"][year] += 1
    if year not in quotas[entry_id]["year"]["frames"]:
        quotas[entry_id]["year"]["frames"][year] = 0
        quotas[entry_id]["year"]["seconds"][year] = 0
        quotas[entry_id]["year"]["count"][year] = 0
        quotas[entry_id]["year"]["drawings"][year] = 0


def _init_quota_entry(quotas, entry_id):
    """
    Create the quota entry of a person, with its day, week, month and year
    buckets and their counters.
    """
    quotas[entry_id] = {
        "day": {
            "frames": {},
            "seconds": {},
            "count": {},
            "entries": {},
            "drawings": {},
        },
        "week": {
            "frames": {},
            "seconds": {},
            "count": {},
            "entries": {},
            "drawings": {},
        },
        "month": {
            "frames": {},
            "seconds": {},
            "count": {},
            "entries": {},
            "drawings": {},
        },
        "year": {"frames": {}, "seconds": {}, "count": {}, "drawings": {}},
    }


def get_month_quota_shots(
    person_id,
    year,
    month,
    project_id=None,
    task_type_id=None,
    weighted=True,
    feedback=True,
    timezone=None,
):
    """
    Return the shots that are included in the quota computation for the
    given person and month.
    """
    start, end = date_helpers.get_month_interval(year, month)
    if weighted:
        return get_weighted_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
            timezone=timezone,
        )
    else:
        return get_raw_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
            timezone=timezone,
        )


def get_week_quota_shots(
    person_id,
    year,
    week,
    project_id=None,
    task_type_id=None,
    weighted=True,
    feedback=True,
    timezone=None,
):
    """
    Return the shots that are included in the quota computation for the
    given person and week.
    """
    start, end = date_helpers.get_week_interval(year, week)
    if weighted:
        return get_weighted_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
            timezone=timezone,
        )
    else:
        return get_raw_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
            timezone=timezone,
        )


def get_day_quota_shots(
    person_id,
    year,
    month,
    day,
    project_id=None,
    task_type_id=None,
    weighted=True,
    feedback=True,
    timezone=None,
):
    """
    Return the shots that are included in the quota computation for the
    given person and day.
    """
    start, end = date_helpers.get_day_interval(year, month, day)
    if weighted:
        return get_weighted_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
            timezone=timezone,
        )
    else:
        return get_raw_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
            timezone=timezone,
        )


def get_weighted_quota_shots_between(
    person_id,
    start,
    end,
    project_id=None,
    task_type_id=None,
    feedback=True,
    timezone=None,
):
    """
    Return all the shots that cause a quota computation during the given
    period. Set a weight on each shot: the sum of the shares of its tasks.
        * The weight of a task with time spents is the sum of the
          durations divided by the full task duration. Do not include a
          task with a duration of 0 or without a duration.
        * The weight of a task without time spent is the share of its
          working days in the period, from its WIP day to its end day
          (feedback or approval). If the task did not go WIP, or has no
          working day, its full weight goes on its end day.

    The period bounds are in the local time of the user. TimeSpent dates
    are plain calendar days, thus the bounds apply to them directly. Task
    end / done dates are UTC instants, thus the bounds become UTC before
    the comparison. A feedback given in the local evening east of UTC is
    part of the next local day.
    """
    shot_type = entity_types_service.get_shot_type()
    person = persons_service.get_person_raw(person_id)
    shots = {}
    if type(start) is str:
        start = date_helpers.get_datetime_from_string(start)
    if type(end) is str:
        end = date_helpers.get_datetime_from_string(end)
    if timezone is None:
        timezone = persons_service.get_timezone()
    utc_start, utc_end = _get_timezoned_interval(start, end, timezone)

    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(TimeSpent.person_id == person_id)
        .filter(TimeSpent.date >= func.cast(start, TimeSpent.date.type))
        .filter(TimeSpent.date < func.cast(end, TimeSpent.date.type))
        # As in the quotas: if the duration is 0 or null after time was
        # logged, there is nothing to divide the shot by.
        .filter(Task.duration > 0)
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(TimeSpent, Task.id == TimeSpent.task_id)
        # TimeSpent.id is selected only to keep the rows different. The
        # legacy Query.all() removes duplicates. Two days logged with the
        # same duration on one task are identical in all other columns.
        .add_columns(Task.duration, TimeSpent.duration, TimeSpent.id)
    )

    query = _filter_on_scope(query, project_id, task_type_id)

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    query_shots = query.all()
    for entity, task_duration, duration, _ in query_shots:
        shot = _get_listed_shot(shots, entity)
        shot["weight"] += duration / task_duration

    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.assignees.contains(person))
        .filter(TimeSpent.id == None)
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(TimeSpent, TimeSpent.task_id == Task.id)
    )

    query = _filter_on_scope(query, project_id, task_type_id)

    # If a task did not go WIP, or went WIP after its end date, its work
    # occurred on its end date only. LEAST ignores a NULL start date.
    if feedback:
        query = (
            query.filter(Task.end_date != None)
            .filter(
                (func.least(Task.real_start_date, Task.end_date) <= utc_end)
                & (Task.end_date >= utc_start)
            )
            .add_columns(Task.real_start_date, Task.end_date)
        )
    else:
        query = (
            query.filter(Task.done_date != None)
            .filter(
                (func.least(Task.real_start_date, Task.done_date) <= utc_end)
                & (Task.done_date >= utc_start)
            )
            .add_columns(Task.real_start_date, Task.done_date)
        )

    # Task.id keeps two tasks of a shot with the same work dates different.
    # The legacy Query.all() removes duplicate rows.
    query_shots = query.add_columns(Task.id).all()

    # The share of the task days that is in the period. The comparison
    # uses days of the user: dates, not datetimes, are the limits of a
    # week. The period ends before its end bound. As in the quotas, each
    # task of a shot adds its share.
    first_day = _get_day(start)
    last_day = _get_day(end)
    for entity, task_start, task_end, _ in query_shots:
        days = _get_working_days(task_start, task_end, timezone)
        nb_days = len([day for day in days if first_day <= day < last_day])
        if nb_days > 0:
            shot = _get_listed_shot(shots, entity)
            shot["weight"] += nb_days / len(days)

    # Round one time only. If each time spent is rounded, a shot logged
    # fully in the period has a weight of 0.99.
    for shot in shots.values():
        shot["weight"] = round(shot["weight"], 2)

    return sorted(shots.values(), key=itemgetter("full_name"))


def _get_listed_shot(shots, entity):
    """
    Return the entry of a shot in a quota list. Create it on the first
    task row of the shot. Thus the time spents and the tasks of a shot
    add their weights to this entry.
    """
    shot_id = str(entity.id)
    if shot_id not in shots:
        shot = entity.serialize()
        full_name, _, _ = entities_service.get_full_entity_name(shot_id)
        shot["full_name"] = full_name
        shot["weight"] = 0
        shots[shot_id] = shot
    return shots[shot_id]


def get_raw_quota_shots_between(
    person_id,
    start,
    end,
    project_id=None,
    task_type_id=None,
    feedback=True,
    timezone=None,
):
    """
    Return all the shots that cause a quota computation during the given
    period. The period bounds are in the local time of the user. End /
    done dates are UTC instants, thus the bounds become UTC before the
    comparison.
    """
    shot_type = entity_types_service.get_shot_type()
    person = persons_service.get_person_raw(person_id)
    shots = {}
    if type(start) is str:
        start = date_helpers.get_datetime_from_string(start)
    if type(end) is str:
        end = date_helpers.get_datetime_from_string(end)
    start, end = _get_timezoned_interval(start, end, timezone)

    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.assignees.contains(person))
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
    )

    query = _filter_on_scope(query, project_id, task_type_id)

    # The period ends before its end bound. A task that ends on that local
    # midnight is part of the next period, as in the raw quotas.
    if feedback:
        query = query.filter(
            (Task.end_date >= func.cast(start, Task.end_date.type))
            & (Task.end_date < func.cast(end, Task.end_date.type))
        )
    else:
        query = query.filter(
            (Task.done_date >= func.cast(start, Task.done_date.type))
            & (Task.done_date < func.cast(end, Task.done_date.type))
        )

    # Task.id keeps a row for each task of a shot. With the shots only,
    # the legacy Query.all() returns each shot one time.
    query_shots = query.add_columns(Task.id).all()

    # As in the quotas, each task of a shot counts.
    for entity, _ in query_shots:
        shot = _get_listed_shot(shots, entity)
        shot["weight"] += 1

    return sorted(shots.values(), key=itemgetter("full_name"))


def _filter_on_scope(query, project_id=None, task_type_id=None):
    """
    Filter a query of quota shots on a production and a task type, only
    if they are given. The view of a person includes all of them.
    """
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)
    return query


def _get_timezoned_interval(start, end, timezone=None):
    """
    Convert an interval in the local time of the user to naive UTC.
    """
    if timezone is None:
        timezone = persons_service.get_timezone()
    return date_helpers.get_timezoned_interval(start, end, timezone)
