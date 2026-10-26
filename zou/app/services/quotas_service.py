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
    Build quota statistics. It counts the number of frames done for each day.
    A shot is considered done at the first feedback request or at last
    approval.

    If time spent is  filled for it, it weights the result with the frame
    number with the time spents. If there is no time spent, it considers that
    the work was done from the wip date to the feedback date (or approval
    date), or on that end date for a task that never went WIP.
    It computes the shot count and the number of seconds too.

    If the `feedback` flag is set to True, it uses the feedback date
    (real_end_date), if feedback is set to False, it uses the approval date
    (done_date).
    """
    fps = projects_service.get_project_fps(project_id)
    timezone = persons_service.get_timezone()
    shot_type = entity_types_service.get_shot_type()
    quotas = {}
    query = (
        Task.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        # A duration set to 0, or to null, once time was logged leaves
        # nothing to share the shot out by.
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
        # Every time spent of the tasks the person logged time on: the
        # shares of a task are taken together, as on the task type route.
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
        # One EXISTS on the assignees, instead of one per member of the
        # studio; a studio without members then matches nothing, where the
        # empty or_() matched everything.
        query = query.filter(Task.assignees.any(Person.studio_id == studio_id))
    result = query.all()

    # The time spents of a task share its frames out together, whoever
    # logged them, so that the shares add up to the shot.
    time_spents = {}
    for task, nb_frames, date, duration, task_person_id in result:
        if task.id not in time_spents:
            time_spents[task.id] = task, nb_frames or 0, []
        time_spents[task.id][2].append((date, str(task_person_id), duration))

    for task, nb_frames, days in time_spents.values():
        # One block per person: interleaved with the days of another
        # person, the running sum would move frames from one to the other.
        # The blocks come in an order drawn for the task, so that the frame
        # left over by a tie does not always go to the same person.
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
        # One EXISTS on the assignees, instead of one per member of the
        # studio; a studio without members then matches nothing, where the
        # empty or_() matched everything.
        query = query.filter(Task.assignees.any(Person.studio_id == studio_id))
    result = query.all()

    tasks_in_total = set()
    for task, nb_frames, task_person_id in result:
        end_date = task.done_date
        if feedback:
            end_date = task.end_date

        # Spread the work over the days the task was actually in progress,
        # from the wip date to the end date.
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
    Weighted counts are shares of shots: they add up at full precision and
    are rounded only once every share is in, so a period total stays whole.
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
    Build quota statistics in a raw way. It counts the number of frames done
    for each day. A shot is considered done at the first feedback request (end
    date) or approval date (done_date).

    It considers that all the work was done at the end date.
    It computes the shot count and the number of seconds too.
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
        # One EXISTS on the assignees, instead of one per member of the
        # studio; a studio without members then matches nothing, where the
        # empty or_() matched everything.
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
    The entries a row of a task adds to. The query returns a row for each
    assignee of the task: each of them counts it whole, the total counts
    it once.
    """
    if task.id in tasks_in_total:
        return [entry_id]
    tasks_in_total.add(task.id)
    return [entry_id, "total"]


def _spread(amount, nb_days):
    """
    Split a whole amount into whole daily shares that add up to it, the
    remainder spread evenly. Rounding each day's share on its own lost or
    added frames: 5 frames over 11 days counted none.
    """
    return [
        amount * (day + 1) // nb_days - amount * day // nb_days
        for day in range(nb_days)
    ]


def _share_out(amount, durations, task_duration):
    """
    Split a whole amount between time spents by the share of the task
    duration they took. Each share comes from the running sum, so the
    shares add up: rounded one by one, three equal time spents on 10
    frames counted 9. The sum is rounded half up, so that consecutive
    time spents worth a whole number of frames get exactly that number,
    and to 9 decimals first, so that a tie stays one with minutes that
    are not whole (439.8 for a day of 7.33 hours).
    """
    totals = [
        floor(round(amount * spent / task_duration, 9) + 0.5)
        for spent in accumulate(durations)
    ]
    return [total - previous for previous, total in zip([0] + totals, totals)]


def _get_block_key(task_id, person_id):
    """
    The rank of the time spents of a person when a task is shared out: the
    same on every page, but drawn anew for each task, so that the frame
    left over by a tie does not always go to the same person.
    """
    return hashlib.sha1(
        f"{task_id}{person_id}".encode(), usedforsecurity=False
    ).hexdigest()


def _get_working_days(start_date, end_date, timezone):
    """
    The business days a task without time spent is spread over, from its
    WIP day to its end day, taken as calendar days of the user: east of
    UTC, a Monday morning is still Sunday in UTC. A task that never went
    WIP, or one without any working day, run over a weekend only or WIP
    after its end, lands on its end day.
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
    The calendar day a UTC instant falls on for the user.
    """
    return date_helpers.get_date_from_string(
        date_helpers.get_simple_string_with_timezone_from_date(
            date_obj, timezone
        )
    ).date()


def _get_day(date_obj):
    """
    The calendar day of a period bound, given as a date or a datetime.
    """
    if isinstance(date_obj, datetime):
        return date_obj.date()
    return date_obj


