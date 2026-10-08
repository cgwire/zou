from sqlalchemy.sql import func

from zou.app.models.project import ProjectPersonLink
from zou.app.models.notification import Notification
from zou.app.models.person import Person, DepartmentLink
from zou.app.models.task import Task

from zou.app.services import (
    emails_service,
    projects_service,
    tasks_service,
    persons_service,
    subscriptions_service,
)
from zou.app.exceptions import PersonNotFoundException
from zou.app.utils import date_helpers, events, fields, query as query_utils


def _emit_notification(notification, recipient_id, project_id):
    """
    Tell the recipient's client that a notification landed. Not persisted:
    the notification row is the record, the event is only the live signal.
    """
    events.emit(
        "notification:new",
        {"notification_id": notification["id"], "person_id": recipient_id},
        project_id=project_id,
        persist=False,
    )


def create_notification(
    person_id,
    comment_id=None,
    author_id=None,
    task_id=None,
    reply_id=None,
    read=False,
    change=False,
    type="comment",
    created_at=None,
    playlist_id=None,
):
    """
    Create a new notification for given person and comment.
    """
    creation_date = fields.get_default_date_object(created_at)
    notification = Notification.create(
        read=read,
        change=change,
        person_id=person_id,
        author_id=author_id,
        task_id=task_id,
        comment_id=comment_id,
        reply_id=reply_id,
        playlist_id=playlist_id,
        type=type,
        created_at=creation_date,
    )
    return notification.serialize()


def get_notification_recipients(task, replies=None):
    """
    Get the list of notification recipients for given task: assignees and
    every people who commented the task.
    """
    if replies is None:
        replies = []
    recipients = set(task["assignees"])
    for subscription in subscriptions_service.get_task_subscriptions(task):
        recipients.add(str(subscription.person_id))
    for (
        subscription
    ) in subscriptions_service.get_sequence_subscriptions_for_task(task):
        recipients.add(str(subscription.person_id))
    for reply in replies:
        recipients.add(reply["person_id"])
    return recipients


def create_notifications_for_task_and_comment(task, comment, change=False):
    """
    For given task and comment, create a notification for every assignee
    to the task and to every person participating to this task.
    """
    recipient_ids = get_notification_recipients(task)
    if comment["person_id"] in recipient_ids:
        recipient_ids.remove(comment["person_id"])
    author_id = comment["person_id"]
    task = tasks_service.get_task(comment["object_id"])

    for recipient_id in recipient_ids:
        try:
            notification = create_notification(
                recipient_id,
                comment_id=comment["id"],
                author_id=author_id,
                task_id=task["id"],
                read=False,
                change=change,
                type="comment",
            )
            emails_service.send_comment_notification(
                recipient_id, author_id, comment, task
            )
            _emit_notification(notification, recipient_id, task["project_id"])
        except PersonNotFoundException:
            pass

    mentions = get_mentioned_people(task["project_id"], comment)
    for recipient_id in mentions:
        if recipient_id != comment["person_id"]:
            notification = create_notification(
                recipient_id,
                comment_id=comment["id"],
                author_id=comment["person_id"],
                task_id=comment["object_id"],
                type="mention",
            )
            emails_service.send_mention_notification(
                recipient_id, author_id, comment, task
            )
            _emit_notification(notification, recipient_id, task["project_id"])

    return recipient_ids


def get_mentioned_people(project_id, comment):
    """
    Return all people mentioned in the comment: the one listed via their name
    and the one listed via their department.
    """
    # Copy the list: appending in place would corrupt the comment dict,
    # which may come from the cache or be reused by the caller.
    mentions = list(comment["mentions"])
    for department_id in comment["department_mentions"]:
        persons = projects_service.get_department_team(
            project_id, department_id
        )
        for person in persons:
            mentions.append(str(person.id))
    return mentions


