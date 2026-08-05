from zou.app import config
from zou.app.utils import emails, chats
from zou.app.utils.email_i18n import get_email_translation

from zou.app.services import (
    entities_service,
    names_service,
    persons_service,
    projects_service,
    shots_service,
    tasks_service,
    templates_service,
)
from zou.app.stores import queue_store

# Chat channels a person can be notified on: the suffix used by the person
# columns, the message keys and the chats sender, then the organisation field
# holding the credential. The sender is resolved at call time, not stored
# here, so that patching zou.app.utils.chats still intercepts it.
CHAT_CHANNELS = [
    ("slack", "chat_token_slack"),
    ("mattermost", "chat_webhook_mattermost"),
    ("discord", "chat_token_discord"),
]


def _is_notified(person):
    """
    Return True when the person expects a notification on at least one
    channel.
    """
    return (
        person["notifications_enabled"]
        or person["notifications_slack_enabled"]
        or person["notifications_mattermost_enabled"]
        or person["notifications_discord_enabled"]
    )


def _get_locale(person):
    """
    Return the locale the person must be written to in.
    """
    return person.get("locale") or persons_service.get_default_locale()


def _build_messages(email_message, slack_message, discord_message, project):
    """
    Build the per channel message map expected by send_notification. The
    mattermost payload carries the project name on top of the slack text.
    """
    return {
        "email_message": email_message,
        "slack_message": slack_message,
        "mattermost_message": {
            "message": slack_message,
            "project_name": project["name"],
        },
        "discord_message": discord_message,
    }


def send_notification(
    person_id, subject, messages, title="", force_email=False, locale=None
):
    """
    Send email notification to given person. Use the job queue if it is
    activated. If locale is provided, the email Content-Language header
    is set accordingly.
    """
    person = persons_service.get_person(person_id)
    email_message = messages["email_message"]
    chat_messages = {
        channel: messages[f"{channel}_message"] for channel, _ in CHAT_CHANNELS
    }
    email_locale = (
        locale or person.get("locale") or persons_service.get_default_locale()
    )
    email_html_body = templates_service.generate_html_body(
        title, email_message, locale=email_locale
    )

    if person["notifications_enabled"] or force_email:
        if config.ENABLE_JOB_QUEUE:
            queue_store.job_queue.enqueue(
                emails.send_email,
                args=(
                    subject,
                    email_html_body,
                    person["email"],
                ),
                kwargs={"locale": email_locale},
            )
        else:
            emails.send_email(
                subject, email_html_body, person["email"], locale=email_locale
            )

    for channel, credential_field in CHAT_CHANNELS:
        if not person[f"notifications_{channel}_enabled"]:
            continue
        organisation = persons_service.get_organisation(sensitive=True)
        send_to_chat = getattr(chats, f"send_to_{channel}")
        args = (
            organisation.get(credential_field, ""),
            person[f"notifications_{channel}_userid"],
            chat_messages[channel],
        )
        if config.ENABLE_JOB_QUEUE:
            queue_store.job_queue.enqueue(send_to_chat, args=args)
        else:
            send_to_chat(*args)

    return True


def send_comment_notification(person_id, author_id, comment, task):
    """
    Send a notification email telling that a new comment was posted to person
    matching given person id. Email content is translated according to the
    recipient's locale.
    """
    person = persons_service.get_person(person_id)
    project = projects_service.get_project(task["project_id"])
    locale = _get_locale(person)
    if _is_notified(person):
        task_status = tasks_service.get_task_status(task["task_status_id"])
        task_status_name = task_status["short_name"].upper()
        author, task_name, task_url = get_task_descriptors(author_id, task)
        subject = get_email_translation(
            locale,
            "comment_subject",
            task_status_name=task_status_name,
            author_first_name=author["first_name"],
            task_name=task_name,
        )
        email_params = {
            "author_full_name": author["full_name"],
            "task_url": task_url,
            "task_name": task_name,
            "task_status_name": task_status_name,
        }
        if len(comment["text"]) > 0:
            email_message = get_email_translation(
                locale,
                "comment_body_with_text",
                comment_text=comment["text"],
                **email_params,
            )
            slack_message = f"""*{author["full_name"]}* wrote a comment on <{task_url}|{task_name}> and set the status to *{task_status_name}*.

_{comment["text"]}_
"""

            discord_message = f"""*{author["full_name"]}* wrote a comment on [{task_name}]({task_url})> and set the status to *{task_status_name}*.

_{comment["text"]}_
"""

        else:
            email_message = get_email_translation(
                locale, "comment_body_status_only", **email_params
            )
            slack_message = f"""*{author["full_name"]}* changed status of <{task_url}|{task_name}> to *{task_status_name}*.
"""

            discord_message = f"""*{author["full_name"]}* changed status of [{task_name}]({task_url}) to *{task_status_name}*.
"""

        title = get_email_translation(locale, "comment_title")
        messages = _build_messages(
            email_message, slack_message, discord_message, project
        )
        send_notification(person_id, subject, messages, title)

    return True


