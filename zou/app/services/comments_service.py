import re
import uuid

from flask import current_app
from sqlalchemy import and_
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func

from zou.app import db
from zou.app.exceptions import (
    AssetNotFoundException,
    CommentNotFoundException,
    PreviewFileNotFoundException,
    ReplyNotFoundException,
    TaskStatusNotFoundException,
    TaskTypeNotFoundException,
    TooManyPreviewFilesException,
    WrongParameterException,
)
from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import (
    Comment,
    CommentPreviewLink,
    acknowledgements_table,
    department_mentions_table,
    mentions_table,
)
from zou.app.models.department import Department
from zou.app.models.news import News
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project, ProjectPersonLink
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.services import (
    assets_service,
    attachment_files_service,
    breakdown_service,
    entities_service,
    entity_types_service,
    files_service,
    news_service,
    notifications_service,
    persons_service,
    preview_file_states_service,
    preview_files_service,
    projects_service,
    status_automations_service,
    task_types_service,
    tasks_service,
)
from zou.app.stores import file_store, redis_lock
from zou.app.utils import (
    cache,
    date_helpers,
    events,
    fields,
    query as query_utils,
)

# A chain of status automations stops after this number of nested automation
# comments. This stops a cycle that the fired set does not find, or a chain
# that does not end.
MAX_AUTOMATION_DEPTH = 10

# Raster image types that are safe to show inline. With the global
# X-Content-Type-Options: nosniff header, the browser uses the declared type.
# It does not sniff a disguised HTML payload into an executable document.
# image/svg+xml is not in this list on purpose: an SVG can contain scripts, and
# these scripts run in the origin of Kitsu (stored XSS).
INLINE_SAFE_MIMETYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/avif",
}


def is_inline_safe_mimetype(mimetype):
    """
    Return True if an attachment with this mimetype can be served inline (shown
    in the browser). Otherwise, the attachment is sent as a download.
    """
    if not mimetype:
        return False
    return mimetype.split(";")[0].strip().lower() in INLINE_SAFE_MIMETYPES


def create_comment(
    person_id,
    task_id,
    task_status_id,
    text,
    checklist=None,
    files=None,
    created_at="",
    links=None,
    with_hashtags=True,
    for_client=False,
    posted_comments=None,
    _fired_automations=None,
    _automation_depth=0,
):
    """
    Create a new comment and the related news, notifications and events.

    A batch gives posted_comments: the set of the (task id string, text) pairs
    that it posts. The hashtags do not post a text again on a task that the set
    pairs with this text. They add the pairs of their new posts to the set.

    The two private arguments send a cascade of status automations to the
    comments that the automations post. Callers do not give them.
    """
    if checklist is None:
        checklist = []
    if files is None:
        files = {}
    if links is None:
        links = []
    author = _get_comment_author(person_id)
    task = tasks_service.get_task(task_id, relations=True)
    task_status = task_types_service.get_task_status(task_status_id)
    task_type = task_types_service.get_task_type(task["task_type_id"])
    _check_retake_capping(task_status, task, created_at)

    comment = new_comment(
        task_id=task_id,
        object_type="Task",
        files=files,
        person_id=author["id"],
        task_status_id=task_status_id,
        text=text,
        checklist=checklist,
        created_at=created_at,
        links=links,
        for_client=for_client,
    )

    if with_hashtags:
        _handle_hashtags(author, task_type, task, text, posted_comments)

    # Read the value from the row: get_task is memoized, and a sync import
    # updates the row but does not remove that cache entry.
    previous_task_status_id = str(
        tasks_service.get_task_raw(task_id).task_status_id
    )
    task, status_changed = _manage_status_change(task_status, task, comment)
    _manage_subscriptions(task, comment, status_changed)
    comment["task_status"] = task_status
    comment["person"] = author

    _run_status_automations(
        task,
        previous_task_status_id,
        person_id,
        set() if _fired_automations is None else _fired_automations,
        _automation_depth,
    )
    return comment


def _handle_hashtags(person, task_type, task, text, posted_comments=None):
    """
    Post the same comment on the sibling tasks that the hashtags of the text
    name. Thus a supervisor can send a comment to many task types at one time.

    If posted_comments is given, it is a mutable set of the (task id string,
    text) pairs that a batch posts. If the set pairs a sibling with this text,
    do not post on that sibling. Add the pairs of the new posts to the set.
    """
    hashtags = get_comment_hashtags(text)
    if len(hashtags) > 0:
        entity = entities_service.get_entity(entity_id=task["entity_id"])
        tasks = tasks_service.get_entity_tasks(entity)
        tasks = filter_tasks_by_hashtags(tasks, hashtags, task_type)
        if posted_comments is not None:
            tasks = [
                _task
                for _task in tasks
                if (str(_task["id"]), text) not in posted_comments
            ]
            posted_comments.update((str(_task["id"]), text) for _task in tasks)
        if len(tasks) > 0:
            status_ids = set(t["task_status_id"] for t in tasks)
            statuses_map = {
                str(s.id): s.serialize()
                for s in TaskStatus.query.filter(
                    TaskStatus.id.in_(list(status_ids))
                ).all()
            }
            for _task in tasks:
                task_status = statuses_map.get(
                    str(_task["task_status_id"]), {}
                )
                create_comment(
                    person_id=person["id"],
                    task_id=_task["id"],
                    text=text + f"\n\n____\nFrom {task_type['name']} task",
                    task_status_id=task_status.get("id"),
                    with_hashtags=False,
                )
    return hashtags


def _check_retake_capping(task_status, task, created_at=None):
    """
    Raise an exception if a retake goes above the cap. If the entity sets a
    cap, read the cap on the entity. Otherwise, read it on the project. A cap
    of zero means no cap. A comment dated now that keeps the task on that
    status adds no retake: the cap does not apply. A comment with its own date
    can come before other comments. Then the replay of the history can count
    one more retake.
    """
    adds_no_retake = (
        task_status["id"] == task["task_status_id"] and not created_at
    )
    if task_status["is_retake"] and not adds_no_retake:
        project = projects_service.get_project(task["project_id"])
        project_max_retakes = project["max_retakes"] or 0
        if project_max_retakes > 0:
            entity = entities_service.get_entity(task["entity_id"])
            entity_data = entity.get("data", {}) or {}
            entity_max_retakes = entity_data.get("max_retakes", None)
            max_retakes = int(entity_max_retakes or project["max_retakes"])
            if task["retake_count"] >= max_retakes and max_retakes > 0:
                raise WrongParameterException(
                    "No more retakes allowed on this task"
                )
    return True


def _get_comment_author(person_id):
    """
    Return the author of the comment: the given person, or the current user if
    no id is given.
    """
    if person_id is not None and person_id != "":
        person = persons_service.get_person(person_id)
    else:
        person = persons_service.get_current_user()
    return person


