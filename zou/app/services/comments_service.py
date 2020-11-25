import datetime
import re

from flask import current_app

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.project import Project

from zou.app.services import (
    base_service,
    news_service,
    notifications_service,
    persons_service,
    tasks_service
)
from zou.app.services.exception import (
    AttachmentFileNotFoundException
)

from zou.app.utils import cache, events, fs, fields
from zou.app.stores import file_store
from zou.app import config


def get_attachment_file_raw(attachment_file_id):
    return base_service.get_instance(
        AttachmentFile,
        attachment_file_id,
        AttachmentFileNotFoundException
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
    return fs.get_file_path(
        config,
        file_store.get_local_file_path,
        file_store.open_file,
        "attachments",
        attachment_file["id"],
        attachment_file["extension"]
    )


def create_comment(
    person_id,
    task_id,
    task_status_id,
    comment,
    checklist,
    files,
    created_at
):
    """
    Create a new comment and related: news, notifications and events.
    """
    task = tasks_service.get_task_with_relations(task_id)
    task_status = tasks_service.get_task_status(task_status_id)
    author = _get_comment_author(person_id)
    comment = new_comment(
        task_id=task_id,
        object_type="Task",
        files=files,
        person_id=author["id"],
        task_status_id=task_status_id,
        text=comment,
        checklist=checklist,
        created_at=created_at
    )
    task, status_changed = _manage_status_change(task_status, task, comment)
    _manage_subscriptions(task, comment, status_changed)
    comment["task_status"] = task_status
    comment["person"] = author
    return comment


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

        if task_status["is_done"]:
            new_data["end_date"] = datetime.datetime.now()
        else:
            new_data["end_date"] = None

        if (
            task_status["short_name"] == "wip" and
            task["real_start_date"] is None
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
                "person_id": comment["person_id"]
            },
            project_id=task["project_id"]
        )
    return task, status_changed


def _manage_subscriptions(task, comment, status_changed):
    notifications_service.create_notifications_for_task_and_comment(
        task, comment, change=status_changed
    )
    news_service.create_news_for_task_and_comment(
        task, comment, change=status_changed
    )


def new_comment(
    task_id, task_status_id, person_id, text,
    object_type="Task", files={}, checklist=[], created_at=""
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
                created_at,
                date_format="%Y-%m-%d %H:%M:%S"
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
        created_at=created_at_date
    )

    comment = comment.serialize(relations=True)
    comment["attachment_files"] = []
    for uploaded_file in files.values():
        attachment_file = create_attachment(comment, uploaded_file)
        comment["attachment_files"].append(attachment_file)

    events.emit(
        "comment:new",
        {"comment_id": comment["id"]},
        project_id=task["project_id"]
    )
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


def create_attachment(comment, uploaded_file):
    tmp_folder = current_app.config["TMP_DIR"]
    filename = uploaded_file.filename
    mimetype = uploaded_file.mimetype
    extension = fs.get_file_extension(filename)

    attachment_file = AttachmentFile.create(
        name=filename,
        size=0,
        extension=extension,
        mimetype=mimetype,
        comment_id=comment["id"]
    )
    attachment_file_id = str(attachment_file.id)

    tmp_file_path = fs.save_file(tmp_folder, attachment_file_id, uploaded_file)
    size = fs.get_file_size(tmp_file_path)
    attachment_file.update({"size": size})
    file_store.add_file("attachments", attachment_file_id, tmp_file_path)
    return attachment_file.present()


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
        {
            "comment_id": str(comment.id),
            "person_id": user_id
        },
        project_id=project_id,
        persist=False
    )