def send_mention_notification(person_id, author_id, comment, task):
    """
    Send a notification email telling that somenone mentioned the
    person matching given person id. Email content is translated
    according to the recipient's locale.
    """
    person = persons_service.get_person(person_id)
    project = projects_service.get_project(task["project_id"])
    locale = _get_locale(person)
    if _is_notified(person):
        author, task_name, task_url = get_task_descriptors(author_id, task)
        subject = get_email_translation(
            locale,
            "mention_subject",
            author_first_name=author["first_name"],
            task_name=task_name,
        )
        email_message = get_email_translation(
            locale,
            "mention_body",
            author_full_name=author["full_name"],
            task_url=task_url,
            task_name=task_name,
            comment_text=comment["text"],
        )
        slack_message = f"""*{author["full_name"]}* mentioned you in a comment on <{task_url}|{task_name}>.

_{comment["text"]}_
"""

        discord_message = f"""*{author["full_name"]}* mentioned you in a comment on [{task_name}]({task_url}).

_{comment["text"]}_
"""
        title = get_email_translation(locale, "mention_title")
        messages = _build_messages(
            email_message, slack_message, discord_message, project
        )
        return send_notification(person_id, subject, messages, title)
    else:
        return True


def send_assignation_notification(person_id, author_id, task):
    """
    Send a notification email telling that somenone assigned to a task the
    person matching given person id. Email content is translated according
    to the recipient's locale.
    """
    person = persons_service.get_person(person_id)
    project = projects_service.get_project(task["project_id"])
    locale = _get_locale(person)
    if _is_notified(person):
        author, task_name, task_url = get_task_descriptors(author_id, task)
        subject = get_email_translation(
            locale, "assignation_subject", task_name=task_name
        )
        email_message = get_email_translation(
            locale,
            "assignation_body",
            author_full_name=author["full_name"],
            task_url=task_url,
            task_name=task_name,
        )
        slack_message = f"""*{author["full_name"]}* assigned you to <{task_url}|{task_name}>.
"""
        discord_message = f"""*{author["full_name"]}* assigned you to [{task_name}]({task_url}).
"""

        title = get_email_translation(locale, "assignation_title")
        messages = _build_messages(
            email_message, slack_message, discord_message, project
        )
        return send_notification(person_id, subject, messages, title)
    return True


def get_task_descriptors(person_id, task):
    """
    Build task information needed to write notification emails: author object,
    full task name and task URL.
    """
    author = persons_service.get_person(person_id)
    project = projects_service.get_project(task["project_id"])
    task_type = tasks_service.get_task_type(task["task_type_id"])
    entity = entities_service.get_entity(task["entity_id"])
    entity_name, episode_id, _ = names_service.get_full_entity_name(
        entity["id"]
    )

    episode_segment = ""
    entity_type = "assets"
    if task_type["for_entity"] == "Shot":
        entity_type = "shots"
    elif task_type["for_entity"] == "Edit":
        entity_type = "edits"
    if project["production_type"] == "tvshow":
        episode_segment = f"/episodes/{episode_id}"

    task_name = f"{project['name']} / {entity_name} / {task_type['name']}"
    task_url = (
        f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}/productions/"
        f"{task['project_id']}{episode_segment}/{entity_type}/tasks/{task['id']}"
    )
    return author, task_name, task_url


