import datetime
import re
import random
import string

from flask import current_app

from sqlalchemy.exc import IntegrityError

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.department import Department
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus

from zou.app.services import (
    assets_service,
    base_service,
    breakdown_service,
    deletion_service,
    entities_service,
    news_service,
    notifications_service,
    persons_service,
    projects_service,
    tasks_service,
    concepts_service,
    preview_files_service,
)
from zou.app.services.exception import (
    AttachmentFileNotFoundException,
    WrongParameterException,
    AssetNotFoundException,
    ReplyNotFoundException,
)

from zou.app.utils import cache, date_helpers, events, fs, fields
from zou.app.stores import file_store
from zou.app import config


def get_attachment_file_raw(attachment_file_id):
    return base_service.get_instance(
        AttachmentFile, attachment_file_id, AttachmentFileNotFoundException
    )


@cache.memoize_function(120)
def get_attachment_file(attachment_file_id):
    """
    Return attachment file model matching given id.
    """
    attachment_file = get_attachment_file_raw(attachment_file_id)
    return attachment_file.serialize()


def clear_attachment_file_cache(attachment_file_id):
    cache.cache.delete_memoized(get_attachment_file, attachment_file_id)


def get_attachment_file_path(attachment_file):
    """
    Get attachement file path when stored locally.
    """
    return fs.get_file_path_and_file(
        config,
        file_store.get_local_file_path,
        file_store.open_file,
        "attachments",
        attachment_file["id"],
        attachment_file["extension"],
        file_size=attachment_file["size"],
    )


# Raster image types that are safe to display inline. Paired with the global
# X-Content-Type-Options: nosniff header, the browser honors the declared type
# and will not sniff a disguised HTML payload into an executable document.
# image/svg+xml is deliberately excluded: SVG can embed scripts and would run
# in Kitsu's origin (stored XSS).
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
    Return True when an attachment with this mimetype may be served inline
    (displayed in the browser) instead of forced as a download.
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
):
    """
    Create a new comment and related: news, notifications and events.
    """
    if checklist is None:
        checklist = []
    if files is None:
        files = {}
    if links is None:
        links = []
    author = _get_comment_author(person_id)
    task = tasks_service.get_task(task_id, relations=True)
    task_status = tasks_service.get_task_status(task_status_id)
    task_type = tasks_service.get_task_type(task["task_type_id"])
    _check_retake_capping(task_status, task)

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
        _handle_hashtags(author, task_type, task, text)

    task, status_changed = _manage_status_change(task_status, task, comment)
    _manage_subscriptions(task, comment, status_changed)
    comment["task_status"] = task_status
    comment["person"] = author

    status_automations = projects_service.get_project_status_automations(
        task["project_id"]
    )
    for automation in status_automations:
        _run_status_automation(automation, task, person_id)

    return comment


def _handle_hashtags(person, task_type, task, text):
    hashtags = get_comment_hashtags(text)
    if len(hashtags) > 0:
        entity = entities_service.get_entity(entity_id=task["entity_id"])
        tasks = entities_service.get_entity_tasks(entity)
        tasks = filter_tasks_by_hashtags(tasks, hashtags, task_type)
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


def _check_retake_capping(task_status, task):
    if task_status["is_retake"]:
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
    if person_id is not None and person_id != "":
        person = persons_service.get_person(person_id)
    else:
        person = persons_service.get_current_user()
    return person