def _manage_status_change(task_status, task, comment):
    """
    Apply the status of the comment to its task. Return the task and whether
    the status changed.

    If the date of the comment is older than the date of the last comment, the
    task does not move. The function replays all the history. Thus an import of
    old comments cannot move a task back.
    """
    is_last_comment = (
        task["last_comment_date"] is None
        or task["last_comment_date"] <= comment["created_at"]
    )
    if not is_last_comment:
        status_changed = False
        task = tasks_service.reset_task_data(task["id"])
    else:
        status_changed = task_status["id"] != task["task_status_id"]
        new_data = {
            "task_status_id": task_status["id"],
            "last_comment_date": comment["created_at"],
        }
        if status_changed:
            if task_status["is_retake"]:
                retake_count = task["retake_count"]
                if retake_count is None:
                    retake_count = 0
                new_data["retake_count"] = retake_count + 1

            # update_task sets the end date and the done date, because it owns
            # that policy. It also resets them when a task leaves a feedback
            # status or a done status.

            if task_status["is_wip"] and task["real_start_date"] is None:
                # Use naive UTC, like all other stored datetimes. The server
                # session timezone converts an aware value when it goes into a
                # timestamp without time zone column.
                new_data["real_start_date"] = (
                    date_helpers.get_utc_now_datetime()
                )

        tasks_service.update_task(task["id"], new_data)

        if status_changed:
            events.emit(
                "task:status-changed",
                {
                    "task_id": task["id"],
                    "new_task_status_id": new_data["task_status_id"],
                    "previous_task_status_id": task["task_status_id"],
                    "person_id": comment["person_id"],
                },
                project_id=task["project_id"],
            )
            if task_status["is_feedback_request"]:
                # Backward compatibility: the legacy
                # /actions/tasks/<id>/to-review endpoint emitted task:to-review
                # each time a task moved to a feedback-request status. Modern
                # Kitsu posts a comment with the new task_status_id. Thus we
                # emit the event again here, so that the existing gazu
                # listeners continue to work.
                events.emit(
                    "task:to-review",
                    {
                        "task_id": task["id"],
                        "new_task_status_id": new_data["task_status_id"],
                        "previous_task_status_id": task["task_status_id"],
                        "person_id": comment["person_id"],
                        "comment_id": comment["id"],
                    },
                    project_id=task["project_id"],
                )
        task.update(new_data)
    return task, status_changed


def _manage_subscriptions(task, comment, status_changed):
    """
    Notify the people who follow the task, and add news to the news stream.
    Concepts are not in the news stream on purpose.
    """
    notifications_service.create_notifications_for_task_and_comment(
        task, comment, change=status_changed
    )
    if (
        entities_service.get_entity(task["entity_id"])["entity_type_id"]
        != entity_types_service.get_concept_type()["id"]
    ):
        news_service.create_news_for_task_and_comment(
            task,
            comment,
            created_at=comment["created_at"],
            change=status_changed,
        )


def _run_status_automations(
    task, previous_task_status_id, person_id, fired_automations, depth
):
    """
    Run the status automations of the project of the task after a comment.

    - Only a status change can fire an automation. An automation fires when the
      change makes its trigger go from false to true.
    - The decision for all automations uses the tasks as the change leaves
      them, before any automation applies its change. Thus no decision uses the
      change of another automation.
    - Then the automations apply in their creation order. On a shared target,
      each automation finds the values of the previous ones, and its target
      guard reads these values.
    - If an automation fails, the comment does not fail: it is already saved.

    The comments that automations post run the automations again. In one user
    action, an automation applies its change one time per entity at most. The
    chain stops after MAX_AUTOMATION_DEPTH nested comments.
    """
    if str(task["task_status_id"]) == previous_task_status_id:
        return
    candidates = []
    for automation in projects_service.get_project_status_automations(
        task["project_id"]
    ):
        trigger = None
        if not automation["archived"]:
            trigger = status_automations_service.get_trigger(automation)
        if trigger is not None and any(
            condition["task_type_id"] == task["task_type_id"]
            for condition in trigger["conditions"]
        ):
            candidates.append((automation, trigger))
    if len(candidates) == 0:
        return

    try:
        fired = _get_fired_status_automations(
            candidates, task, previous_task_status_id, depth
        )
    except Exception:
        db.session.rollback()
        current_app.logger.error(
            f"Status automations failed on task {task['id']}", exc_info=True
        )
        return
    for automation, trigger, conditions, tasks_by_type in fired:
        try:
            _apply_status_automation(
                automation,
                trigger,
                conditions,
                task,
                tasks_by_type,
                person_id,
                fired_automations,
                depth,
            )
        except WrongParameterException as exception:
            # A check refused the change before any write, for example the
            # retake cap of the target task.
            current_app.logger.warning(
                f"Status automation {automation['id']} skipped: {exception}"
            )
        except Exception:
            db.session.rollback()
            current_app.logger.error(
                f"Status automation {automation['id']} failed on task "
                f"{task['id']}",
                exc_info=True,
            )


def _is_automation_for_entity_type(automation, entity_type):
    wanted = (automation.get("entity_type") or "").lower()
    if wanted == "asset":
        return entity_types_service.is_asset_type(entity_type)
    return entity_type["name"].lower() == wanted


def _get_fired_status_automations(
    candidates, task, previous_task_status_id, depth
):
    """
    Return the candidate automations that the status change of the given task
    fires. Each automation comes with its conditions, as the runner reads them,
    and with the tasks of its decision. These tasks are read one time, as the
    change leaves them. "before" puts back the previous status of the task.
    """
    entity = entities_service.get_entity(task["entity_id"])
    entity_type = entity_types_service.get_entity_type(
        entity["entity_type_id"]
    )
    candidates = [
        (automation, trigger)
        for automation, trigger in candidates
        if _is_automation_for_entity_type(automation, entity_type)
    ]
    if len(candidates) == 0:
        return []
    priority_maps = {}
    triggered = []
    for automation, trigger in candidates:
        conditions = _get_effective_conditions(
            automation,
            trigger,
            _get_priority_map(task["project_id"], automation, priority_maps),
        )
        if any(
            condition["is_trigger"]
            and condition["task_type_id"] == task["task_type_id"]
            for condition in conditions
        ):
            triggered.append((automation, trigger, conditions))
    if len(triggered) == 0:
        return []

    tasks_by_type = _get_condition_tasks(
        task["entity_id"],
        [
            condition
            for _, _, conditions in triggered
            for condition in conditions
        ],
    )
    previous_statuses = {task["id"]: previous_task_status_id}
    fired = [
        (automation, trigger, conditions, tasks_by_type)
        for automation, trigger, conditions in triggered
        if _is_trigger_met(trigger["operator"], conditions, tasks_by_type, {})
        and not _is_trigger_met(
            trigger["operator"], conditions, tasks_by_type, previous_statuses
        )
    ]
    if len(fired) > 0 and depth >= MAX_AUTOMATION_DEPTH:
        current_app.logger.warning(
            f"Status automations stopped on task {task['id']}: "
            f"{MAX_AUTOMATION_DEPTH} chained automation comments reached."
        )
        return []
    return fired