def send_reply_notification(person_id, author_id, comment, task, reply):
    """
    Send a notification email telling that a new reply was posted to person
    matching given person id. Email content is translated according to the
    recipient's locale.
    """
    person = persons_service.get_person(person_id)
    locale = _get_locale(person)
    if _is_notified(person):
        tasks_service.get_task_status(task["task_status_id"])
        project = projects_service.get_project(task["project_id"])
        author, task_name, task_url = get_task_descriptors(author_id, task)
        subject = get_email_translation(
            locale,
            "reply_subject",
            author_first_name=author["first_name"],
            task_name=task_name,
        )
        email_message = get_email_translation(
            locale,
            "reply_body",
            author_full_name=author["full_name"],
            task_url=task_url,
            task_name=task_name,
            reply_text=reply["text"],
        )
        slack_message = f"""*{author["full_name"]}* wrote a reply on <{task_url}|{task_name}>.

_{reply["text"]}_
"""

        discord_message = f"""*{author["full_name"]}* wrote a reply on [{task_name}]({task_url}).

_{reply["text"]}_
"""

        title = get_email_translation(locale, "reply_title")
        messages = _build_messages(
            email_message, slack_message, discord_message, project
        )
        send_notification(person_id, subject, messages, title)
    return True


def send_playlist_ready_notification(person_id, author_id, playlist):
    """
    Send a notification email telling that a new playlist is ready to person
    matching given person id. Email content is translated according to the
    recipient's locale.
    """
    person = persons_service.get_person(person_id)
    author = persons_service.get_person(author_id)
    project = projects_service.get_project(playlist["project_id"])
    locale = _get_locale(person)
    # A playlist may carry no episode, or one that no longer exists.
    episode = None
    try:
        episode = shots_service.get_episode(playlist["episode_id"])
    except Exception:
        pass

    if _is_notified(person):
        playlist_url = f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}/productions/{playlist['project_id']}/"

        if episode is not None:
            playlist_url += (
                f"episodes/{episode['id']}/playlists/{playlist['id']}"
            )
        elif (
            project["production_type"] == "tvshow"
            and playlist["for_entity"] == "asset"
        ):
            if playlist["is_for_all"]:
                playlist_url += f"episodes/all/playlists/{playlist['id']}"
            else:
                playlist_url += f"episodes/main/playlists/{playlist['id']}"
        else:
            playlist_url += f"playlists/{playlist['id']}"

        if episode is not None:
            episode_segment = get_email_translation(
                locale,
                "playlist_episode_segment",
                episode_name=episode["name"],
            )
        else:
            episode_segment = ""

        title = get_email_translation(locale, "playlist_title")
        subject = get_email_translation(
            locale,
            "playlist_subject",
            playlist_name=playlist["name"],
            project_name=project["name"],
        )

        email_message = get_email_translation(
            locale,
            "playlist_body",
            author_full_name=author["full_name"],
            playlist_url=playlist_url,
            playlist_name=playlist["name"],
            episode_segment=episode_segment,
            project_name=project["name"],
        )

        if len(playlist["shots"]) > 1:
            email_message += get_email_translation(
                locale,
                "playlist_elements_count",
                count=len(playlist["shots"]),
            )

        slack_message = f"*{author['full_name']}* notifies you that a playlist <{playlist_url}|{playlist['name']}> is ready for a review under {episode_segment}the project {project['name']}."

        discord_message = f"*{author['full_name']}* notifies you that a playlist [{playlist['name']}]({playlist_url}) is ready for a review under {episode_segment}the project {project['name']}."
        messages = _build_messages(
            email_message, slack_message, discord_message, project
        )
        send_notification(
            person_id, subject, messages, title, force_email=True
        )


def send_share_invitation(
    recipient_email,
    author,
    playlist,
    project,
    share_url,
    message=None,
    locale=None,
):
    """
    Send a shared-playlist review invitation by email. Recipients are
    addressed by raw email rather than going through ``Person`` so guests
    who do not have a Kitsu account can be invited too. Fire-and-forget:
    no DB record is kept, no Person is created.
    """
    email_locale = locale or persons_service.get_default_locale()
    title = get_email_translation(email_locale, "share_invitation_title")
    subject = get_email_translation(
        email_locale,
        "share_invitation_subject",
        author_full_name=author["full_name"],
        playlist_name=playlist["name"],
    )
    email_message = get_email_translation(
        email_locale,
        "share_invitation_body",
        author_full_name=author["full_name"],
        playlist_name=playlist["name"],
        project_name=project["name"],
        share_url=share_url,
    )
    if message:
        email_message += get_email_translation(
            email_locale,
            "share_invitation_message_segment",
            message=message,
        )
    email_html_body = templates_service.generate_html_body(
        title, email_message, locale=email_locale
    )
    if config.ENABLE_JOB_QUEUE:
        queue_store.job_queue.enqueue(
            emails.send_email,
            args=(subject, email_html_body, recipient_email),
            kwargs={"locale": email_locale},
        )
    else:
        emails.send_email(
            subject, email_html_body, recipient_email, locale=email_locale
        )