def _manage_status_change(task_status, task, comment):
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

            if task_status["is_feedback_request"]:
                if task.get("end_date") is None:
                    new_data["end_date"] = date_helpers.get_utc_now_datetime()

            if task_status["is_wip"] and task["real_start_date"] is None:
                new_data["real_start_date"] = datetime.datetime.now(
                    datetime.timezone.utc
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
                # Backwards-compatible: the legacy /actions/tasks/<id>/to-review
                # endpoint emitted task:to-review whenever a task moved to a
                # feedback-request status. Modern Kitsu posts a comment with
                # the new task_status_id instead, so we re-emit the event from
                # here to keep existing gazu listeners working.
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
    notifications_service.create_notifications_for_task_and_comment(
        task, comment, change=status_changed
    )
    if (
        entities_service.get_entity(task["entity_id"])["entity_type_id"]
        != concepts_service.get_concept_type()["id"]
    ):
        news_service.create_news_for_task_and_comment(
            task,
            comment,
            created_at=comment["created_at"],
            change=status_changed,
        )


def _run_status_automation(automation, task, person_id):
    if (
        automation["archived"]
        or task["task_type_id"] != automation["in_task_type_id"]
        or task["task_status_id"] != automation["in_task_status_id"]
    ):
        return

    entity = entities_service.get_entity(task["entity_id"])
    entity_type = entities_service.get_entity_type(entity["entity_type_id"])
    wanted = (automation.get("entity_type") or "").lower()
    if wanted == "asset":
        if not assets_service.is_asset_type(entity_type):
            return
    elif entity_type["name"].lower() != wanted:
        return

    priorities = projects_service.get_task_type_priority_map(
        task["project_id"], automation["entity_type"].capitalize()
    )
    in_priority = priorities.get(automation["in_task_type_id"], 0) or 0
    out_priority = priorities.get(automation["out_task_type_id"], 0) or 0
    is_rollback = (
        priorities is not None
        and automation["out_field_type"] != "ready_for"
        and in_priority > out_priority
    )
    if is_rollback:  # Do not apply rollback to avoid change cycles.
        return

    if automation["out_field_type"] == "status":
        tasks_to_update = tasks_service.get_tasks_for_entity_and_task_type(
            task["entity_id"], automation["out_task_type_id"]
        )
        if len(tasks_to_update) > 0:
            task_to_update = tasks_to_update[0]
            task_type = tasks_service.get_task_type(
                automation["in_task_type_id"]
            )
            task_status = tasks_service.get_task_status(
                automation["in_task_status_id"]
            )
            new_comment = create_comment(
                person_id,
                task_to_update["id"],
                automation["out_task_status_id"],
                f"Change triggered by {task_type['name']} set to {task_status['name']}",
                [],
                {},
                None,
            )
            if automation["import_last_revision"]:
                preview_file = (
                    preview_files_service.get_last_preview_file_for_task(
                        task["id"]
                    )
                )
                if preview_file is not None:
                    preview_files = (
                        preview_files_service.get_preview_files_for_revision(
                            preview_file["task_id"], preview_file["revision"]
                        )
                    )

                    for preview_file in preview_files:
                        new_preview_file = (
                            tasks_service.add_preview_file_to_comment(
                                new_comment["id"],
                                new_comment["person_id"],
                                task_to_update["id"],
                            )
                        )

                        preview_files_service.copy_preview_file_in_another_one(
                            preview_file["id"], new_preview_file["id"]
                        )

    elif automation["out_field_type"] == "ready_for":
        try:
            data = {"ready_for": automation["out_task_type_id"]}
            asset = assets_service.update_asset(task["entity_id"], data)
            events.emit(
                "asset:update",
                {"asset_id": task["entity_id"], "data": data},
                project_id=task["project_id"],
            )
            breakdown_service.refresh_casting_stats(asset)
        except AssetNotFoundException:
            pass


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
    Create a new comment for given object (by default, it considers this object
    as a Task).
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
        department_mentions=get_comment_department_mentions(task_id, text),
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
        },
        project_id=task["project_id"],
    )
    return comment


def move_comment_to_task(comment_id, target_task_id):
    """
    Move a comment from its current task to another task that belongs to the
    same entity. The original creation date, text, attachments, mentions and
    status change carried by the comment are preserved. Notifications and
    news linked to the comment on the source task are removed and recreated
    against the target task so the target task's watchers are notified as if
    they received a new comment.

    Comments tied to a preview revision (preview_file_id set or previews
    populated) cannot be moved: previews stay attached to the task that
    owns the revision.
    """
    comment = tasks_service.get_comment_raw(comment_id)
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
    tasks_service.clear_comment_cache(str(comment.id))

    tasks_service.reset_task_data(str(source_task["id"]))
    target_task = tasks_service.reset_task_data(str(target_task["id"]))

    comment_dict = comment.serialize(relations=True)

    events.emit(
        "comment:delete",
        {"comment_id": str(comment.id)},
        project_id=source_task["project_id"],
    )
    events.emit(
        "comment:new",
        {
            "comment_id": str(comment.id),
            "task_id": str(target_task["id"]),
            "task_status_id": comment_dict["task_status_id"],
        },
        project_id=target_task["project_id"],
    )

    notifications_service.create_notifications_for_task_and_comment(
        target_task, comment_dict, change=False
    )
    if (
        entities_service.get_entity(target_task["entity_id"])["entity_type_id"]
        != concepts_service.get_concept_type()["id"]
    ):
        news_service.create_news_for_task_and_comment(
            target_task,
            comment_dict,
            created_at=comment_dict["created_at"],
        )

    return comment_dict


