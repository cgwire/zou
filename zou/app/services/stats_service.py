import copy
from sqlalchemy import func

from sqlalchemy.orm import aliased

from zou.app.models.entity import Entity
from zou.app.models.comment import Comment
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus

from zou.app.services import (
    user_service
)


DEFAULT_RETAKE_STATS = {
    "max_retake_count": 0,
    "evolution": {},
    "done": {
        "count": 0,
        "frames": 0,
    },
    "retake": {
        "count": 0,
        "frames": 0,
    },
    "other": {
        "count": 0,
        "frames": 0,
    }
}


DEFAULT_EVOLUTION_STATS = {
    "done": {"count": 0, "frames": 0},
    "retake": {"count": 0, "frames": 0},
    "other": {"count": 0, "frames": 0},
}


def get_main_stats():
    return {
        "number_of_video_previews":
            PreviewFile.query.filter(PreviewFile.extension == "mp4").count(),
        "number_of_picture_previews":
            PreviewFile.query.filter(PreviewFile.extension == "png").count(),
        "number_of_model_previews":
            PreviewFile.query.filter(PreviewFile.extension == "obj").count(),
        "number_of_comments":
            Comment.query.count()
    }


def get_episode_stats_for_project(project_id, only_assigned=False):
    """
    Retrieve number of tasks by status, task_types and episodes
    for given project.
    """

    results = {}
    episode_counts = _get_episode_counts(project_id, only_assigned)
    for data in episode_counts:
        add_entry_to_stats(results, *data)
        add_entry_to_all_stats(results, *data)
    return results


def _get_episode_counts(project_id, only_assigned=False):
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
        .add_columns(func.sum(Entity.nb_frames))
    )

    if only_assigned:
        query = query.filter(user_service.build_assignee_filter())

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
    entity_nb_frames,
):
    """
    Add to stats results, information of given count for given entity, task
    type and task satus.
    """
    episode_id = str(episode_id)
    task_type_id = str(task_type_id)
    task_status_id = str(task_status_id)
    results.setdefault(episode_id, {})
    results[episode_id].setdefault(task_type_id, {})
    results[episode_id][task_type_id].setdefault(task_status_id, {})
    results[episode_id][task_type_id][task_status_id] = {
        "name": task_status_short_name,
        "color": task_status_color,
        "count": task_count,
        "frames": entity_nb_frames or 0,
    }

    # Aggregate for episode
    results[episode_id].setdefault("all", {})
    results[episode_id]["all"].setdefault(
        task_status_id,
        {
            "name": task_status_short_name,
            "color": task_status_color,
            "count": 0,
            "frames": 0,
        },
    )
    results[episode_id]["all"][task_status_id]["count"] += task_count or 0
    results[episode_id]["all"][task_status_id]["frames"] += (
        entity_nb_frames or 0
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
    entity_nb_frames,
):
    """
    Add to aggregated entry of stats results, information of given count for
    given entity, task type and task satus.
    """
    task_type_id = str(task_type_id)
    task_status_id = str(task_status_id)
    results.setdefault("all", {"all": {}})

    results["all"].setdefault(task_type_id, {})
    results["all"][task_type_id].setdefault(
        task_status_id,
        {
            "name": task_status_short_name,
            "color": task_status_color,
            "count": 0,
            "frames": 0,
        },
    )
    results["all"][task_type_id][task_status_id]["count"] += task_count or 0
    results["all"][task_type_id][task_status_id]["frames"] += (
        entity_nb_frames or 0
    )

    results["all"]["all"].setdefault(
        task_status_id,
        {
            "name": task_status_short_name,
            "color": task_status_color,
            "count": 0,
            "frames": 0,
        },
    )
    results["all"]["all"][task_status_id]["count"] += task_count or 0
    results["all"]["all"][task_status_id]["frames"] += entity_nb_frames or 0


def get_episode_retake_stats_for_project(project_id, only_assigned=False):
    """
    Retrieve number of retakes and done tasks by task_types and episodes for
    given project. It gives the max retake count by episode too and show
    the evolution of the number of retakes. The result is returned a dict.
    Exemple of entry returned:
        "1dcdc0f2-8aa1-4267-b56d-7621d86eef4b": {
            "max_retake_count": 4,
            "evolution": {
                "1": {
                    "retake": {
                        "count": 80,
                        "frames": 7900
                    },
                    "done": {
                        "count": 117,
                        "frames": 3900
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
                "frames": 16090
            },
            "retake": {
                "count": 0,
                "frames": 0
            },
            "other": {
                "count": 5,
                "frames": 185
            }

        },
    """
    results = {
        "all": {"all":  copy.deepcopy(DEFAULT_RETAKE_STATS)}
    }
    query = _get_retake_stats_query(project_id, only_assigned)
    query_results = query.all()
    for (
        episode_id,
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
            str(episode_id),
            str(task_type_id),
            is_retake,
            is_done,
            retake_count,
            nb_frames
        )

    # Another loop is needed because we need to know the max retake count
    # for each entries prior to build evolution stats.
    for (
        episode_id,
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
            nb_frames
        )
    return results


def _get_retake_stats_query(project_id, only_assigned):
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    query = (
        Task.query.with_entities(
            Episode.id,
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
        query = query.filter(user_service.build_assignee_filter())
    return query


def _init_entries(results, episode_id, task_type_id):
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
    nb_frames
):
    for (key1, key2) in [
        ("all", "all"),
        ("all", task_type_id),
        (episode_id, "all"),
        (episode_id, task_type_id),
    ]:
        # In this loop we compute the aggregated "current" statistics.
        # They represent the present state of the production

        if results[key1][key2]["max_retake_count"] < retake_count:
            results[key1][key2]["max_retake_count"] = retake_count

        if is_done:
            # For the "current" stats we prioritize `is_done` over `is_retake`
            results[key1][key2]["done"]["count"] += 1
            results[key1][key2]["done"]["frames"] += nb_frames or 0
        elif is_retake:
            results[key1][key2]["retake"]["count"] += 1
            results[key1][key2]["retake"]["frames"] += nb_frames or 0
        else:
            results[key1][key2]["other"]["count"] += 1
            results[key1][key2]["other"]["frames"] += nb_frames or 0
    return results


def _add_evolution_stats(
    results,
    episode_id,
    task_type_id,
    is_retake,
    is_done,
    retake_count,
    nb_frames
):
    for (key1, key2) in [(episode_id, "all"), (episode_id, task_type_id)]:
        # In this loop we compute the "evolution" statistics
        # They represent the dynamics of the production
        max_retake_count = results[key1][key2]["max_retake_count"]
        evolution_data = results[key1][key2]["evolution"]
        # Note that tasks can have both `is_done` and `is_retake` values:
        # We simply count them twice in two different takes
        # (at take `retake_count` and take `retake_count+1`).
        for i in range(1, max_retake_count + 1):
            take_number = str(i)
            if take_number not in evolution_data:
                evolution_data[take_number] = \
                    copy.deepcopy(DEFAULT_EVOLUTION_STATS)
            if retake_count > 0 and i <= retake_count:
                evolution_data[take_number]["retake"]["count"] += 1
                evolution_data[take_number]["retake"]["frames"] += \
                    nb_frames or 0
            elif is_done:
                evolution_data[take_number]["done"]["count"] += 1
                evolution_data[take_number]["done"]["frames"] += \
                    nb_frames or 0
            else:
                evolution_data[take_number]["other"]["count"] += 1
                evolution_data[take_number]["other"]["frames"] += \
                    nb_frames or 0
    return results
