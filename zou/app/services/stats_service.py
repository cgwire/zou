import copy

from sqlalchemy import func
from sqlalchemy.orm import aliased

from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.services import (
    persons_service,
)

DEFAULT_RETAKE_STATS = {
    "max_retake_count": 0,
    "evolution": {},
    "done": {
        "count": 0,
        "frames": 0,
        "drawings": 0,
    },
    "retake": {
        "count": 0,
        "frames": 0,
        "drawings": 0,
    },
    "other": {
        "count": 0,
        "frames": 0,
        "drawings": 0,
    },
}


DEFAULT_EVOLUTION_STATS = {
    "done": {"count": 0, "frames": 0, "drawings": 0},
    "retake": {"count": 0, "frames": 0, "drawings": 0},
    "other": {"count": 0, "frames": 0, "drawings": 0},
}


def _new_status_entry(task_status_short_name, task_status_color):
    """
    Return an empty count bucket that holds the display fields of the task
    status.
    """
    return {
        "name": task_status_short_name,
        "color": task_status_color,
        "count": 0,
        "frames": 0,
        "drawings": 0,
    }


def _add_to_bucket(bucket, count, nb_frames, nb_drawings):
    """
    Add the given counts to a bucket. A null column counts as zero: the sums
    come from the database, where nb_frames and nb_drawings are nullable.
    """
    bucket["count"] += count or 0
    bucket["frames"] += nb_frames or 0
    bucket["drawings"] += nb_drawings or 0


def get_main_stats():
    """
    Return the counts that the telemetry sends to the CGWire website.
    """
    return {
        "number_of_video_previews": PreviewFile.query.filter(
            PreviewFile.extension == "mp4"
        ).count(),
        "number_of_picture_previews": PreviewFile.query.filter(
            PreviewFile.extension == "png"
        ).count(),
        "number_of_model_previews": PreviewFile.query.filter(
            PreviewFile.extension == "obj"
        ).count(),
        "number_of_comments": Comment.query.count(),
    }


def get_episode_stats_for_project(project_id, only_assigned=False):
    """
    Return the number of tasks of the given project, by task status, task
    type and episode.
    """
    results = {}
    episode_counts = _get_episode_counts(project_id, only_assigned)
    for data in episode_counts:
        add_entry_to_stats(results, *data)
        add_entry_to_all_stats(results, *data)
    return results


def _get_episode_counts(project_id, only_assigned=False):
    """
    Count the tasks of a project by episode, task type and task status.
    Also give the sums of their frames and drawings.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    query = (
        Task.query.with_entities(
            Task.project_id,
            Episode.id,
            Task.task_type_id,
            Task.task_status_id,
            TaskStatus.short_name,
            TaskStatus.color,
        )
        .filter(Task.project_id == project_id)
        .join(Project, Project.id == Task.project_id)
        .join(TaskStatus, TaskStatus.id == Task.task_status_id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Sequence, Sequence.id == Entity.parent_id)
        .join(Episode, Episode.id == Sequence.parent_id)
        .group_by(
            Task.project_id,
            Episode.id,
            Task.task_type_id,
            Task.task_status_id,
            TaskStatus.short_name,
            TaskStatus.color,
        )
        .add_columns(func.count(Task.id))
        .add_columns(func.sum(Task.nb_drawings))
        .add_columns(func.sum(Entity.nb_frames))
    )

    if only_assigned:
        query = query.filter(persons_service.build_assignee_filter())

    return query.all()


def add_entry_to_stats(
    results,
    project_id,
    episode_id,
    task_type_id,
    task_status_id,
    task_status_short_name,
    task_status_color,
    task_count,
    task_nb_drawings,
    entity_nb_frames,
):
    """
    Add the given count to the stats results, for the given episode, task
    type and task status. Also add it to the "all" aggregate of the episode.
    """
    episode_id = str(episode_id)
    task_type_id = str(task_type_id)
    task_status_id = str(task_status_id)
    results.setdefault(episode_id, {})
    results[episode_id].setdefault(task_type_id, {})
    results[episode_id][task_type_id][task_status_id] = {
        "name": task_status_short_name,
        "color": task_status_color,
        "count": task_count,
        "frames": entity_nb_frames or 0,
        "drawings": task_nb_drawings or 0,
    }

    # Aggregate for the episode
    results[episode_id].setdefault("all", {})
    results[episode_id]["all"].setdefault(
        task_status_id,
        _new_status_entry(task_status_short_name, task_status_color),
    )
    _add_to_bucket(
        results[episode_id]["all"][task_status_id],
        task_count,
        entity_nb_frames,
        task_nb_drawings,
    )


def add_entry_to_all_stats(
    results,
    project_id,
    episode_id,
    task_type_id,
    task_status_id,
    task_status_short_name,
    task_status_color,
    task_count,
    task_nb_drawings,
    entity_nb_frames,
):
    """
    Add the given count to the aggregated entry of the stats results, for
    the given task type and task status. This entry is the sum for all the
    episodes.
    """
    task_type_id = str(task_type_id)
    task_status_id = str(task_status_id)
    results.setdefault("all", {"all": {}})

    for task_type_key in [task_type_id, "all"]:
        results["all"].setdefault(task_type_key, {})
        results["all"][task_type_key].setdefault(
            task_status_id,
            _new_status_entry(task_status_short_name, task_status_color),
        )
        _add_to_bucket(
            results["all"][task_type_key][task_status_id],
            task_count,
            entity_nb_frames,
            task_nb_drawings,
        )


def get_episode_retake_stats_for_project(project_id, only_assigned=False):
    """
    Return the number of retakes and done tasks of the given project, by
    task type and episode, as a dict. Also give the maximum retake count by
    episode and the evolution of the number of retakes.
    Example of a returned entry:
        "1dcdc0f2-8aa1-4267-b56d-7621d86eef4b": {
            "max_retake_count": 4,
            "evolution": {
                "1": {
                    "retake": {
                        "count": 80,
                        "frames": 7900,
                        "drawings": 8000
                    },
                    "done": {
                        "count": 117,
                        "frames": 3900,
                        "drawings": 8000
                    }
                },
                "2": {
                    ...
                },
                "3": {
                    ...
                },
                "4": {
                    ...
                }
            },
            "done": {
                "count": 197,
                "frames": 16090,
                "drawings": 16090
            },
            "retake": {
                "count": 0,
                "frames": 0,
                "drawings": 0
            },
            "other": {
                "count": 5,
                "frames": 185,
                "drawings": 185
            }

        },
    """
    results = {"all": {"all": copy.deepcopy(DEFAULT_RETAKE_STATS)}}
    query = _get_retake_stats_query(project_id, only_assigned)
    query_results = query.all()
    for (
        episode_id,
        nb_drawings,
        nb_frames,
        task_type_id,
        retake_count,
        is_done,
        is_retake,
    ) in query_results:
        episode_id = str(episode_id)
        task_type_id = str(task_type_id)

        _init_entries(results, episode_id, task_type_id)
        results = _add_stats(
            results,
            episode_id,
            task_type_id,
            is_retake,
            is_done,
            retake_count,
            nb_frames,
            nb_drawings,
        )

    # A second loop is necessary: the evolution stats need the maximum
    # retake count of each entry before they start.
    for (
        episode_id,
        nb_drawings,
        nb_frames,
        task_type_id,
        retake_count,
        is_done,
        is_retake,
    ) in query_results:
        results = _add_evolution_stats(
            results,
            str(episode_id),
            str(task_type_id),
            is_retake,
            is_done,
            retake_count,
            nb_frames,
            nb_drawings,
        )
    return results


def _get_retake_stats_query(project_id, only_assigned):
    """
    Build the query for the retake stats. The query gives one row per task
    with these values:
    - the episode
    - the retake count
    - whether the status is done or retake.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    query = (
        Task.query.with_entities(
            Episode.id,
            Task.nb_drawings,
            Entity.nb_frames,
            Task.task_type_id,
            Task.retake_count,
            TaskStatus.is_done,
            TaskStatus.is_retake,
        )
        .join(Project, Project.id == Task.project_id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Sequence, Sequence.id == Entity.parent_id)
        .join(Episode, Episode.id == Sequence.parent_id)
        .join(TaskStatus, TaskStatus.id == Task.task_status_id)
        .filter(Project.id == project_id)
    )
    if only_assigned:
        query = query.filter(persons_service.build_assignee_filter())
    return query