def reset_mentions(comment):
    task = tasks_service.get_task(comment["object_id"])
    mentions = get_comment_mentions(task["project_id"], comment["text"])
    department_mentions = get_comment_department_mentions(
        task["project_id"], comment["text"]
    )
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


def create_attachment(comment, uploaded_file, randomize=False, reply_id=None):
    tmp_folder = current_app.config["TMP_DIR"]
    filename = uploaded_file.filename
    mimetype = uploaded_file.mimetype
    extension = fs.get_file_extension(filename)
    if randomize:
        letters = string.ascii_lowercase
        random_str = "".join(random.choice(letters) for i in range(8))
        filename = f"{filename[:len(filename) - len(extension) - 1]}"
        filename += f"-{random_str}.{extension}"

    if reply_id is not None:
        is_reply_present = any(
            reply["id"] == reply_id for reply in comment.get("replies", [])
        )
        if not is_reply_present:
            reply_id = None

    attachment_file = AttachmentFile.create(
        name=filename,
        size=0,
        extension=extension,
        mimetype=mimetype,
        reply_id=reply_id,
        comment_id=comment["id"],
    )
    attachment_file_id = str(attachment_file.id)

    # On storage failure, drop the database entry to avoid a ghost
    # attachment pointing to a missing object; the temporary file is
    # removed in every case.
    tmp_file_path = fs.save_file(tmp_folder, attachment_file_id, uploaded_file)
    try:
        size = fs.get_file_size(tmp_file_path)
        attachment_file.update({"size": size})
        file_store.add_file("attachments", attachment_file_id, tmp_file_path)
        return attachment_file.present()
    except Exception:
        try:
            attachment_file.delete()
        except Exception:
            current_app.logger.error(
                f"Failed to delete attachment file {attachment_file_id} "
                f"after a storage failure",
                exc_info=1,
            )
        raise
    finally:
        fs.rm_file(tmp_file_path)


def get_all_attachment_files_for_project(project_id):
    """
    Return all attachment files listed into given project. It is mainly needed
    for synchronisation purposes.
    """
    attachment_files = (
        AttachmentFile.query.join(Comment)
        .join(Task, Task.id == Comment.object_id)
        .filter(Task.project_id == project_id)
    )
    return fields.serialize_models(attachment_files)


def get_all_attachment_files_for_task(task_id):
    """
    Return all attachment files listed into given task.
    """
    attachment_files = (
        AttachmentFile.query.join(Comment)
        .join(Task, Task.id == Comment.object_id)
        .filter(Task.id == task_id)
    )
    return fields.serialize_models(attachment_files)


def acknowledge_comment(comment_id):
    """
    Add current user to the list of people who acknowledged given comment.
    If he's already present, remove it.
    """
    comment = tasks_service.get_comment_raw(comment_id)
    task = tasks_service.get_task(str(comment.object_id))
    project_id = task["project_id"]
    # Reload the person through the session: appending the cached
    # current_user instance to the relationship raises an identity
    # conflict when another instance of the row lives in the session.
    current_user_id = persons_service.get_current_user()["id"]
    current_user = Person.get(current_user_id)

    acknowledgements = fields.serialize_orm_arrays(comment.acknowledgements)
    is_already_ack = current_user_id in acknowledgements

    if is_already_ack:
        _unack_comment(project_id, comment, current_user)
    else:
        _ack_comment(project_id, comment, current_user)
    comment.save()
    return comment.serialize(relations=True)


def _ack_comment(project_id, comment, user):
    user_id = str(user.id)
    comment.acknowledgements.append(user)
    _send_ack_event(project_id, comment, user_id, "acknowledge")