def _apply_status_automation(
    automation,
    trigger,
    conditions,
    task,
    tasks_by_type,
    person_id,
    fired_automations,
    depth,
):
    """
    Apply the change of an automation that the status change of the given task
    fired.
    """
    if automation["out_field_type"] == "status":
        _apply_status_change(
            automation,
            trigger,
            conditions,
            task,
            tasks_by_type,
            person_id,
            fired_automations,
            depth,
        )
    elif automation["out_field_type"] == "ready_for":
        if _record_fire(automation, task, fired_automations):
            try:
                asset = assets_service.update_asset(
                    task["entity_id"],
                    {"ready_for": automation["out_task_type_id"]},
                )
                breakdown_service.refresh_casting_stats(asset)
            except AssetNotFoundException:
                pass


def _record_fire(automation, task, fired_automations):
    """
    Record that the given automation applies its change on the entity of the
    task. If it already did for this user action, return False: this is a
    cycle, and it stops there.
    """
    fired_key = (automation["id"], task["entity_id"])
    if fired_key in fired_automations:
        current_app.logger.warning(
            f"Status automation {automation['id']} already fired on entity "
            f"{task['entity_id']} for this action: cycle stopped."
        )
        return False
    fired_automations.add(fired_key)
    return True


def _get_effective_conditions(automation, trigger, priorities):
    """
    Return the conditions of a trigger as the runner reads them.

    With a status output, a condition can be on a task type that comes after
    the output in the production: a strictly higher priority, where a missing
    priority counts as 0. This condition never fires the automation, to prevent
    change cycles. Under "and", the condition must still be met. Under "or", it
    is removed: when it is met, it keeps the trigger met and blocks all other
    changes. If a task type does not exist anymore, its condition is false. If
    a status does not exist anymore, it is removed from its condition.
    """
    is_status_output = automation["out_field_type"] != "ready_for"
    out_priority = priorities.get(automation["out_task_type_id"], 0) or 0
    conditions = []
    for condition in trigger["conditions"]:
        task_type_id = condition["task_type_id"]
        is_guard_only = (
            is_status_output
            and (priorities.get(task_type_id, 0) or 0) > out_priority
        )
        if not is_guard_only or trigger["operator"] == "and":
            conditions.append(
                {
                    "task_type_id": task_type_id,
                    "task_status_ids": {
                        task_status_id
                        for task_status_id in condition["task_status_ids"]
                        if _is_task_status(task_status_id)
                    },
                    "is_known": _is_task_type(task_type_id),
                    "is_trigger": not is_guard_only,
                }
            )
    return conditions


def _get_priority_map(project_id, automation, priority_maps):
    """
    Return the task type priorities that the given automation reads, as the
    single-condition runner did: the priorities of the task types for its
    entity type. An old row that names an asset type ("props") finds no
    priority. Thus it fires whatever the priorities are. ``priority_maps``
    keeps the maps that were already read.
    """
    for_entity = automation["entity_type"].capitalize()
    if for_entity not in priority_maps:
        priority_maps[for_entity] = (
            projects_service.get_task_type_priority_map(project_id, for_entity)
        )
    return priority_maps[for_entity]


def _is_task_type(task_type_id):
    try:
        task_types_service.get_task_type(task_type_id)
        return True
    except TaskTypeNotFoundException:
        return False


def _is_task_status(task_status_id):
    try:
        task_types_service.get_task_status(task_status_id)
        return True
    except TaskStatusNotFoundException:
        return False


def _get_condition_tasks(entity_id, conditions):
    """
    Return the tasks of the given entity for the task types of the conditions,
    grouped by task type and sorted by name.
    """
    task_type_ids = {
        condition["task_type_id"]
        for condition in conditions
        if condition["is_known"]
    }
    tasks_by_type = {}
    for task in (
        Task.query.filter(Task.entity_id == entity_id)
        .filter(Task.task_type_id.in_(task_type_ids))
        .order_by(Task.name)
    ):
        tasks_by_type.setdefault(str(task.task_type_id), []).append(
            {"id": str(task.id), "task_status_id": str(task.task_status_id)}
        )
    return tasks_by_type


def _is_trigger_met(operator, conditions, tasks_by_type, status_overrides):
    """
    Return True if a trigger is met. A condition is met when all tasks of its
    task type have one of its statuses. If the entity has no task of the task
    type of a condition, ignore that condition. If no condition is left, the
    trigger is not met.
    """
    values = []
    for condition in conditions:
        tasks = tasks_by_type.get(condition["task_type_id"], [])
        if not condition["is_known"]:
            values.append(False)
        elif len(tasks) > 0:
            values.append(
                all(
                    status_overrides.get(task["id"], task["task_status_id"])
                    in condition["task_status_ids"]
                    for task in tasks
                )
            )
    if len(values) == 0:
        return False
    return all(values) if operator == "and" else any(values)


def _apply_status_change(
    automation,
    trigger,
    conditions,
    task,
    tasks_by_type,
    person_id,
    fired_automations,
    depth,
):
    """
    Post the comment that moves the first task, by name, of the output task
    type to the output status. The author is the author of the comment that
    fired the automation. If the target guard refuses the task, or if the
    automation already fired on the entity, do not post it. If the automation
    asks for it, import the last revision of the source task into the new
    comment.
    """
    tasks_to_update = tasks_service.get_tasks_for_entity_and_task_type(
        task["entity_id"], automation["out_task_type_id"]
    )
    if len(tasks_to_update) == 0:
        return
    task_to_update = tasks_to_update[0]
    if not _is_target_status_allowed(automation, task_to_update):
        return
    if not _record_fire(automation, task, fired_automations):
        return
    new_comment = create_comment(
        person_id,
        task_to_update["id"],
        automation["out_task_status_id"],
        _get_automation_comment_text(trigger, conditions, task, tasks_by_type),
        [],
        {},
        None,
        _fired_automations=fired_automations,
        _automation_depth=depth + 1,
    )
    if automation["import_last_revision"]:
        _import_last_revision(
            _get_revision_source_task_id(
                trigger, conditions, task, tasks_by_type
            ),
            new_comment,
            task_to_update["id"],
        )


def _is_target_status_allowed(automation, task):
    """
    Return True if the target guard of an automation lets its change apply. If
    the guard lists statuses, the change applies only to a target task in one
    of them. Thus an automation does not overwrite the work in progress. A
    guard that is not a list counts as no guard, as Kitsu shows it and as a
    write reads it. Only a direct write can store such a guard.
    """
    allowed_task_status_ids = automation.get("out_only_if_task_status_ids")
    if allowed_task_status_ids is None:
        return True
    if not isinstance(allowed_task_status_ids, list):
        current_app.logger.warning(
            f"Status automation {automation['id']} has a malformed target "
            f"guard, read as none: {allowed_task_status_ids}"
        )
        return True
    allowed_ids = {
        str(task_status_id) for task_status_id in allowed_task_status_ids
    }
    return len(allowed_ids) == 0 or str(task["task_status_id"]) in allowed_ids


