"""
Untracked items are the work planned in the production schedule that is
not an asset, a shot or an edit: sound design, a department planned before
its shots exist... They carry tasks like any entity, but stay out of the
asset, shot and edit lists.

An untracked item can be linked to an episode, a sequence or a shot through
its parent, so a rough plan can be made more precise once the breakdown is
known.
"""

import random

from zou.app.exceptions import (
    UntrackedNotFoundException,
    WrongParameterException,
)
from zou.app.models.entity import Entity
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    base_service,
    departments_service,
    entities_service,
    projects_service,
    task_types_service,
    tasks_service,
)
from zou.app.services.entity_types_service import (
    get_episode_type,
    get_sequence_type,
    get_shot_type,
    get_untracked_type,
)
from zou.app.utils import events

# The colours of the task type colour picker of Kitsu, without its greys
# and its palest yellows: an untracked item without department takes one at
# random, so that its row stands out from the others.
COLORS = [
    "#009688",
    "#33B378",
    "#7CB342",
    "#43A047",
    "#8D6E63",
    "#AFB42B",
    "#9CCC65",
    "#FFEB3B",
    "#F9A825",
    "#F57C00",
    "#FF5252",
    "#F06292",
    "#AB47BC",
    "#5C6BC0",
    "#1976D2",
    "#039BE5",
    "#42A5F5",
    "#64B5F6",
    "#26C6DA",
]


def get_untracked_raw(untracked_id):
    """
    Return given untracked item as an active record.
    """
    return base_service.get_typed_instance(
        Entity,
        untracked_id,
        get_untracked_type()["id"],
        UntrackedNotFoundException,
    )


def get_untracked(untracked_id):
    """
    Return given untracked item as a dictionary.
    """
    return get_untracked_raw(untracked_id).serialize(obj_type="Untracked")


def get_untracked_for_project(project_id):
    """
    Retrieve all untracked items of given project, sorted by name. Each item
    carries the episode it belongs to through its link, if any, and the
    readable path of that link (E01 / SQ01 / SH010).
    """
    untracked_items = entities_service.get_entities_for_project(
        project_id, get_untracked_type()["id"], "Untracked"
    )
    parent_ids = {
        item["parent_id"] for item in untracked_items if item["parent_id"]
    }
    link_map = _get_link_map(parent_ids)
    for item in untracked_items:
        episode_id, link_name = link_map.get(item["parent_id"], (None, None))
        item["episode_id"] = episode_id
        item["link_name"] = link_name
    return untracked_items


def _get_link_map(entity_ids):
    """
    Map each given episode, sequence or shot id to the id of the episode it
    belongs to (None for a sequence or a shot outside any episode) and to
    its readable path, from the episode down.
    """
    episode_type_id = get_episode_type()["id"]
    walkable_type_ids = (get_sequence_type()["id"], get_shot_type()["id"])
    entities = {}
    to_load = set(entity_ids)
    # Shot -> sequence -> episode: three loads reach the top.
    for _ in range(3):
        if not to_load:
            break
        for entity in Entity.query.filter(Entity.id.in_(to_load)).all():
            entities[str(entity.id)] = entity
        to_load = {
            str(entity.parent_id)
            for entity in entities.values()
            if entity.parent_id is not None
            and str(entity.parent_id) not in entities
        }

    def resolve(entity_id):
        names = []
        entity = entities.get(entity_id)
        while entity is not None:
            names.insert(0, entity.name)
            entity_type_id = str(entity.entity_type_id)
            if entity_type_id == episode_type_id:
                return str(entity.id), " / ".join(names)
            if (
                entity_type_id not in walkable_type_ids
                or entity.parent_id is None
            ):
                break
            entity = entities.get(str(entity.parent_id))
        return None, " / ".join(names) or None

    return {entity_id: resolve(entity_id) for entity_id in entity_ids}


def check_link(project_id, parent_id):
    """
    Raise if given parent cannot be the link of an untracked item of given
    project: it has to be one of its episodes, sequences or shots.
    """
    if parent_id is None:
        return
    parent = entities_service.get_entity(parent_id)
    allowed_type_ids = {
        get_episode_type()["id"],
        get_sequence_type()["id"],
        get_shot_type()["id"],
    }
    if (
        parent["project_id"] != str(project_id)
        or parent["entity_type_id"] not in allowed_type_ids
    ):
        raise WrongParameterException(
            "An untracked item can only be linked to an episode, a sequence "
            "or a shot of its project."
        )


def create_untracked(
    project_id,
    name,
    description="",
    parent_id=None,
    data=None,
    created_by=None,
):
    """
    Create an untracked item for given project, linked to given episode,
    sequence or shot when one is named. An item already carrying this name
    and link is returned as is.
    """
    check_link(project_id, parent_id)
    untracked_type = get_untracked_type()
    untracked = Entity.get_by(
        entity_type_id=untracked_type["id"],
        project_id=project_id,
        parent_id=parent_id,
        name=name,
    )
    if untracked is None:
        untracked = Entity.create(
            entity_type_id=untracked_type["id"],
            project_id=project_id,
            parent_id=parent_id,
            name=name,
            description=description,
            data=data or {},
            created_by=created_by,
        )
        events.emit(
            "untracked:new",
            {"untracked_id": str(untracked.id), "parent_id": parent_id},
            project_id=str(project_id),
        )
    return untracked.serialize(obj_type="Untracked")