def _unack_comment(project_id, comment, user):
    user_id = str(user.id)
    comment.acknowledgements = [
        person
        for person in comment.acknowledgements
        if str(person.id) != user_id
    ]
    _send_ack_event(project_id, comment, user_id, "unacknowledge")


def _send_ack_event(project_id, comment, user_id, name="acknowledge"):
    events.emit(
        f"comment:{name}",
        {"comment_id": str(comment.id), "person_id": user_id},
        project_id=project_id,
        persist=False,
    )


def reply_comment(comment_id, text, person_id=None, files=None):
    """
    Add a reply entry to the JSONB field of given comment model. Create
    notifications needed for this.
    """
    if files is None:
        files = {}
    person = None
    if person_id is None:
        person = persons_service.get_current_user()
    else:
        person = persons_service.get_person(person_id)
    comment = tasks_service.get_comment_raw(comment_id)
    task = tasks_service.get_task(comment.object_id, relations=True)
    if comment.replies is None:
        comment.replies = []

    reply = {
        "id": str(fields.gen_uuid()),
        "date": date_helpers.get_now(),
        "person_id": person["id"],
        "text": text,
        "mentions": get_comment_mention_ids(task["project_id"], text),
        "department_mentions": get_comment_department_mention_ids(
            task["project_id"], text
        ),
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
    tasks_service.clear_comment_cache(comment_id)
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
    # Embed the author so the just-posted reply renders with name and avatar.
    reply["person"] = persons_service.get_short_person(reply["person_id"])
    return reply


def get_reply(comment_id, reply_id):
    comment = tasks_service.get_comment_raw(comment_id)
    if comment.replies is None:
        comment.replies = []
    for reply in comment.replies:
        if reply.get("id") == reply_id:
            return reply
    raise ReplyNotFoundException


def delete_reply(comment_id, reply_id):
    comment = tasks_service.get_comment_raw(comment_id)
    task = tasks_service.get_task(comment.object_id)

    if comment.attachment_files is not None:
        for attachment_file in comment.attachment_files:
            if attachment_file.reply_id == reply_id:
                deletion_service.remove_attachment_file_by_id(
                    str(attachment_file.id)
                )
    if comment.replies is None:
        comment.replies = []
    comment.replies = [
        reply for reply in comment.replies if reply["id"] != reply_id
    ]
    comment.save()
    tasks_service.clear_comment_cache(comment_id)
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
    Check for people mention (@full name) in text and returns matching person
    active records.
    """
    project = Project.get(project_id)
    mentions = []
    for person in project.team:
        if re.search(f"@{person.full_name}( |$)", text) is not None:
            mentions.append(person)
    return mentions


def get_comment_mention_ids(project_id, text):
    return [
        str(mention.id) for mention in get_comment_mentions(project_id, text)
    ]


def get_comment_department_mentions(project_id, text):
    """
    Check for department mention (@name) in text and returns matching person
    active records.
    """
    departments = Department.query.all()
    mentions = []
    for department in departments:
        if re.search(f"@{department.name}( |$)", text) is not None:
            mentions.append(department)
    return mentions


def get_comment_department_mention_ids(project_id, text):
    return [
        str(mention.id)
        for mention in get_comment_department_mentions(project_id, text)
    ]


def get_comment_hashtags(text):
    """
    Check for task type mentions (#full name) in text and returns matching
    tags. If all is present, return only all because it includes everything
    else.
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
    Filter tasks based on hashtags, excluding specified task types.
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
    Create an attachment entry and for each given uploaded files and tie it
    to given comment.
    """
    if comment.get("attachment_files", None) is None:
        comment["attachment_files"] = []
    new_attachment_files = []
    for uploaded_file in files.values():
        try:
            attachment_file = create_attachment(
                comment, uploaded_file, reply_id=reply_id
            )
            comment["attachment_files"].append(attachment_file)
            new_attachment_files.append(attachment_file)
        except IntegrityError:
            attachment_file = create_attachment(
                comment, uploaded_file, randomize=True, reply_id=reply_id
            )
            comment["attachment_files"].append(attachment_file)
            new_attachment_files.append(attachment_file)
    return comment, new_attachment_files