def _get_automation_comment_text(trigger, conditions, task, tasks_by_type):
    """
    Name the change that fired the automation. If all of several conditions
    must be met, name each condition that the entity has, in their order. Use
    the commented task for its own condition, and the first task by name for
    the other conditions.
    """
    if trigger["operator"] == "and" and len(trigger["conditions"]) > 1:
        changes = [
            _describe_status(
                condition["task_type_id"],
                (
                    task
                    if condition["task_type_id"] == task["task_type_id"]
                    else tasks[0]
                ),
            )
            for condition in conditions
            for tasks in [tasks_by_type.get(condition["task_type_id"], [])]
            if len(tasks) > 0
        ]
    else:
        changes = [_describe_status(task["task_type_id"], task)]
    return f"Change triggered by {' and '.join(changes)}"


def _describe_status(task_type_id, task):
    task_type = task_types_service.get_task_type(task_type_id)
    task_status = task_types_service.get_task_status(task["task_status_id"])
    return f"{task_type['name']} set to {task_status['name']}"


def _get_revision_source_task_id(trigger, conditions, task, tasks_by_type):
    """
    Return the task whose last revision the automation imports. Under "and",
    return the task of the first condition that the entity has. If the
    commented task is of that type, return the commented task. Under "or",
    return the commented task.
    """
    if trigger["operator"] == "and":
        for condition in conditions:
            tasks = tasks_by_type.get(condition["task_type_id"], [])
            if len(tasks) > 0:
                if condition["task_type_id"] == task["task_type_id"]:
                    return task["id"]
                return tasks[0]["id"]
    return task["id"]


def _import_last_revision(source_task_id, new_comment, task_id):
    preview_file = preview_files_service.get_last_preview_file_for_task(
        source_task_id
    )
    if preview_file is None:
        return
    for revision_file in preview_files_service.get_preview_files_for_revision(
        preview_file["task_id"], preview_file["revision"]
    ):
        new_preview_file = add_preview_file_to_comment(
            new_comment["id"], new_comment["person_id"], task_id
        )
        copy_preview_file_in_another_one(
            revision_file["id"], new_preview_file["id"]
        )


