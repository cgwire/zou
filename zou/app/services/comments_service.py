import datetime
import os
import re
import random
import string

from flask import current_app

from sqlalchemy.exc import IntegrityError

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.notification import Notification
from zou.app.models.project import Project
from zou.app.models.task import Task

from zou.app.services import (
    assets_service,
    base_service,
    breakdown_service,
    entities_service,
    news_service,
    notifications_service,
    persons_service,
    projects_service,
    tasks_service,
)
from zou.app.services.exception import (
    AttachmentFileNotFoundException,
    WrongParameterException,
    AssetNotFoundException,
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


def create_comment(
    person_id, task_id, task_status_id, text, checklist, files, created_at
):
    """
    Create a new comment and related: news, notifications and events.
    """
    task = tasks_service.get_task_with_relations(task_id)
    task_status = tasks_service.get_task_status(task_status_id)
    author = _get_comment_author(person_id)
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
    )
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


def _check_retake_capping(task_status, task):
    if task_status["is_retake"]:
        project = projects_service.get_project(task["project_id"])
        project_max_retakes = project["max_retakes"] or 0
        if project_max_retakes > 0:
            entity = entities_service.get_entity_raw(task["entity_id"])
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
    if person_id:
        person = persons_service.get_person(person_id)
    else:
        person = persons_service.get_current_user()
    return person


def _manage_status_change(task_status, task, comment):
    status_changed = task_status["id"] != task["task_status_id"]
    new_data = {
        "task_status_id": task_status["id"],
        "last_comment_date": comment["created_at"],
    }
    if status_changed:
        if task_status["is_retake"]:
            retake_count = task["retake_count"]
            if retake_count is None or retake_count == "NoneType":
                retake_count = 0
            new_data["retake_count"] = retake_count + 1

        if task_status["is_feedback_request"]:
            new_data["end_date"] = datetime.datetime.now()
        else:
            new_data["end_date"] = None

        if (
            task_status["short_name"] == "wip"
            and task["real_start_date"] is None
        ):
            new_data["real_start_date"] = datetime.datetime.now()

    tasks_service.update_task(task["id"], new_data)
    task.update(new_data)
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
    return task, status_changed


def _manage_subscriptions(task, comment, status_changed):
    notifications_service.create_notifications_for_task_and_comment(
        task, comment, change=status_changed
    )
    news_service.create_news_for_task_and_comment(
        task, comment, created_at=comment["created_at"], change=status_changed
    )