def create_notifications_for_task_and_reply(task, comment, reply):
    """
    For given task, comment and reply, create a notification for every assignee
    to the task and to every person participating to this task and comment.
    """
    recipient_ids = get_notification_recipients(task, comment["replies"])
    if reply["person_id"] in recipient_ids:
        recipient_ids.remove(reply["person_id"])
    author_id = reply["person_id"]
    if author_id != comment["person_id"]:
        recipient_ids.add(comment["person_id"])
    task = tasks_service.get_task(comment["object_id"])
    for recipient_id in recipient_ids:
        try:
            notification = create_notification(
                recipient_id,
                comment_id=comment["id"],
                author_id=author_id,
                task_id=task["id"],
                reply_id=reply["id"],
                read=False,
                type="reply",
                created_at=reply["created_at"],
            )
            emails_service.send_reply_notification(
                recipient_id, author_id, comment, task, reply
            )
            _emit_notification(notification, recipient_id, task["project_id"])
        except PersonNotFoundException:
            pass

    mentions = get_mentioned_people(task["project_id"], reply)
    for recipient_id in mentions:
        if recipient_id != reply["person_id"]:
            notification = create_notification(
                recipient_id,
                comment_id=comment["id"],
                author_id=reply["person_id"],
                task_id=task["id"],
                reply_id=reply["id"],
                read=False,
                type="reply-mention",
            )
            emails_service.send_mention_notification(
                recipient_id, author_id, comment, task
            )
            _emit_notification(notification, recipient_id, task["project_id"])

    return recipient_ids


def reset_notifications_for_mentions(comment):
    """
    For given task and comment, delete all mention notifications related
    to the comment and recreate notifications for the mentions listed in the
    comment.
    """
    # Only the mentions: they are the ones rebuilt below. The notifications
    # raised by the replies of that comment belong to the replies, which
    # clean up after themselves in delete_reply, and nothing here would
    # bring them back.
    Notification.delete_all_by(type="mention", comment_id=comment["id"])
    notifications = []
    task = tasks_service.get_task(comment["object_id"])
    author_id = comment["person_id"]
    mentions = get_mentioned_people(task["project_id"], comment)
    for recipient_id in mentions:
        notification = create_notification(
            recipient_id,
            comment_id=comment["id"],
            author_id=author_id,
            task_id=comment["object_id"],
            type="mention",
            created_at=comment["created_at"],
        )
        emails_service.send_mention_notification(
            recipient_id, author_id, comment, task
        )
        notifications.append(notification)
        _emit_notification(notification, recipient_id, task["project_id"])
    return notifications


def create_assignation_notification(task_id, person_id, author_id=None):
    """
    Create a notification following a task assignation.
    """
    task = tasks_service.get_task_raw(task_id)
    if author_id is None:
        author_id = task.assigner_id

    if str(author_id) == person_id:
        return None

    notification = create_notification(
        person_id, author_id=author_id, task_id=task_id, type="assignation"
    )
    emails_service.send_assignation_notification(
        person_id, author_id, task.serialize()
    )
    _emit_notification(notification, person_id, str(task.project_id))
    return notification


def get_recent_notifications(notification_type=None):
    """
    Return last notification created. This function is used mainly for testing
    purpose.
    """
    query = Notification.query
    if notification_type is not None:
        query = query.filter_by(type=notification_type)
    return fields.serialize_value(query.limit(100).all())


def get_notifications_for_project(project_id, page=0):
    """
    Return all notifications for given project.
    """
    query = (
        Notification.query.join(Task)
        .filter(Task.project_id == project_id)
        .order_by(Notification.updated_at.desc())
    )
    return query_utils.get_paginated_results(query, page)


def notify_clients_playlist_ready(
    playlist, studio_id=None, department_id=None
):
    """
    Notify clients that given playlist is ready.
    """
    author = persons_service.get_current_user()
    project_id = playlist["project_id"]
    query = (
        Person.query.join(ProjectPersonLink)
        .filter(Person.is_bot == False)
        .filter(func.coalesce(ProjectPersonLink.role, Person.role) == "client")
        .filter(ProjectPersonLink.project_id == project_id)
    )

    if studio_id is not None and studio_id != "":
        query = query.filter(Person.studio_id == studio_id)

    if department_id is not None and department_id != "":
        query = (
            query.join(DepartmentLink)
            .filter(DepartmentLink.department_id == department_id)
            .distinct()
        )

    for client in query.all():
        recipient_id = str(client.id)
        author_id = author["id"]
        created_at = date_helpers.get_now()
        notification = create_notification(
            recipient_id,
            author_id=author_id,
            playlist_id=playlist["id"],
            type="playlist-ready",
            created_at=created_at,
        )
        emails_service.send_playlist_ready_notification(
            recipient_id, author_id, playlist
        )
        _emit_notification(notification, recipient_id, playlist["project_id"])
