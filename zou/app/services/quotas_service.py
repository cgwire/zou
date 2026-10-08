from datetime import datetime, timedelta
from operator import itemgetter
from sqlalchemy import func

from zou.app.utils import date_helpers
from zou.app.models.entity import Entity
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.services import (
    persons_service,
    projects_service,
    entity_types_service,
    entities_service,
)


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
    the work was done from the wip date to the feedback date (or approval date).
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

    if person_id is not None:
        query = query.filter(TimeSpent.person_id == person_id)

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

    for task, nb_frames, date, duration, task_person_id in result:
        task_person_id = str(task_person_id)
        nb_drawings = task.nb_drawings or 0
        nb_frames = nb_frames or 0
        if task.duration > 0:
            share = duration / task.duration
            nb_frames = round(nb_frames * share)
            nb_drawings = round(nb_drawings * share)
            entry_id = str(task_person_id)
            # We get quotas for a specific person split by task types
            if person_id is not None:
                entry_id = str(task.task_type_id)
            for entry in [entry_id, "total"]:
                _add_quota_entry(
                    quotas,
                    entry,
                    date,
                    timezone,
                    nb_frames,
                    nb_drawings,
                    fps,
                    count=share,
                )

    query = (
        Task.query.filter(Task.project_id == project_id)
        .filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.real_start_date != None)
        .filter(TimeSpent.id == None)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(TimeSpent, Task.id == TimeSpent.task_id)
        .join(Task.assignees)
        .add_columns(Entity.nb_frames, Person.id)
    )

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if person_id is not None:
        person = persons_service.get_person_raw(person_id)
        query = query.filter(Task.assignees.contains(person))

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

    for task, nb_frames, task_person_id in result:
        end_date = task.done_date
        if feedback:
            end_date = task.end_date

        business_days = (
            date_helpers.get_business_days(task.real_start_date, end_date) + 1
        )
        if nb_frames is not None:
            nb_frames = round(nb_frames / business_days) or 0
        else:
            nb_frames = 0

        nb_drawings = task.nb_drawings or 0

        # Spread the work over the days the task was actually in progress,
        # from the wip date to the end date. The cursor used to start at
        # the end date, which pushed every frame past the period.
        day = task.real_start_date
        for _ in range((end_date - task.real_start_date).days + 1):
            if day.weekday() < 5:
                entry_id = str(task_person_id)
                # We get quotas for a specific person split by task types
                if person_id is not None:
                    entry_id = str(task.task_type_id)

                for entry in [entry_id, "total"]:
                    _add_quota_entry(
                        quotas,
                        entry,
                        day,
                        timezone,
                        nb_frames,
                        nb_drawings,
                        fps,
                        count=1 / business_days,
                    )
            day = day + timedelta(1)
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
        query = query.filter(Task.assignees.contains(person))

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

        for entry in [entry_id, "total"]:
            _add_quota_entry(
                quotas, entry, date, timezone, nb_frames, nb_drawings, fps
            )
    return quotas


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
    Set a weight on each one:
        * If there is time spent filled, weight it by the sum of duration
          divided py the overall task duration.
        * If there is no time spent, weight it by the number of business days
          in the time interval spent between WIP date (start) and
          feedback date (end).

    The period bounds are expressed in the user's local time. TimeSpent
    dates are plain calendar days, so the bounds apply to them as-is; task
    end / done dates are UTC instants, so the bounds are converted to UTC
    before comparing (a feedback given in the local evening east of UTC
    belongs to the next local day).
    """
    shot_type = entity_types_service.get_shot_type()
    person = persons_service.get_person_raw(person_id)
    shots = []
    already_listed = {}
    if type(start) is str:
        start = date_helpers.get_datetime_from_string(start)
    if type(end) is str:
        end = date_helpers.get_datetime_from_string(end)
    utc_start, utc_end = _get_timezoned_interval(start, end, timezone)

    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        .filter(Task.task_type_id == task_type_id)
        .filter(TimeSpent.person_id == person_id)
        .filter(TimeSpent.date >= func.cast(start, TimeSpent.date.type))
        .filter(TimeSpent.date < func.cast(end, TimeSpent.date.type))
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(TimeSpent, Task.id == TimeSpent.task_id)
        # TimeSpent.id is selected only to keep the rows apart: the legacy
        # Query.all() drops duplicates, and two days logged for the same
        # duration on one task are identical in every other column.
        .add_columns(Task.duration, TimeSpent.duration, TimeSpent.id)
    )

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    query_shots = query.all()
    for entity, task_duration, duration, _ in query_shots:
        shot = entity.serialize()
        if shot["id"] not in already_listed:
            full_name, _, _ = entities_service.get_full_entity_name(shot["id"])
            shot["full_name"] = full_name
            shot["weight"] = round(duration / task_duration, 2) or 0
            shots.append(shot)
            already_listed[shot["id"]] = shot
        else:
            shot = already_listed[shot["id"]]
            shot["weight"] += round(duration / task_duration, 2)

    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        .filter(Task.task_type_id == task_type_id)
        .filter(Task.real_start_date != None)
        .filter(Task.assignees.contains(person))
        .filter(TimeSpent.id == None)
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(TimeSpent, TimeSpent.task_id == Task.id)
    )

    if feedback:
        query = (
            query.filter(Task.end_date != None)
            .filter(
                (Task.real_start_date <= utc_end)
                & (Task.end_date >= utc_start)
            )
            .add_columns(Task.real_start_date, Task.end_date)
        )
    else:
        query = (
            query.filter(Task.done_date != None)
            .filter(
                (Task.real_start_date <= utc_end)
                & (Task.done_date >= utc_start)
            )
            .add_columns(Task.real_start_date, Task.done_date)
        )

    query_shots = query.all()

    for entity, task_start, task_end in query_shots:
        shot = entity.serialize()
        if shot["id"] not in already_listed:
            business_days = (
                date_helpers.get_business_days(task_start, task_end) + 1
            )
            full_name, _, _ = entities_service.get_full_entity_name(shot["id"])
            shot["full_name"] = full_name
            multiplicator = 1
            if task_start >= start and task_end <= end:
                multiplicator = business_days
            elif task_start >= start:
                multiplicator = (
                    date_helpers.get_business_days(task_start, end) + 1
                )
            elif task_end <= end:
                multiplicator = (
                    date_helpers.get_business_days(start, task_end) + 1
                )
            shot["weight"] = round(multiplicator / business_days, 2)
            already_listed[shot["id"]] = True
            shots.append(shot)

    return sorted(shots, key=itemgetter("full_name"))


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
    shots = []
    if type(start) is str:
        start = date_helpers.get_datetime_from_string(start)
    if type(end) is str:
        end = date_helpers.get_datetime_from_string(end)
    start, end = _get_timezoned_interval(start, end, timezone)

    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        .filter(Task.task_type_id == task_type_id)
        .filter(Task.assignees.contains(person))
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
    )

    if feedback:
        query = query.filter(
            Task.end_date.between(
                func.cast(start, Task.end_date.type),
                func.cast(end, Task.end_date.type),
            )
        )
    else:
        query = query.filter(
            Task.done_date.between(
                func.cast(start, Task.done_date.type),
                func.cast(end, Task.done_date.type),
            )
        )

    query_shots = query.all()

    for entity in query_shots:
        shot = entity.serialize()
        full_name, _, _ = entities_service.get_full_entity_name(shot["id"])
        shot["full_name"] = full_name
        shot["weight"] = 1
        shots.append(shot)

    return sorted(shots, key=itemgetter("full_name"))


def _get_timezoned_interval(start, end, timezone=None):
    """
    Convert an interval expressed in the user's local time to naive UTC.
    """
    if timezone is None:
        timezone = persons_service.get_timezone()
    return date_helpers.get_timezoned_interval(start, end, timezone)