def _run_status_automation(automation, task, person_id):
    is_automation_to_run = (
        task["task_type_id"] == automation["in_task_type_id"]
        and task["task_status_id"] == automation["in_task_status_id"]
    )
    if not is_automation_to_run:
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
            create_comment(
                person_id,
                task_to_update["id"],
                automation["out_task_status_id"],
                "Change triggered by %s set to %s"
                % (
                    task_type["name"],
                    task_status["name"],
                ),
                [],
                {},
                None,
            )
    elif automation["out_field_type"] == "ready_for":
        try:
            asset = assets_service.update_asset(
                task["entity_id"],
                {"ready_for": automation["out_task_type_id"]},
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
    files={},
    checklist=[],
    created_at="",
):
    """
    Create a new comment for given object (by default, it considers this object
    as a Task).
    """
    created_at_date = None
    task = tasks_service.get_task(task_id)
    if created_at is not None and len(created_at) > 0:
        try:
            created_at_date = fields.get_date_object(
                created_at, date_format="%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            try:
                created_at_date = fields.get_date_object(
                    created_at, date_format="%Y-%m-%dT%H:%M:%S"
                )
            except ValueError:
                pass

    comment = Comment.create(
        object_id=task_id,
        object_type=object_type,
        task_status_id=task_status_id,
        person_id=person_id,
        mentions=get_comment_mentions(task_id, text),
        checklist=checklist,
        text=text,
        created_at=created_at_date,
    )

    comment = comment.serialize(relations=True)
    add_attachments_to_comment(comment, files)
    events.emit(
        "comment:new",
        {"comment_id": comment["id"], "task_id": task_id},
        project_id=task["project_id"],
    )
    return comment


def add_attachments_to_comment(comment, files):
    """
    Create an attachment entry and for each given uploaded files and tie it
    to given comment.
    """
    comment["attachment_files"] = []
    for uploaded_file in files.values():
        try:
            attachment_file = create_attachment(comment, uploaded_file)
            comment["attachment_files"].append(attachment_file)
        except IntegrityError:
            attachment_file = create_attachment(
                comment, uploaded_file, randomize=True)
            comment["attachment_files"].append(attachment_file)
    return comment


def get_comment_mentions(object_id, text):
    """
    Check for people mention (@full name) in text and returns matching person
    active records.
    """
    task = tasks_service.get_task_raw(object_id)
    project = Project.get(task.project_id)
    mentions = []
    for person in project.team:
        if re.search("@%s( |$)" % person.full_name(), text) is not None:
            mentions.append(person)
    return mentions


def reset_mentions(comment):
    task = tasks_service.get_task(comment["object_id"])
    mentions = get_comment_mentions(task["id"], comment["text"])
    comment_to_update = Comment.get(comment["id"])
    comment_to_update.mentions = mentions
    comment_to_update.save()
    comment_dict = comment_to_update.serialize()
    comment_dict["mentions"] = [str(mention.id) for mention in mentions]
    return comment_dict


def create_attachment(comment, uploaded_file, randomize=False):
    tmp_folder = current_app.config["TMP_DIR"]
    filename = uploaded_file.filename
    mimetype = uploaded_file.mimetype
    extension = fs.get_file_extension(filename)
    if randomize:
        letters = string.ascii_lowercase
        random_str = ''.join(random.choice(letters) for i in range(8))
        filename = f"{filename[:len(filename) - len(extension) - 1]}"
        filename += f"-{random_str}.{extension}"

    attachment_file = AttachmentFile.create(
        name=filename,
        size=0,
        extension=extension,
        mimetype=mimetype,
        comment_id=comment["id"],
    )
    attachment_file_id = str(attachment_file.id)

    tmp_file_path = fs.save_file(tmp_folder, attachment_file_id, uploaded_file)
    size = fs.get_file_size(tmp_file_path)
    attachment_file.update({"size": size})
    file_store.add_file("attachments", attachment_file_id, tmp_file_path)
    os.remove(tmp_file_path)
    return attachment_file.present()


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
    current_user = persons_service.get_current_user_raw()
    current_user_id = str(current_user.id)

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
        "comment:%s" % name,
        {"comment_id": str(comment.id), "person_id": user_id},
        project_id=project_id,
        persist=False,
    )


def reply_comment(comment_id, text):
    """
    Add a reply entry to the JSONB field of given comment model. Create
    notifications needed for this.
    """
    person = persons_service.get_current_user()
    comment = tasks_service.get_comment_raw(comment_id)
    task = tasks_service.get_task(comment.object_id, relations=True)
    if comment.replies is None:
        comment.replies = []
    reply = {
        "id": str(fields.gen_uuid()),
        "date": date_helpers.get_now(),
        "person_id": person["id"],
        "text": text,
    }
    replies = list(comment.replies)
    replies.append(reply)
    comment.update({"replies": replies})
    tasks_service.clear_comment_cache(comment_id)
    events.emit(
        "comment:reply",
        {
            "task_id": task["id"],
            "comment_id": str(comment.id),
            "reply_id": reply["id"],
        },
        project_id=task["project_id"],
    )
    notifications_service.create_notifications_for_task_and_reply(
        task, comment.serialize(), reply
    )
    return reply


def get_reply(comment_id, reply_id):
    comment = tasks_service.get_comment_raw(comment_id)
    reply = next(reply for reply in comment.replies if reply["id"] == reply_id)
    return reply


def delete_reply(comment_id, reply_id):
    comment = tasks_service.get_comment_raw(comment_id)
    task = tasks_service.get_task(comment.object_id)
    if comment.replies is None:
        comment.replies = []
    comment.replies = [
        reply for reply in comment.replies if reply["id"] != reply_id
    ]
    comment.save()
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