def update_untracked(untracked_id, data):
    """
    Update the name, the description or the link of given untracked item.
    Passing parent_id None removes the link.
    """
    untracked = get_untracked_raw(untracked_id)
    if "parent_id" in data:
        check_link(untracked.project_id, data["parent_id"])
    name = data.get("name", untracked.name)
    parent_id = data.get("parent_id", untracked.parent_id)
    namesake = Entity.get_by(
        entity_type_id=untracked.entity_type_id,
        project_id=untracked.project_id,
        parent_id=parent_id,
        name=name,
    )
    if namesake is not None and namesake.id != untracked.id:
        raise WrongParameterException(
            "An untracked item with this name and link already exists."
        )
    previous_name = untracked.name
    untracked.update(data)
    entities_service.clear_entity_cache(untracked_id)
    if untracked.name != previous_name:
        _rename_untracked_tasks(untracked)
    events.emit(
        "untracked:update",
        {"untracked_id": str(untracked.id)},
        project_id=str(untracked.project_id),
    )
    return untracked.serialize(obj_type="Untracked")


def _rename_untracked_tasks(untracked):
    """
    Move the tasks of given untracked item to the task type of its new name,
    which keeps the department and the colour of the former one. The former
    task type stays as is: the items of the same name in other productions
    may still use it.
    """
    tasks = Task.query.filter_by(entity_id=untracked.id).all()
    for task in tasks:
        task_type = task_types_service.get_task_type(str(task.task_type_id))
        if task_type["for_entity"] == "Untracked":
            new_task_type = get_or_create_untracked_task_type(
                untracked.name,
                task_type["department_id"],
                task_type["color"],
            )
            if new_task_type["id"] != task_type["id"]:
                projects_service.add_task_type_setting(
                    str(untracked.project_id), new_task_type["id"]
                )
                tasks_service.update_task(
                    str(task.id), {"task_type_id": new_task_type["id"]}
                )


def unlink_untracked_items(parent_id):
    """
    Link to nothing the untracked items linked to given episode, sequence or
    shot, so that it can be deleted: they then belong to the whole
    production.
    """
    items = Entity.get_all_by(
        entity_type_id=get_untracked_type()["id"], parent_id=parent_id
    )
    for item in items:
        item.update({"parent_id": None})
        entities_service.clear_entity_cache(str(item.id))
        events.emit(
            "untracked:update",
            {"untracked_id": str(item.id)},
            project_id=str(item.project_id),
        )


def get_or_create_untracked_task_type(name, department_id=None, color=None):
    """
    Return the task type an untracked item is planned with, creating it
    when needed. Being untracked is a state of the work, not a kind of it:
    the task type carries the name of the item ("Sound design"). Its colour
    is the given one, else the one of its department, else a random one.
    An untracked task type of the same name and department is reused, so
    the items of the same name in other productions share it, and it keeps
    its colour: changing it would change their rows too. Task type names are unique regardless of case:
    when another task type already takes the name, the department name, or
    "untracked", is added to it.
    """
    department = None
    if department_id is not None:
        department = departments_service.get_department(department_id)
    name = name[:40]
    suffix = department["name"] if department else "untracked"
    candidates = [name, f"{name[: 37 - len(suffix[:20])]} ({suffix[:20]})"]
    for candidate in candidates:
        task_type = TaskType.get_by_case_insensitive(name=candidate)
        if task_type is None:
            return _create_untracked_task_type(candidate, department, color)
        if task_type.for_entity == "Untracked" and str(
            task_type.department_id or ""
        ) == str(department_id or ""):
            return task_type.serialize()
    raise WrongParameterException(
        "A task type already takes the name of this untracked item."
    )


def _create_untracked_task_type(name, department=None, color=None):
    """
    Create an untracked task type of given name, with given colour, else
    the one of given department, else a random one.
    """
    if color is None:
        color = department["color"] if department else random.choice(COLORS)
    task_type = TaskType.create(
        name=name,
        short_name=name[:3].upper(),
        color=color,
        for_entity="Untracked",
        department_id=department["id"] if department else None,
    )
    task_types_service.clear_task_type_cache(str(task_type.id))
    events.emit("task-type:new", {"task_type_id": str(task_type.id)})
    return task_type.serialize()


def create_untracked_task(untracked, department_id=None, color=None):
    """
    Create the task of given untracked item, with a task type named after
    it and given colour, which is enabled in the production of the item if
    it is not yet. Return the created task, or the existing one when the
    item already has it, so that creating the item again plans it again.
    """
    task_type = get_or_create_untracked_task_type(
        untracked["name"], department_id, color
    )
    projects_service.add_task_type_setting(
        untracked["project_id"], task_type["id"]
    )
    tasks = tasks_service.create_tasks_for_entity(untracked, [task_type])
    if not tasks:
        tasks = [
            task
            for task in tasks_service.get_tasks_for_entity_and_task_type(
                untracked["id"], task_type["id"]
            )
            if task["name"] == "main"
        ]
    return tasks
