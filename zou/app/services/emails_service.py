from zou.app import config
from zou.app.utils import emails, chats

from zou.app.services import (
    entities_service,
    names_service,
    persons_service,
    projects_service,
    tasks_service,
)
from zou.app.stores import queue_store
from flask import current_app


def send_notification(person_id, subject, messages):
    """
    Send email notification to given person. Use the job queue if it is
    activated.
    """
    person = persons_service.get_person(person_id)
    email_message = messages["email_message"]
    slack_message = messages["slack_message"]
    mattermost_message = messages["mattermost_message"]
    discord_message = messages["discord_message"]
    if person["notifications_enabled"]:
        if config.ENABLE_JOB_QUEUE:
            queue_store.job_queue.enqueue(
                emails.send_email,
                args=(
                    subject,
                    email_message + get_signature(),
                    person["email"],
                ),
            )
        else:
            emails.send_email(
                subject, email_message + get_signature(), person["email"]
            )

    if person["notifications_slack_enabled"]:
        organisation = persons_service.get_organisation()
        userid = person["notifications_slack_userid"]
        token = organisation.get("chat_token_slack", "")
        if config.ENABLE_JOB_QUEUE:
            queue_store.job_queue.enqueue(
                chats.send_to_slack, args=(token, userid, slack_message)
            )
        else:
            chats.send_to_slack(token, userid, slack_message)

    if person["notifications_mattermost_enabled"]:
        organisation = persons_service.get_organisation()
        userid = person["notifications_mattermost_userid"]
        webhook = organisation.get("chat_webhook_mattermost", "")
        if config.ENABLE_JOB_QUEUE:
            queue_store.job_queue.enqueue(
                chats.send_to_mattermost,
                args=(webhook, userid, mattermost_message),
            )
        else:
            chats.send_to_mattermost(webhook, userid, discord_message)

    if person["notifications_discord_enabled"]:
        organisation = persons_service.get_organisation()
        userid = person["notifications_discord_userid"]
        token = organisation.get("chat_token_discord", "")
        if config.ENABLE_JOB_QUEUE:
            queue_store.job_queue.enqueue(
                chats.send_to_discord,
                args=(current_app, token, userid, discord_message),
            )
        else:
            chats.send_to_discord(current_app, token, userid, discord_message)

    return True


def send_comment_notification(person_id, author_id, comment, task):
    """
    Send a notification emali telling that a new comment was posted to person
    matching given person id.
    """
    person = persons_service.get_person(person_id)
    project = projects_service.get_project(task["project_id"])
    if (
        person["notifications_enabled"]
        or person["notifications_slack_enabled"]
        or person["notifications_mattermost_enabled"]
        or person["notifications_discord_enabled"]
    ):
        task_status = tasks_service.get_task_status(task["task_status_id"])
        task_status_name = task_status["short_name"].upper()
        (author, task_name, task_url) = get_task_descriptors(author_id, task)
        subject = "[Kitsu] %s - %s commented on %s" % (
            task_status_name,
            author["first_name"],
            task_name,
        )
        if len(comment["text"]) > 0:
            email_message = """<p><strong>%s</strong> wrote a comment on <a href="%s">%s</a> and set the status to <strong>%s</strong>.</p>

<p><em>%s</em></p>
""" % (
                author["full_name"],
                task_url,
                task_name,
                task_status_name,
                comment["text"],
            )
            slack_message = """*%s* wrote a comment on <%s|%s> and set the status to *%s*.

_%s_
""" % (
                author["full_name"],
                task_url,
                task_name,
                task_status_name,
                comment["text"],
            )

            discord_message = """*%s* wrote a comment on [%s](%s)> and set the status to *%s*.

_%s_
""" % (
                author["full_name"],
                task_name,
                task_url,
                task_status_name,
                comment["text"],
            )

        else:
            email_message = """<p><strong>%s</strong> changed status of <a href="%s">%s</a> to <strong>%s</strong>.</p>
""" % (
                author["full_name"],
                task_url,
                task_name,
                task_status_name,
            )
            slack_message = """*%s* changed status of <%s|%s> to *%s*.
""" % (
                author["full_name"],
                task_url,
                task_name,
                task_status_name,
            )

            discord_message = """*%s* changed status of [%s](%s) to *%s*.
""" % (
                author["full_name"],
                task_name,
                task_url,
                task_status_name,
            )
        messages = {
            "email_message": email_message,
            "slack_message": slack_message,
            "mattermost_message": {
                "message": slack_message,
                "project_name": project["name"],
            },
            "discord_message": discord_message,
        }
        send_notification(person_id, subject, messages)

    return True