def _add_quota_entry(
    quotas, entry_id, date, timezone, nb_frames, nb_drawings, fps, count=1
):
    """
    Add one shot, or the share of it given by count, to the quotas of a
    person, counted at once on its day, its week and its month. Seconds are
    derived from the frame count and the project fps.
    """
    nb_seconds = nb_frames / fps
    # TimeSpent dates are plain calendar days, already the user's working
    # day: converting them would shift them for users west of UTC. Only
    # real datetimes (end / done dates, stored in UTC) need the user
    # timezone applied to find the local day they belong to. The week
    # bucket follows the same local day, or day and week totals disagree
    # around midnight UTC.
    if isinstance(date, datetime):
        date_str = date_helpers.get_simple_string_with_timezone_from_date(
            date, timezone
        )
        local_date = date_helpers.get_date_from_string(date_str)
    else:
        local_date = date
        date_str = date.strftime("%Y-%m-%d")
    year = date_str[:4]
    # A week belongs to its ISO year: 2025-12-30 is the first week of 2026.
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
    Make sure the day, week and month buckets of given dates exist before
    counts are added to them.
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
    Make sure the quota entry of a person exists, with its three
    granularities and their four counters.
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
    Return shots that are included in quota computation for given
    person and month.
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
    Return shots that are included in quota comptutation for given
    person and week.
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
    Return shots that are included in quota comptutation for given
    person and day.
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
    Get all shots leading to a quota computation during the given period.
    Set a weight on each one, the sum of the shares of its tasks:
        * A task with time spent filled weighs the sum of the durations
          divided by the overall task duration. A task whose duration is 0
          or unset is left out.
        * A task without time spent weighs the share of its working days,
          from its WIP day to its end day (feedback or approval), that
          falls in the period. A task that never went WIP, or has no
          working day, weighs whole on its end day.

    The period bounds are expressed in the user's local time. TimeSpent
    dates are plain calendar days, so the bounds apply to them as-is; task
    end / done dates are UTC instants, so the bounds are converted to UTC
    before comparing (a feedback given in the local evening east of UTC
    belongs to the next local day).
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
        # As in the quotas: a duration set to 0, or to null, once time was
        # logged leaves nothing to share the shot out by.
        .filter(Task.duration > 0)
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(TimeSpent, Task.id == TimeSpent.task_id)
        # TimeSpent.id is selected only to keep the rows apart: the legacy
        # Query.all() drops duplicates, and two days logged for the same
        # duration on one task are identical in every other column.
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

    # A task that never went WIP, or went WIP after its end date, is worked
    # on its end date only. LEAST ignores a NULL start date.
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

    # Task.id keeps apart two tasks of a shot worked on the same dates: the
    # legacy Query.all() drops duplicate rows.
    query_shots = query.add_columns(Task.id).all()

    # The share of the days the quotas spread a task over that falls in
    # the period, compared as days of the user: a week is bounded by
    # dates, not datetimes. The period ends before its end bound. As in
    # the quotas, every task of a shot adds its share.
    first_day = _get_day(start)
    last_day = _get_day(end)
    for entity, task_start, task_end, _ in query_shots:
        days = _get_working_days(task_start, task_end, timezone)
        nb_days = len([day for day in days if first_day <= day < last_day])
        if nb_days > 0:
            shot = _get_listed_shot(shots, entity)
            shot["weight"] += nb_days / len(days)

    # Rounded once: rounded per time spent, a shot logged whole in the
    # period weighed 0.99.
    for shot in shots.values():
        shot["weight"] = round(shot["weight"], 2)

    return sorted(shots.values(), key=itemgetter("full_name"))


def _get_listed_shot(shots, entity):
    """
    The entry of a shot in a quota list, created on the first task row of
    the shot, so that the time spents and the tasks of a shot add their
    weights up on it.
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
    Get all shots leading to a quota computation during the given period.
    The period bounds are expressed in the user's local time; end / done
    dates are UTC instants, so the bounds are converted to UTC before
    comparing.
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

    # The period ends before its end bound: a task ending on that local
    # midnight belongs to the next period, as in the raw quotas.
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

    # Task.id keeps a row for each task of a shot: on the shots alone, the
    # legacy Query.all() returns each of them once.
    query_shots = query.add_columns(Task.id).all()

    # As in the quotas, every task of a shot counts.
    for entity, _ in query_shots:
        shot = _get_listed_shot(shots, entity)
        shot["weight"] += 1

    return sorted(shots.values(), key=itemgetter("full_name"))


def _filter_on_scope(query, project_id=None, task_type_id=None):
    """
    Restrict a quota shots query to a production and a task type, each
    only when given: a person's own view spans all of them.
    """
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)
    return query


def _get_timezoned_interval(start, end, timezone=None):
    """
    Convert an interval expressed in the user's local time to naive UTC.
    """
    if timezone is None:
        timezone = persons_service.get_timezone()
    return date_helpers.get_timezoned_interval(start, end, timezone)
