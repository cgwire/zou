from sqlalchemy.sql import func

from zou.app.exceptions import PersonNotFoundException
from zou.app.models.notification import Notification
from zou.app.models.person import DepartmentLink, Person
from zou.app.models.project import ProjectPersonLink
from zou.app.models.task import Task
from zou.app.services import (
    emails_service,
    permissions_service,
    persons_service,
    projects_service,
    subscriptions_service,
    tasks_service,
)
from zou.app.utils import date_helpers, events, fields, query as query_utils


def _emit_notification(notification, recipient_id, project_id):
    """
    Tell the client of the recipient that a notification arrived. This event is
    not persisted: the notification row is the record, and the event is only
    the live signal.
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
    Create a new notification for the given person and return it as a dict.
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
    Return the set of the ids of the notification recipients for the given
    task:
    - the assignees,
    - the people subscribed to the task or to its sequence,
    - the authors of the given replies.
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


def _with_task_access(person_ids, task):
    """
    Keep only the people who can access the given task. Whatever made them a
    recipient, nobody gets a notification about a comment on a task that the
    API refuses to them.
    """
    kept = []
    for person_id in person_ids:
        try:
            if permissions_service.can_access_task(person_id, task):
                kept.append(person_id)
        except PersonNotFoundException:
            pass
    return kept


def create_notifications_for_task_and_comment(task, comment, change=False):
    """
    For the given task and comment, create a notification for each assignee and
    subscriber of the task. Create a mention notification for each person
    mentioned in the comment. Only the people who can access the task get a
    notification. Send the emails, emit notification:new for each notification
    and return the ids of the recipients that are not mentions.
    """
    recipient_ids = get_notification_recipients(task)
    if comment["person_id"] in recipient_ids:
        recipient_ids.remove(comment["person_id"])
    author_id = comment["person_id"]
    task = tasks_service.get_task(comment["object_id"])
    recipient_ids = _with_task_access(recipient_ids, task)

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
            if permissions_service.can_read_comment(
                recipient_id, comment, task["project_id"]
            ):
                emails_service.send_comment_notification(
                    recipient_id, author_id, comment, task
                )
            _emit_notification(notification, recipient_id, task["project_id"])
        except PersonNotFoundException:
            pass

    mentions = get_mentioned_people(task["project_id"], comment)
    for recipient_id in _with_task_access(mentions, task):
        if recipient_id != comment["person_id"]:
            notification = create_notification(
                recipient_id,
                comment_id=comment["id"],
                author_id=comment["person_id"],
                task_id=comment["object_id"],
                type="mention",
            )
            if permissions_service.can_read_comment(
                recipient_id, comment, task["project_id"]
            ):
                emails_service.send_mention_notification(
                    recipient_id, author_id, comment, task
                )
            _emit_notification(notification, recipient_id, task["project_id"])

    return recipient_ids


def get_mentioned_people(project_id, comment):
    """
    Return all people mentioned in the comment: the people mentioned with their
    name, and the people mentioned with their department.
    """
    # Copy the list: an append in place changes the comment dict. This dict can
    # come from the cache, or the caller can use it again.
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
    For the given task, comment and reply, create a notification for:
    - each assignee and subscriber of the task,
    - the author of the comment,
    - the authors of its replies.

    Create a mention notification for each person mentioned in the reply. Only
    the people who can access the task get a notification. Send the emails,
    emit notification:new for each notification and return the ids of the
    recipients that are not mentions.
    """
    recipient_ids = get_notification_recipients(task, comment["replies"])
    if reply["person_id"] in recipient_ids:
        recipient_ids.remove(reply["person_id"])
    author_id = reply["person_id"]
    if author_id != comment["person_id"]:
        recipient_ids.add(comment["person_id"])
    task = tasks_service.get_task(comment["object_id"])
    recipient_ids = _with_task_access(recipient_ids, task)
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
            if permissions_service.can_read_reply(
                recipient_id, comment, author_id, task["project_id"]
            ):
                emails_service.send_reply_notification(
                    recipient_id, author_id, comment, task, reply
                )
            _emit_notification(notification, recipient_id, task["project_id"])
        except PersonNotFoundException:
            pass

    mentions = get_mentioned_people(task["project_id"], reply)
    for recipient_id in _with_task_access(mentions, task):
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
            if permissions_service.can_read_reply(
                recipient_id, comment, author_id, task["project_id"]
            ):
                emails_service.send_mention_notification(
                    recipient_id, author_id, comment, task
                )
            _emit_notification(notification, recipient_id, task["project_id"])

    return recipient_ids