def new_comment(
    task_id,
    task_status_id,
    person_id,
    text,
    object_type="Task",
    files=None,
    checklist=None,
    created_at="",
    links=None,
    for_client=False,
):
    """
    Create a new comment for the given object, with its attachments. By
    default, the object is a Task. Emit comment:new and return the comment as a
    dict.
    """
    if files is None:
        files = {}
    if checklist is None:
        checklist = []
    if links is None:
        links = []
    created_at_date = None
    task = tasks_service.get_task(task_id)
    if created_at is not None and len(created_at) > 0:
        try:
            created_at_date = fields.get_date_object(
                created_at, date_format="%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            try:
                created_at_date = date_helpers.get_datetime_from_string(
                    created_at
                )
            except ValueError:
                pass

    comment = Comment.create(
        object_id=task_id,
        object_type=object_type,
        task_status_id=task_status_id,
        person_id=person_id,
        mentions=get_comment_mentions(task["project_id"], text),
        department_mentions=get_comment_department_mentions(text),
        checklist=checklist,
        text=text,
        created_at=created_at_date,
        links=links,
        for_client=for_client,
    )

    comment = comment.serialize(relations=True)
    add_attachments_to_comment(comment, files)
    events.emit(
        "comment:new",
        {
            "comment_id": comment["id"],
            "task_id": task_id,
            "task_status_id": task_status_id,
            "person_id": comment["person_id"],
            "for_client": comment["for_client"],
        },
        project_id=task["project_id"],
    )
    return comment


def move_comment_to_task(comment_id, target_task_id):
    """
    Move a comment from its current task to another task of the same entity.
    Keep the original creation date, text, attachments, mentions and status
    change of the comment. Remove the notifications and news of the comment on
    the source task, and create them again for the target task. Thus the
    watchers of the target task get notifications, as for a new comment.

    A comment tied to a preview revision (preview_file_id set or previews
    populated) cannot move: the previews stay attached to the task that owns
    the revision.
    """
    comment = get_comment_raw(comment_id)
    source_task = tasks_service.get_task(str(comment.object_id))
    target_task = tasks_service.get_task(target_task_id, relations=True)

    if str(source_task["id"]) == str(target_task["id"]):
        raise WrongParameterException(
            "Source and target tasks must be different."
        )
    if source_task["entity_id"] != target_task["entity_id"]:
        raise WrongParameterException(
            "A comment can only be moved between tasks of the same entity."
        )
    if comment.preview_file_id is not None or (
        comment.previews is not None and len(comment.previews) > 0
    ):
        raise WrongParameterException(
            "A comment attached to a preview revision cannot be moved."
        )

    Notification.delete_all_by(comment_id=comment.id)
    news_service.delete_news_for_comment(comment.id)

    comment.update({"object_id": target_task["id"]})
    clear_comment_cache(str(comment.id))

    tasks_service.reset_task_data(str(source_task["id"]))
    target_task = tasks_service.reset_task_data(str(target_task["id"]))

    comment_dict = comment.serialize(relations=True)

    events.emit(
        "comment:delete",
        {"comment_id": str(comment.id), "task_id": str(source_task["id"])},
        project_id=source_task["project_id"],
    )
    events.emit(
        "comment:new",
        {
            "comment_id": str(comment.id),
            "task_id": str(target_task["id"]),
            "task_status_id": comment_dict["task_status_id"],
            "person_id": comment_dict["person_id"],
            "for_client": comment_dict["for_client"],
        },
        project_id=target_task["project_id"],
    )

    notifications_service.create_notifications_for_task_and_comment(
        target_task, comment_dict, change=False
    )
    if (
        entities_service.get_entity(target_task["entity_id"])["entity_type_id"]
        != entity_types_service.get_concept_type()["id"]
    ):
        news_service.create_news_for_task_and_comment(
            target_task,
            comment_dict,
            created_at=comment_dict["created_at"],
        )

    return comment_dict


def reset_mentions(comment):
    """
    Find again, from its text, the people and departments that a comment
    mentions.
    """
    task = tasks_service.get_task(comment["object_id"])
    mentions = get_comment_mentions(task["project_id"], comment["text"])
    department_mentions = get_comment_department_mentions(comment["text"])
    comment_to_update = Comment.get(comment["id"])
    comment_to_update.mentions = mentions
    comment_to_update.department_mentions = department_mentions
    comment_to_update.save()
    comment_dict = comment_to_update.serialize()
    comment_dict["mentions"] = [str(mention.id) for mention in mentions]
    comment_dict["department_mentions"] = [
        str(mention.id) for mention in department_mentions
    ]
    return comment_dict


def acknowledge_comment(comment_id):
    """
    Add the current user to the list of people who acknowledged the given
    comment. If the user is already in the list, remove the user.
    """
    comment = get_comment_raw(comment_id)
    task = tasks_service.get_task(str(comment.object_id))
    project_id = task["project_id"]
    # Load the person again through the session. If another instance of the row
    # is in the session, an append of the cached current_user instance to the
    # relationship raises an identity conflict.
    current_user_id = persons_service.get_current_user()["id"]
    current_user = Person.get(current_user_id)

    acknowledgements = fields.serialize_orm_arrays(comment.acknowledgements)
    is_already_ack = current_user_id in acknowledgements

    if is_already_ack:
        _unack_comment(project_id, comment, current_user)
    else:
        _ack_comment(project_id, comment, current_user)
    comment.save()
    # Kitsu shows the checkmark from the comment that it reads back, not from
    # the response of this call.
    clear_comment_cache(str(comment.id))
    return comment.serialize(relations=True)


def _ack_comment(project_id, comment, user):
    """
    Add the user to the people who acknowledged the comment.
    """
    user_id = str(user.id)
    comment.acknowledgements.append(user)
    _send_ack_event(project_id, comment, user_id, "acknowledge")


def _unack_comment(project_id, comment, user):
    """
    Remove the user from the people who acknowledged the comment.
    """
    user_id = str(user.id)
    comment.acknowledgements = [
        person
        for person in comment.acknowledgements
        if str(person.id) != user_id
    ]
    _send_ack_event(project_id, comment, user_id, "unacknowledge")


def _send_ack_event(project_id, comment, user_id, name="acknowledge"):
    """
    Tell the clients that an acknowledgement was added or removed. This event
    is not persisted: it is a live signal, and the link table is the record.
    """
    events.emit(
        f"comment:{name}",
        {"comment_id": str(comment.id), "person_id": user_id},
        project_id=project_id,
        persist=False,
    )


def reply_comment(comment_id, text, person_id=None, files=None):
    """
    Add a reply entry to the JSONB field of the given comment model, with its
    attachments. Emit comment:reply, create the necessary notifications and
    return the reply as a dict.
    """
    if files is None:
        files = {}
    if person_id is None:
        person = persons_service.get_current_user()
    else:
        person = persons_service.get_person(person_id)
    comment = get_comment_raw(comment_id)
    task = tasks_service.get_task(str(comment.object_id), relations=True)
    if comment.replies is None:
        comment.replies = []

    reply = {
        "id": str(fields.gen_uuid()),
        "date": date_helpers.get_now(),
        "person_id": person["id"],
        "text": text,
        "mentions": get_comment_mention_ids(task["project_id"], text),
        "department_mentions": get_comment_department_mention_ids(text),
        "created_at": date_helpers.get_now(),
    }
    replies = list(comment.replies)
    replies.append(reply)
    comment.update({"replies": replies})
    comment_dict = comment.serialize(relations=True)
    if len(files.keys()) > 0:
        _, new_attachment_files = add_attachments_to_comment(
            comment_dict, files, reply_id=reply["id"]
        )
        for new_attachment_file in new_attachment_files:
            new_attachment_file["reply_id"] = reply["id"]
        reply["attachment_files"] = new_attachment_files
    clear_comment_cache(comment_id)
    events.emit(
        "comment:reply",
        {
            "task_id": task["id"],
            "comment_id": comment_id,
            "reply_id": reply["id"],
        },
        project_id=task["project_id"],
    )
    notifications_service.create_notifications_for_task_and_reply(
        task, comment_dict, reply
    )
    # Embed the author, so that the new reply shows its name and avatar.
    reply["person"] = persons_service.get_short_person(reply["person_id"])
    return reply


def get_reply(comment_id, reply_id):
    """
    Return the reply that has the given ID inside the given comment.
    """
    comment = get_comment_raw(comment_id)
    for reply in comment.replies or []:
        if reply.get("id") == reply_id:
            return reply
    raise ReplyNotFoundException


def delete_reply(comment_id, reply_id):
    """
    Remove the given reply from its comment, with its attachments and the
    notifications that it created.
    """
    comment = get_comment_raw(comment_id)
    task = tasks_service.get_task(str(comment.object_id))

    if comment.attachment_files is not None:
        for attachment_file in comment.attachment_files:
            if str(attachment_file.reply_id) == str(reply_id):
                attachment_files_service.remove_attachment_file_by_id(
                    str(attachment_file.id)
                )
    if comment.replies is None:
        comment.replies = []
    comment.replies = [
        reply for reply in comment.replies if reply["id"] != reply_id
    ]
    comment.save()
    clear_comment_cache(comment_id)
    Notification.delete_all_by(reply_id=reply_id)
    events.emit(
        "comment:delete-reply",
        {
            "task_id": task["id"],
            "comment_id": str(comment.id),
            "reply_id": reply_id,
        },
        project_id=task["project_id"],
        persist=False,
    )
    return comment.serialize()


def get_comment_mentions(project_id, text):
    """
    Find the people mentions (@full name) in the text and return the matching
    person active records.
    """
    project = Project.get(project_id)
    return [
        person
        for person in project.team
        if person.preview_project_id is None
        and re.search(f"@{re.escape(person.full_name)}( |$)", text) is not None
    ]


def get_comment_mention_ids(project_id, text):
    """
    Return the ids of the people mentioned in the given text.
    """
    return [
        str(mention.id) for mention in get_comment_mentions(project_id, text)
    ]


def get_comment_department_mentions(text):
    """
    Find the department mentions (@name) in the text and return the matching
    department active records. All departments of the studio can be mentioned,
    whatever the production.
    """
    return [
        department
        for department in Department.query.all()
        if re.search(f"@{re.escape(department.name)}( |$)", text) is not None
    ]


def get_comment_department_mention_ids(text):
    """
    Return the ids of the departments mentioned in the given text.
    """
    return [
        str(mention.id) for mention in get_comment_department_mentions(text)
    ]


def get_text_mentions(project_id, text):
    """
    Return the people and departments that the given text mentions in the
    production as it is now. Use the shape of the mentions of a comment dict.
    """
    return {
        "mentions": get_comment_mention_ids(project_id, text),
        "department_mentions": get_comment_department_mention_ids(text),
    }


def get_comment_hashtags(text):
    """
    Find the task type mentions (#full name) in the text and return the
    matching tags. If "all" is present, return only "all", because it includes
    all other tags.
    """
    hashtags = [
        hashtag[1:].lower()
        for hashtag in re.findall("#[a-zA-Z]*", text, re.IGNORECASE)
    ]
    if "all" in hashtags:
        return ["all"]
    return list(set(hashtags))


def filter_tasks_by_hashtags(tasks, hashtags, original_task_type):
    """
    Filter the tasks with the hashtags, and exclude the specified task types.
    """
    if "all" in hashtags:
        return [
            task
            for task in tasks
            if task["task_type_name"].lower()
            != original_task_type["name"].lower()
        ]
    else:
        hashtag_map = {
            hashtag: True
            for hashtag in hashtags
            if hashtag != original_task_type["name"].lower()
        }
        return [
            task
            for task in tasks
            if hashtag_map.get(task["task_type_name"].lower(), False)
        ]


def add_attachments_to_comment(comment, files, reply_id=None):
    """
    Create an attachment entry for each given uploaded file, and tie it to the
    given comment. Change the comment dict in place. Return the comment and the
    list of the new attachment files.
    """
    if comment.get("attachment_files", None) is None:
        comment["attachment_files"] = []
    new_attachment_files = []
    for uploaded_file in files.values():
        attachment_file = attachment_files_service.create_attachment(
            comment, uploaded_file, reply_id=reply_id
        )
        comment["attachment_files"].append(attachment_file)
        new_attachment_files.append(attachment_file)
    if new_attachment_files:
        # The given dict is a serialization that the caller read from a
        # different location. An append to it does not change the stored
        # serialization. Thus a file attached to an older comment does not show
        # until the window closes.
        clear_comment_cache(comment["id"])
    return comment, new_attachment_files


def clear_comment_cache(comment_id):
    """
    Remove all memoized serializations of the given comment.
    """
    cache.cache.delete_memoized(get_comment, comment_id)
    cache.cache.delete_memoized(get_comment, comment_id, True)


def get_comments(task_id, is_client=False, is_manager=False):
    """
    Return the comments of the given task that the caller can read, newest
    first. A client gets the comments flagged for clients, and the client
    comments that the project shows to clients. A studio comment with previews
    stays, but its text, attachments, checklist and replies are blank.
    """
    comments = []
    query = prepare_query(task_id, is_client, is_manager)
    comments, comment_ids = run_task_comments_query(query)
    if len(comments) > 0:
        ack_map = _build_ack_map_for_comments(comment_ids)
        mention_map = _build_mention_map_for_comments(comment_ids)
        department_mention_map = _build_department_mention_map_for_comments(
            comment_ids
        )
        preview_map = build_preview_map_for_comments(comment_ids, is_client)
        attachment_file_map = (
            attachment_files_service.build_attachment_map_for_comments(
                comment_ids
            )
        )
        for comment in comments:
            comment["acknowledgements"] = ack_map.get(comment["id"], [])
            comment["previews"] = preview_map.get(comment["id"], [])
            comment["mentions"] = mention_map.get(comment["id"], [])
            comment["department_mentions"] = department_mention_map.get(
                comment["id"], []
            )
            comment["attachment_files"] = attachment_file_map.get(
                comment["id"], []
            )
        embed_reply_authors(comments)

    if is_client:
        tmp_comments = []
        task = tasks_service.get_task(task_id)
        project = projects_service.get_project(task["project_id"])
        current_user = persons_service.get_current_user()
        is_clients_isolated = project.get("is_clients_isolated", False)
        person_ids = list(
            {c["person_id"] for c in comments if c.get("person_id")}
        )
        persons_map = {
            p["id"]: p for p in persons_service.get_persons_by_ids(person_ids)
        }
        for comment in comments:
            person = persons_map.get(comment["person_id"], {})
            is_author = comment["person_id"] == current_user["id"]
            is_author_client = person.get("role") == "client"
            is_for_client = comment.get("for_client", False)
            is_allowed = (
                is_for_client
                or (is_clients_isolated and is_author)
                or (not is_clients_isolated and is_author_client)
            )
            if (
                len(comment["previews"]) > 0
                and not is_author_client
                and not is_for_client
            ):
                comment["text"] = ""
                comment["attachment_files"] = []
                comment["checklist"] = []
                comment["replies"] = []
                tmp_comments.append(comment)
            elif is_allowed:
                tmp_comments.append(comment)
        comments = tmp_comments
    return comments


def prepare_query(task_id, is_client, is_manager):
    """
    Build the comment query of a task. If the caller is not a manager and not a
    client, the caller does not get the comments of clients. get_comments does
    the scoping of a client after this query.
    """
    Editor = aliased(Person, name="editor_id")
    query = (
        Comment.query.order_by(Comment.created_at.desc())
        .filter_by(object_id=task_id)
        .join(Person, Comment.person_id == Person.id)
        .join(TaskStatus, Comment.task_status_id == TaskStatus.id)
        .join(Editor, Comment.editor_id == Editor.id, isouter=True)
        .add_columns(
            TaskStatus.name,
            TaskStatus.short_name,
            TaskStatus.color,
            Person.first_name,
            Person.last_name,
            Person.full_name,
            Person.has_avatar,
            Person.role,
            Editor.first_name,
            Editor.last_name,
            Editor.has_avatar,
            Editor.role,
        )
    )
    if not is_manager and not is_client:
        task = tasks_service.get_task(task_id)
        query = query.outerjoin(
            ProjectPersonLink,
            and_(
                ProjectPersonLink.person_id == Person.id,
                ProjectPersonLink.project_id == task["project_id"],
            ),
        ).filter(
            func.coalesce(ProjectPersonLink.role, Person.role) != "client"
        )
    return query


def embed_reply_authors(comments):
    """
    Attach a minimal author to each reply, so that the replies of guests also
    show.
    """
    reply_person_ids = {
        reply.get("person_id")
        for comment in comments
        for reply in (comment.get("replies") or [])
        if reply.get("person_id")
    }
    if not reply_person_ids:
        return
    persons_map = persons_service.get_short_persons_map(list(reply_person_ids))
    for comment in comments:
        for reply in comment.get("replies") or []:
            reply["person"] = persons_map.get(reply.get("person_id"))


def run_task_comments_query(query):
    """
    Execute a comment query. Return the comments with their author, editor and
    task status, and their ids. The callers add the acknowledgements, mentions,
    department mentions, previews, attachments and reply authors that they
    serve. They do this in a fixed number of queries.
    """
    comment_ids = []
    comments = []
    for result in query.all():
        (
            comment,
            task_status_name,
            task_status_short_name,
            task_status_color,
            person_first_name,
            person_last_name,
            person_full_name,
            person_has_avatar,
            person_role,
            editor_first_name,
            editor_last_name,
            editor_has_avatar,
            editor_role,
        ) = result

        comment_dict = comment.serialize()
        comment_dict["person"] = {
            "first_name": person_first_name,
            "last_name": person_last_name,
            "full_name": person_full_name,
            "has_avatar": person_has_avatar,
            "role": getattr(person_role, "code", person_role),
            "id": str(comment.person_id),
        }
        if comment.editor_id is not None:
            comment_dict["editor"] = {
                "first_name": editor_first_name,
                "last_name": editor_last_name,
                "has_avatar": editor_has_avatar,
                "role": getattr(editor_role, "code", editor_role),
                "id": str(comment.editor_id),
            }
        comment_dict["task_status"] = {
            "name": task_status_name,
            "short_name": task_status_short_name,
            "color": task_status_color,
            "id": str(comment.task_status_id),
        }
        comments.append(comment_dict)
        comment_ids.append(comment_dict["id"])
    return (comments, comment_ids)


def _build_link_map_for_comments(comment_ids, table, value_column):
    """
    Group the rows of a comment link table by comment id, in one query.
    """
    link_map = {}
    for link in (
        db.session.query(table).filter(table.c.comment.in_(comment_ids)).all()
    ):
        comment_id = str(link.comment)
        value = str(getattr(link, value_column))
        link_map.setdefault(comment_id, []).append(value)
    return link_map


def _build_ack_map_for_comments(comment_ids):
    """
    Return the ids of the people who acknowledged each comment.
    """
    return _build_link_map_for_comments(
        comment_ids, acknowledgements_table, "person"
    )


def _build_mention_map_for_comments(comment_ids):
    """
    Return the ids of the people mentioned in each comment.
    """
    return _build_link_map_for_comments(comment_ids, mentions_table, "person")


def _build_department_mention_map_for_comments(comment_ids):
    """
    Return the ids of the departments mentioned in each comment.
    """
    return _build_link_map_for_comments(
        comment_ids, department_mentions_table, "department"
    )


def build_preview_map_for_comments(comment_ids, is_client=False):
    """
    Return the previews attached to each comment. Clients never get the
    rejected previews.
    """
    preview_map = {}
    query = (
        PreviewFile.query.join(CommentPreviewLink)
        .filter(CommentPreviewLink.comment.in_(comment_ids))
        .add_columns(CommentPreviewLink.comment)
    )
    for preview, comment_id in query.all():
        comment_id = str(comment_id)
        if comment_id not in preview_map:
            preview_map[comment_id] = []
        status = "ready"
        if preview.status is not None:
            status = preview.status.code
        validation_status = "neutral"
        if preview.validation_status is not None:
            validation_status = preview.validation_status.code

        if validation_status != "rejected" or not is_client:
            preview_map[comment_id].append(
                {
                    "id": str(preview.id),
                    "task_id": str(preview.task_id),
                    "revision": preview.revision,
                    "extension": preview.extension,
                    "width": preview.width,
                    "height": preview.height,
                    "duration": preview.duration,
                    "status": status,
                    "validation_status": validation_status,
                    "original_name": preview.original_name,
                    "position": preview.position,
                    "annotations": preview.annotations,
                    **preview_files_service.get_preview_file_trim(
                        preview.data
                    ),
                }
            )
    return preview_map


def get_comment_raw(comment_id):
    """
    Return the comment that has the given ID, as an active record.
    """
    try:
        comment = Comment.get(comment_id)
    except StatementError:
        raise CommentNotFoundException

    if comment is None:
        raise CommentNotFoundException
    return comment


@cache.memoize_function(120)
def get_comment(comment_id, relations=False):
    """
    Return the comment that has the given ID, as a dict.
    """
    return get_comment_raw(comment_id).serialize(relations=relations)


def get_task_comment(task_id, comment_id):
    """
    Return the comment that has the given ID as a dict, if it is on the given
    task. Otherwise, raise CommentNotFoundException. This function reads the
    row, not the cache. A read at the same time as a move of the comment to
    another task can keep the former task in the cache for two minutes.
    """
    comment = get_comment_raw(comment_id)
    if str(comment.object_id) != str(task_id):
        raise CommentNotFoundException
    return comment.serialize()


def get_comment_preview_file(task_id, comment_id, preview_file_id):
    """
    Return the given preview file as a dict, if it is attached to the given
    comment and both are on the given task. Otherwise, raise the not found
    exception of the comment or of the preview. The rights checked on a task
    tell nothing about the other ids that a route receives with it.
    """
    comment = get_comment_raw(comment_id)
    if str(comment.object_id) != str(task_id):
        raise CommentNotFoundException
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    is_attached = (
        CommentPreviewLink.query.filter_by(
            comment=comment.id, preview_file=preview_file.id
        ).first()
        is not None
    )
    if str(preview_file.task_id) != str(task_id) or not is_attached:
        raise PreviewFileNotFoundException
    return preview_file.serialize()


def get_comments_for_project(project_id, page=0, limit=None, cursor_id=None):
    """
    Return all comments of the given project, a page of them, or the comments
    after a cursor (see query_utils.get_paginated_results).
    """
    query = (
        Comment.query.join(Task, Task.id == Comment.object_id)
        .filter(Task.project_id == project_id)
        .order_by(Comment.updated_at.desc())
    )
    result = query_utils.get_paginated_results(
        query, page, limit, cursor_id=cursor_id
    )
    comments = result["data"] if isinstance(result, dict) else result
    _add_relation_ids_to_comments(comments)
    return result


def _add_relation_ids_to_comments(comments):
    """
    Add to each comment the same relation id lists as
    Comment.serialize(relations=True). Read them in one query per relation for
    the full list, not in five queries per comment.
    """
    comment_ids = [comment["id"] for comment in comments]
    link_maps = {
        "previews": _build_link_map_for_comments(
            comment_ids, CommentPreviewLink.__table__, "preview_file"
        ),
        "mentions": _build_mention_map_for_comments(comment_ids),
        "department_mentions": _build_department_mention_map_for_comments(
            comment_ids
        ),
        "acknowledgements": _build_ack_map_for_comments(comment_ids),
        "attachment_files": {},
    }
    for attachment_id, comment_id in db.session.query(
        AttachmentFile.id, AttachmentFile.comment_id
    ).filter(AttachmentFile.comment_id.in_(comment_ids)):
        link_maps["attachment_files"].setdefault(str(comment_id), []).append(
            str(attachment_id)
        )
    for comment in comments:
        for attr, link_map in link_maps.items():
            comment[attr] = link_map.get(comment["id"], [])


def add_preview_file_to_comment(comment_id, person_id, task_id, revision=None):
    """
    Add a preview to the preview list of the comment. Set the revision field
    automatically: add 1 for a new preview, else keep the revision of the
    preview. A revision of None means "use the next revision". An explicit 0 is
    a valid, stored revision. If the project allows one preview per revision
    and the revision has one, raise TooManyPreviewFilesException. Emit
    preview-file:new and comment:update, and return the preview file as a dict.
    """
    comment = get_comment_raw(comment_id)
    news = News.get_by(comment_id=comment_id)
    task = Task.get(comment.object_id)
    project_id = str(task.project_id)
    # The next revision and position are read, then written. Two uploads on the
    # same task at the same time can get the same values, and the schema does
    # not refuse that. The lock serializes them per task.
    with redis_lock.with_lock(f"preview_revision_lock:{task_id}"):
        position = 1
        if revision is None and len(comment.previews) == 0:
            revision = tasks_service.get_next_preview_revision(task_id)
        elif revision is None:
            revision = comment.previews[0].revision
            position = tasks_service.get_next_position(task_id, revision)
        else:
            if len(comment.previews) == 0:
                tasks_service.check_revision_is_unique_for_task(
                    task_id, revision
                )
            position = tasks_service.get_next_position(task_id, revision)
        if position > 1:
            project = projects_service.get_project(project_id)
            if project.get("is_single_preview_per_revision"):
                raise TooManyPreviewFilesException(
                    "Only one preview file is allowed per revision for this "
                    "project."
                )
        preview_file = files_service.create_preview_file_raw(
            str(uuid.uuid4())[:13],
            revision,
            task_id,
            person_id,
            position=position,
        )
    events.emit(
        "preview-file:new",
        {
            "preview_file_id": preview_file.id,
            "comment_id": comment_id,
        },
        project_id=project_id,
    )
    comment.previews.append(preview_file)
    comment.save()
    clear_comment_cache(comment_id)
    if news is not None:
        news.update({"preview_file_id": preview_file.id})
        news_service.clear_news_cache([news], project_id)
    events.emit(
        "comment:update",
        {
            "comment_id": comment.id,
            "task_id": comment.object_id,
            "person_id": comment.person_id,
            "for_client": comment.for_client,
        },
        project_id=project_id,
    )
    return preview_file.serialize(relations=True)


def copy_preview_file_in_another_one(
    original_preview_file_id, preview_file_to_update_id
):
    """
    Copy the data and the files of one preview file to another preview file. If
    the target preview belongs to a comment, emit comment:update and
    preview-file:add-file. Return the updated preview file as a dict.
    """
    original_preview_file = files_service.get_preview_file(
        original_preview_file_id
    )
    is_movie = original_preview_file["extension"] == "mp4"
    is_picture = original_preview_file["extension"] == "png"

    stored_movie_prefixes = []
    copied_files = {}
    if is_movie:
        # Copy the source too. If the normalization is skipped, the source is
        # the only stored movie, and the preview routes serve it.
        for prefix in files_service.MOVIE_PREFIXES:
            copied = preview_files_service.copy_preview_file_on_storage(
                "movies",
                file_store.get_local_movie_path,
                file_store.exists_movie,
                file_store.copy_movie,
                prefix,
                original_preview_file_id,
                preview_file_to_update_id,
            )
            if copied:
                stored_movie_prefixes.append(prefix)
                copied_files[("movies", prefix)] = (
                    preview_file_states_service.OK
                )

    if is_movie or is_picture:
        prefixes = [
            "previews",
            "original",
            "thumbnails",
            "thumbnails-square",
        ]
        if is_movie:
            prefixes.append("tiles")

        for prefix in prefixes:
            copied = preview_files_service.copy_preview_file_on_storage(
                "pictures",
                file_store.get_local_picture_path,
                file_store.exists_picture,
                file_store.copy_picture,
                prefix,
                original_preview_file_id,
                preview_file_to_update_id,
            )
            if copied:
                copied_files[("pictures", prefix)] = (
                    preview_file_states_service.OK
                )
    else:
        copied = preview_files_service.copy_preview_file_on_storage(
            "files",
            file_store.get_local_file_path,
            file_store.exists_file,
            file_store.copy_file,
            "previews",
            original_preview_file_id,
            preview_file_to_update_id,
        )
        if copied:
            copied_files[("files", "previews")] = (
                preview_file_states_service.OK
            )

    preview_file_states_service.record_file_states(
        preview_file_to_update_id, copied_files
    )

    data = {
        "extension": original_preview_file["extension"],
        "original_name": original_preview_file["original_name"],
        "status": original_preview_file["status"],
        "file_size": original_preview_file["file_size"],
        "width": original_preview_file["width"],
        "height": original_preview_file["height"],
        "duration": original_preview_file["duration"],
    }
    if is_movie:
        # The copy knows which movie versions it found. Record them, so that
        # the movie routes do not examine the storage again.
        target_preview_file = files_service.get_preview_file_raw(
            preview_file_to_update_id
        )
        data["data"] = {
            **files_service.get_preview_file_data(target_preview_file),
            files_service.MOVIE_PREFIXES_KEY: stored_movie_prefixes,
        }
    preview_file_to_update = preview_files_service.update_preview_file(
        preview_file_to_update_id, data
    )
    tasks_service.update_preview_file_info(preview_file_to_update)
    comment = tasks_service.get_comment_by_preview_file_id(
        preview_file_to_update_id
    )
    task = tasks_service.get_task(preview_file_to_update["task_id"])
    comment_id = None
    if comment is not None:
        comment_id = comment["id"]
        news_service.clear_comment_news_cache(comment_id, task["project_id"])
        events.emit(
            "comment:update",
            {
                "comment_id": comment_id,
                "task_id": comment["object_id"],
                "person_id": comment["person_id"],
                "for_client": comment["for_client"],
            },
            project_id=task["project_id"],
        )
        events.emit(
            "preview-file:add-file",
            {
                "comment_id": comment_id,
                "task_id": preview_file_to_update["task_id"],
                "preview_file_id": preview_file_to_update["id"],
                "revision": preview_file_to_update["revision"],
                "extension": preview_file_to_update["extension"],
                "status": preview_file_to_update["status"],
            },
            project_id=task["project_id"],
        )

    return preview_file_to_update


def get_last_client_comments(project_id, task_ids):
    """
    Return the last comment that a client of the project wrote on each given
    task of the project, in one query. A client is a person whose project role
    is client. If the person has no project role, use the global role.
    """
    return [
        comment.serialize()
        for comment in Comment.query.join(Task, Comment.object_id == Task.id)
        .join(Person, Comment.person_id == Person.id)
        .outerjoin(
            ProjectPersonLink,
            and_(
                ProjectPersonLink.person_id == Person.id,
                ProjectPersonLink.project_id == Task.project_id,
            ),
        )
        .filter(Task.project_id == project_id)
        .filter(Comment.object_id.in_(task_ids))
        .filter(func.coalesce(ProjectPersonLink.role, Person.role) == "client")
        .order_by(Comment.object_id, Comment.created_at.desc())
        .distinct(Comment.object_id)
        .all()
    ]


def copy_last_client_comments(project_id, task_ids, person_id, prefix=""):
    """
    Copy the last client comment of each given task into a new comment of the
    given person. Thus the artists who do not see the client comments get it.
    The task keeps its status. If a task has no client comment, skip it.
    """
    result = []
    for client_comment in get_last_client_comments(project_id, task_ids):
        task = tasks_service.get_task(client_comment["object_id"])
        text = client_comment["text"]
        if prefix:
            text = f"{prefix}\n\n{text}"
        result.append(
            create_comment(person_id, task["id"], task["task_status_id"], text)
        )
    return result