def send_mention_notification(person_id, author_id, comment, task):
    """
    Send a notification email telling that somenone mentioned the
    person matching given person id.
    """
    person = persons_service.get_person(person_id)
    project = projects_service.get_project(task["project_id"])
    if (
        person["notifications_enabled"]
        or person["notifications_slack_enabled"]
        or person["notifications_mattermost_enabled"]
        or person["notifications_discord_enabled"]
    ):
        (author, task_name, task_url) = get_task_descriptors(author_id, task)
        subject = "[Kitsu] %s mentioned you on %s" % (
            author["first_name"],
            task_name,
        )
        email_message = """<p><strong>%s</strong> mentioned you in a comment on <a href="%s">%s</a>:</p>

<p><em>%s</em></p>
""" % (
            author["full_name"],
            task_url,
            task_name,
            comment["text"],
        )
        slack_message = """*%s* mentioned you in a comment on <%s|%s>.

_%s_
""" % (
            author["full_name"],
            task_url,
            task_name,
            comment["text"],
        )

        discord_message = """*%s* mentioned you in a comment on [%s](%s).

_%s_
""" % (
            author["full_name"],
            task_name,
            task_url,
            comment["text"],
        )

        messages = {
            "email_message": email_message,
            "slack_message": slack_message,
            "mattermost_message": {
                "message": slack_message,
                "project_name": project["name"],
            },
            "discord_message": discord_message,
        }
        return send_notification(person_id, subject, messages)
    else:
        return True


def send_assignation_notification(person_id, author_id, task):
    """
    Send a notification email telling that somenone assigned to a task the
    person matching given person id.
    """
    person = persons_service.get_person(person_id)
    project = projects_service.get_project(task["project_id"])
    if (
        person["notifications_enabled"]
        or person["notifications_slack_enabled"]
        or person["notifications_mattermost_enabled"]
        or person["notifications_discord_enabled"]
    ):
        (author, task_name, task_url) = get_task_descriptors(author_id, task)
        subject = "[Kitsu] You were assigned to %s" % task_name
        email_message = """<p><strong>%s</strong> assigned you to <a href="%s">%s</a>.</p>
""" % (
            author["full_name"],
            task_url,
            task_name,
        )
        slack_message = """*%s* assigned you to <%s|%s>.
""" % (
            author["full_name"],
            task_url,
            task_name,
        )
        discord_message = """*%s* assigned you to [%s](%s).
""" % (
            author["full_name"],
            task_name,
            task_url,
        )
        messages = {
            "email_message": email_message,
            "slack_message": slack_message,
            "mattermost_message": {
                "message": slack_message,
                "project_name": project["name"],
            },
            "discord_message": discord_message,
        }
        return send_notification(person_id, subject, messages)
    return True


def get_signature():
    """
    Build signature for Zou emails.
    """
    organisation = persons_service.get_organisation()
    return (
        """
<p>Best,</p>

<p>%s Team</p>"""
        % organisation["name"]
    )


def get_task_descriptors(person_id, task):
    """
    Build task information needed to write notification emails: author object,
    full task name and task URL.
    """
    author = persons_service.get_person(person_id)
    project = projects_service.get_project(task["project_id"])
    task_type = tasks_service.get_task_type(task["task_type_id"])
    entity = entities_service.get_entity(task["entity_id"])
    (entity_name, episode_id) = names_service.get_full_entity_name(
        entity["id"]
    )

    episode_segment = ""
    entity_type = "assets"
    if task_type["for_entity"] == "Shot":
        entity_type = "shots"
    if task_type["for_entity"] == "Edit":
        entity_type = "edits"
    if project["production_type"] == "tvshow":
        episode_segment = "/episodes/%s" % episode_id

    task_name = "%s / %s / %s" % (
        project["name"],
        entity_name,
        task_type["name"],
    )
    task_url = "%s://%s/productions/%s%s/%s/tasks/%s" % (
        config.DOMAIN_PROTOCOL,
        config.DOMAIN_NAME,
        task["project_id"],
        episode_segment,
        entity_type,
        task["id"],
    )
    return (author, task_name, task_url)


def send_reply_notification(person_id, author_id, comment, task, reply):
    """
    Send a notification email telling that a new reply was posted to person
    matching given person id.
    """
    person = persons_service.get_person(person_id)
    if (
        person["notifications_enabled"]
        or person["notifications_slack_enabled"]
    ):
        task_status = tasks_service.get_task_status(task["task_status_id"])
        project = projects_service.get_project(task["project_id"])
        (author, task_name, task_url) = get_task_descriptors(author_id, task)
        subject = "[Kitsu] %s replied on %s" % (
            author["first_name"],
            task_name,
        )
        email_message = """<p><strong>%s</strong> wrote a reply on <a href="%s">%s</a>.</p>

<p><em>%s</em></p>
""" % (
            author["full_name"],
            task_url,
            task_name,
            reply["text"],
        )
        slack_message = """*%s* wrote a reply on <%s|%s>.

_%s_
""" % (
            author["full_name"],
            task_url,
            task_name,
            reply["text"],
        )

        discord_message = """*%s* wrote a reply on [%s](%s).

_%s_
""" % (
            author["full_name"],
            task_name,
            task_url,
            reply["text"],
        )

        messages = {
            "email_message": email_message,
            "slack_message": slack_message,
            "mattermost_message": {
                "message": slack_message,
                "project_name": project["name"],
            },
            "discord_message": discord_message,
        }
        send_notification(person_id, subject, messages)
    return True