def reset_notifications_for_mentions(comment, editor_id, previous_mentions):
    """
    Align the mention notifications of the given comment with an edit of its
    text. previous_mentions contains the mentions of the text before the edit.
    They are read in the production as it is now, as the mentions of the new
    text are.

    - The people who are not mentioned anymore lose their notification.
    - The people that the text did not name before get one, if they did not
      make the edit.
    - The other people keep their notification as it is, with its read status,
      or still have none.

    The people with no notification can be the author, an editor who named
    themselves, or a person named before they joined the production. They can
    also have a row that the removal of old data deleted. Return the created
    notifications.
    """
    task = tasks_service.get_task(comment["object_id"])
    # Use the author of the comment, also when another person adds the mention.
    # The listing uses the role of this author to hide the text of a client
    # comment from artists.
    author_id = comment["person_id"]
    mentions = set(get_mentioned_people(task["project_id"], comment))
    named_before = set(
        get_mentioned_people(task["project_id"], previous_mentions)
    )
    # Delete only the mention notifications: this function aligns only them.
    # The notifications that the replies of that comment created belong to the
    # replies. delete_reply removes them, and nothing here can create them
    # again.
    Notification.delete_all_by(
        Notification.person_id.not_in(list(mentions)),
        type="mention",
        comment_id=comment["id"],
    )
    notified_ids = {
        str(notification.person_id)
        for notification in Notification.get_all_by(
            type="mention", comment_id=comment["id"]
        )
    }
    notifications = []
    for recipient_id in _with_task_access(
        mentions - named_before - notified_ids - {str(editor_id)}, task
    ):
        notification = create_notification(
            recipient_id,
            comment_id=comment["id"],
            author_id=author_id,
            task_id=comment["object_id"],
            type="mention",
        )
        if permissions_service.can_read_comment(
            recipient_id, comment, task["project_id"]
        ):
            emails_service.send_mention_notification(
                recipient_id, author_id, comment, task
            )
        notifications.append(notification)
        _emit_notification(notification, recipient_id, task["project_id"])
    return notifications


def create_assignation_notification(task_id, person_id, author_id=None):
    """
    Create a notification after a task assignment, send the email and emit
    notification:new. If the author assigned the task to themselves, return
    None.
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
    Return a maximum of 100 notifications, in no specified order. This function
    is mainly for tests.
    """
    query = Notification.query
    if notification_type is not None:
        query = query.filter_by(type=notification_type)
    return fields.serialize_value(query.limit(100).all())


def get_notifications_for_project(
    project_id, page=0, limit=None, cursor_id=None
):
    """
    Return all notifications of the given project, a page of them, or the
    notifications after a cursor (see query_utils.get_paginated_results).
    """
    query = (
        Notification.query.join(Task)
        .filter(Task.project_id == project_id)
        .order_by(Notification.updated_at.desc())
    )
    return query_utils.get_paginated_results(
        query, page, limit, cursor_id=cursor_id
    )


def notify_clients_playlist_ready(
    playlist, studio_id=None, department_id=None
):
    """
    Tell the clients that the given playlist is ready. For each client of the
    project, create a notification, send an email and emit notification:new.
    Skip the bots and the preview accounts. If a studio or a department is
    given, it limits the recipients.
    """
    author = persons_service.get_current_user()
    project_id = playlist["project_id"]
    query = (
        Person.query.join(ProjectPersonLink)
        .filter(Person.is_bot == False)
        .filter(Person.preview_project_id.is_(None))
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