def _init_entries(results, episode_id, task_type_id):
    """
    Make sure that the episode, the task type and their aggregates have a
    default entry. Do this before you add counts to them.
    """
    if episode_id not in results:
        results[episode_id] = {"all": copy.deepcopy(DEFAULT_RETAKE_STATS)}
    if task_type_id not in results["all"]:
        results["all"][task_type_id] = copy.deepcopy(DEFAULT_RETAKE_STATS)
    if task_type_id not in results[episode_id]:
        results[episode_id][task_type_id] = copy.deepcopy(DEFAULT_RETAKE_STATS)
    return results


def _add_stats(
    results,
    episode_id,
    task_type_id,
    is_retake,
    is_done,
    retake_count,
    nb_frames,
    nb_drawings,
):
    """
    Add one task to the current stats, at the four aggregation levels
    (all/all, all/task type, episode/all, episode/task type).
    """
    for key1, key2 in [
        ("all", "all"),
        ("all", task_type_id),
        (episode_id, "all"),
        (episode_id, task_type_id),
    ]:
        # This loop calculates the aggregated "current" statistics.
        # They show the present state of the production.

        entry = results[key1][key2]
        if entry["max_retake_count"] < retake_count:
            entry["max_retake_count"] = retake_count

        # For the "current" stats, `is_done` has priority over `is_retake`.
        if is_done:
            key = "done"
        elif is_retake:
            key = "retake"
        else:
            key = "other"
        _add_to_bucket(entry[key], 1, nb_frames, nb_drawings)
    return results


def _add_evolution_stats(
    results,
    episode_id,
    task_type_id,
    is_retake,
    is_done,
    retake_count,
    nb_frames,
    nb_drawings,
):
    """
    Add one task to the evolution stats. For each take number up to the
    maximum, these stats show the state of the production at that take.
    """
    for key1, key2 in [(episode_id, "all"), (episode_id, task_type_id)]:
        # This loop calculates the "evolution" statistics.
        # They show the changes of the production over time.
        max_retake_count = results[key1][key2]["max_retake_count"]
        evolution_data = results[key1][key2]["evolution"]
        # A task counts as a retake at each take up to its retake count. At
        # the later takes, it counts as done or other. is_retake is not used.
        for i in range(1, max_retake_count + 1):
            take_number = str(i)
            if take_number not in evolution_data:
                evolution_data[take_number] = copy.deepcopy(
                    DEFAULT_EVOLUTION_STATS
                )
            if retake_count > 0 and i <= retake_count:
                key = "retake"
            elif is_done:
                key = "done"
            else:
                key = "other"
            _add_to_bucket(
                evolution_data[take_number][key], 1, nb_frames, nb_drawings
            )
    return results
