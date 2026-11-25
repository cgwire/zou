import datetime
import uuid

from sqlalchemy import or_

from zou.app.exceptions import (
    PersonNotFoundException,
    PlaylistShareLinkNotFoundException,
    PreviewFileNotFoundException,
    WrongParameterException,
)
from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.services import (
    attachment_files_service,
    comments_service,
    deletion_service,
    emails_service,
    files_service,
    notifications_service,
    persons_service,
    playlists_service,
    projects_service,
    task_types_service,
    tasks_service,
)
from zou.app.utils import auth, events, fields

# Entity types for which "parent" is a parent record (shot/seq/episode/…).
# For other types, the entity type name is the logical parent (for
# example, assets).
_SHOT_LIKE_ENTITY_TYPE_NAMES = frozenset(
    ("Shot", "Sequence", "Episode", "Edit", "Concept")
)


def _get_expiration_datetime(expiration_date):
    """
    Change the expiration date of a share link into the instant when the
    link stops working. A date-only value means the full day. A manager
    who sets the link to expire on the 10th expects it to work on the 10th.
    Because of this, a date-only value becomes the last second of the day, not
    the first. A full timestamp stays as it is.
    """
    if not expiration_date:
        return None
    try:
        return datetime.datetime.combine(
            datetime.date.fromisoformat(expiration_date), datetime.time.max
        )
    except ValueError:
        pass
    try:
        return datetime.datetime.fromisoformat(expiration_date)
    except ValueError:
        raise WrongParameterException(
            f"{expiration_date} is not a valid ISO 8601 date"
        )


def create_share_link(
    playlist_id,
    person_id,
    expiration_date=None,
    can_comment=True,
    can_download=False,
    password=None,
):
    """
    Make a share link for a playlist. Only managers and higher roles must
    call this function. The resource level does this check.
    """
    playlists_service.get_playlist(playlist_id)
    token = str(uuid.uuid4())
    # Keep a hash of the password at rest. Because of this, a DB leak (or a
    # manager who gets the share link list) never shows the cleartext
    # credential. The service stores an empty or missing password as NULL:
    # check_share_link_password then sees the link as unprotected.
    # encrypt_password returns bytes. Decode them to str, so that the String
    # column gets a real hash and not the literal bytes repr.
    password_hash = (
        auth.encrypt_password(password).decode("utf-8") if password else None
    )
    share_link = PlaylistShareLink.create(
        token=token,
        playlist_id=playlist_id,
        created_by=person_id,
        expiration_date=_get_expiration_datetime(expiration_date),
        can_comment=can_comment,
        can_download=can_download,
        password=password_hash,
    )
    return share_link.serialize()


def get_share_links_for_playlist(playlist_id):
    """
    Return all the active share links of a playlist.
    """
    playlists_service.get_playlist(playlist_id)
    links = PlaylistShareLink.get_all_by(
        playlist_id=playlist_id, is_active=True
    )
    return [link.serialize() for link in links]


def revoke_share_link(token):
    """
    Deactivate a share link. Do not delete it.
    """
    share_link = get_share_link_by_token_raw(token)
    share_link.update({"is_active": False})
    return share_link.serialize()


def get_share_link_by_token_raw(token):
    """
    Return the raw ORM share link for a token. If no link has this token,
    raise PlaylistShareLinkNotFoundException.
    """
    share_link = PlaylistShareLink.get_by(token=token)
    if share_link is None:
        raise PlaylistShareLinkNotFoundException
    return share_link


def validate_share_token(token):
    """
    Make sure that a share token is active and not expired. If the token
    is valid, return the serialized share link. If not, raise the related
    exception.

    check_share_link_password checks the password of a protected link
    separately, one time per request, in the route decorator. The service
    functions that validate the token again do not have the password.
    """
    share_link = get_share_link_by_token_raw(token)
    check_share_link_usable(share_link)
    return share_link.serialize()


def check_share_link_usable(share_link):
    """
    If the given share link is inactive or expired, raise
    PlaylistShareLinkNotFoundException.
    """
    if not share_link.is_active:
        raise PlaylistShareLinkNotFoundException

    if share_link.expiration_date is not None:
        now = datetime.datetime.now(datetime.timezone.utc)
        expiration = share_link.expiration_date
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=datetime.timezone.utc)
        if now > expiration:
            raise PlaylistShareLinkNotFoundException


def check_share_link_password(token, password):
    """
    If the link is protected and ``password`` is missing or wrong, raise
    PlaylistShareLinkNotFoundException. A link without a password accepts
    all passwords.
    """
    share_link = get_share_link_by_token_raw(token)
    if share_link.password:
        # Constant-time bcrypt verify. Never use a plain `!=`.
        if not password:
            raise PlaylistShareLinkNotFoundException
        try:
            if not auth.check_password(share_link.password, password):
                raise PlaylistShareLinkNotFoundException
        except (ValueError, TypeError):
            raise PlaylistShareLinkNotFoundException


def get_shared_playlist(token):
    """
    Return the playlist data that a share token gives access to.

    First, validate the token. The shots have the same preview-file data as
    the public GET endpoint (``preview_file_task_id``,
    ``preview_file_previews``…). For shots added through the playlist
    builder, the raw ``playlist.shots`` JSON stores only ``entity_id`` and
    ``preview_file_id``. Without this data, the guards that compare task
    IDs or sub-revision IDs always fail for those playlists.
    """
    share_link = validate_share_token(token)
    return get_share_link_playlist(share_link)


def get_share_link_playlist(share_link):
    """
    Return the playlist of a validated share link as the link shares it.
    The playlist has the preview-file data. Each shot has only the revision
    that the playlist positions (see hide_other_revisions).
    """
    playlist = playlists_service.get_playlist_with_preview_file_revisions(
        share_link["playlist_id"]
    )
    return hide_other_revisions(playlist)


def is_preview_file_in_shared_playlist(token, preview_file_id):
    """
    Membership check for all the shared-playlist endpoints that serve files
    (thumbnail, original, movie, download…).

    A shared playlist is read-only for the viewer. Because of this, the share
    link serves only the previews of the positioned revision of each shot. The
    check accepts one of these:

    - the exact preview_file_id stored on a shot.
    - another preview file with the same (task, revision) as the positioned
      one. One revision can have many previews (different positions).

    The same entity can occur many times in a playlist. Each shot can have
    a different task type or preview file (for example, the review of the
    texturing, posing and expression previews of one asset). Because of this,
    the check gets *all* the previews positioned for the requested entity. An
    older version used one entity -> preview_file_id map. This map kept only
    the last shot, and refused (403) the previews positioned on the other
    shots.
    """
    share_link = validate_share_token(token)
    playlist = Playlist.get(share_link["playlist_id"])
    if playlist is None or not playlist.shots:
        return False
    preview_file = files_service.get_preview_file(preview_file_id)
    task = tasks_service.get_task(preview_file["task_id"])
    entity_id = str(task["entity_id"])

    positioned_ids = {
        str(shot["preview_file_id"])
        for shot in playlist.shots
        if str(shot.get("entity_id") or shot.get("id")) == entity_id
        and shot.get("preview_file_id")
    }
    if not positioned_ids:
        return False
    if str(preview_file_id) in positioned_ids:
        return True

    # Accept the other positions of a positioned revision: one revision
    # can have many preview files (same task, same revision, different
    # position). A different revision stays rejected. The same revision
    # number on another task type of the entity also stays rejected.
    for positioned_id in positioned_ids:
        try:
            main_preview_file = files_service.get_preview_file(positioned_id)
        except PreviewFileNotFoundException:
            # A deleted preview can stay referenced in playlist.shots (the
            # deletion does not remove it from the shots column). Skip the
            # dangling ID, so that it does not hide a valid match.
            continue
        if (
            str(main_preview_file["task_id"]) == str(preview_file["task_id"])
            and main_preview_file["revision"] == preview_file["revision"]
        ):
            return True
    return False


class GuestCommentForbidden(Exception):
    pass


class GuestCommentNotFound(Exception):
    pass


def _load_guest_comment(comment_id, guest_id, token):
    """
    Get a comment by its ID and make sure of these two conditions:

    - (a) the given guest wrote the comment.
    - (b) the comment is on a task of the playlist that the share token
      shows.

    Without (b), a guest who commented on tasks of many playlists can
    change all these comments through one share link.

    Raises :class:`GuestCommentForbidden` or :class:`GuestCommentNotFound`.
    """
    if not guest_id:
        raise GuestCommentForbidden
    # Make sure that the guest exists AND that this share link created it.
    # This refuses guest UUIDs that leaked from another link.
    share_link = validate_share_token(token)
    try:
        get_guest_for_share_link(guest_id, share_link)
    except Exception:
        raise GuestCommentForbidden
    try:
        comment = comments_service.get_comment(comment_id)
    except Exception:
        raise GuestCommentNotFound
    if str(comment.get("person_id")) != str(guest_id):
        raise GuestCommentForbidden
    task_id = comment.get("object_id")
    if task_id is None:
        raise GuestCommentForbidden
    # Use the enriched playlist, so that preview_file_task_id is set for
    # the shots added through the playlist builder. At rest, these shots
    # store only entity_id / preview_file_id.
    playlist = playlists_service.get_playlist_with_preview_file_revisions(
        share_link["playlist_id"]
    )
    playlist_task_ids = {
        str(shot.get("preview_file_task_id"))
        for shot in playlist.get("shots", []) or []
        if shot.get("preview_file_task_id")
    }
    if str(task_id) not in playlist_task_ids:
        raise GuestCommentForbidden
    return comment


def update_guest_comment(comment_id, guest_id, data, token):
    """
    Update a comment that a guest wrote. ``data`` can contain ``text``,
    ``checklist`` and ``task_status_id``. The function causes the same side
    effects as the usual CRUD update: reset of mentions, cache, events, and
    reset of the task status if necessary.

    The function uses the ``token`` to limit the comment to the playlist of
    the share link. It also uses it to refuse ``task_status_id`` values
    that do not have the client-allowed flag. A guest must not set a status
    that only managers can set.
    """

    instance = _load_guest_comment(comment_id, guest_id, token)

    new_status_id = data.get("task_status_id")
    status_changed = bool(
        new_status_id and instance.get("task_status_id") != new_status_id
    )
    if status_changed:
        try:
            new_status = task_types_service.get_task_status(new_status_id)
        except Exception:
            raise GuestCommentForbidden
        project_id = tasks_service.get_task(instance["object_id"])[
            "project_id"
        ]
        if not projects_service.is_task_status_client_allowed(
            project_id, new_status
        ):
            raise GuestCommentForbidden
    previous_status_id = instance.get("task_status_id")
    # Use the value, as the comment route does: the guest panel of Kitsu
    # sends the text again with each tick of the checklist.
    text_changed = "text" in data and (data["text"] or "") != instance["text"]

    comment_row = Comment.get(comment_id)
    if "text" in data:
        comment_row.text = data["text"] or ""
    if "checklist" in data:
        comment_row.checklist = data["checklist"] or []
    if new_status_id:
        comment_row.task_status_id = new_status_id
    comment_row.editor_id = guest_id
    comment_row.save()

    comments_service.clear_comment_cache(comment_id)
    updated = comments_service.reset_mentions(
        comments_service.get_comment(comment_id)
    )

    task_id = updated["object_id"]
    task = tasks_service.get_task(task_id)
    if status_changed:
        tasks_service.reset_task_data(task_id)
        events.emit(
            "task:status-changed",
            {
                "task_id": task_id,
                "new_task_status_id": new_status_id,
                "previous_task_status_id": previous_status_id,
                "person_id": guest_id,
            },
            project_id=task["project_id"],
        )
    comments_service.clear_comment_cache(comment_id)
    if text_changed:
        notifications_service.reset_notifications_for_mentions(
            updated,
            guest_id,
            comments_service.get_text_mentions(
                task["project_id"], instance["text"]
            ),
        )
    events.emit(
        "comment:update",
        {
            "comment_id": updated["id"],
            "task_id": task_id,
            "person_id": updated["person_id"],
            "for_client": updated["for_client"],
        },
        project_id=task["project_id"],
    )
    return _serialize_enriched_comment(comment_id)


def delete_guest_comment(comment_id, guest_id, token):
    """
    Delete a comment that a guest wrote. The function causes the same side
    effects as the usual CRUD delete: removal through ``deletion_service``,
    reset of the task data, and a task status event if the status changed.

    The ``token`` limits the function to the share link. Because of this, a
    guest cannot delete their comment on a task that is not part of this
    playlist.
    """

    instance = _load_guest_comment(comment_id, guest_id, token)

    task_id = instance["object_id"]
    task_before = tasks_service.get_task(task_id)
    previous_status_id = task_before["task_status_id"]

    deletion_service.remove_comment(comment_id)
    tasks_service.reset_task_data(task_id)
    comments_service.clear_comment_cache(comment_id)

    task_after = tasks_service.get_task(task_id)
    new_status_id = task_after["task_status_id"]
    if previous_status_id != new_status_id:
        events.emit(
            "task:status-changed",
            {
                "task_id": task_id,
                "new_task_status_id": new_status_id,
                "previous_task_status_id": previous_status_id,
                "person_id": guest_id,
            },
            project_id=task_after["project_id"],
        )


def _serialize_enriched_comment(comment_id):
    """
    Return a comment dict with `attachment_files` expanded to objects (id,
    name, extension and size). Because of this, the shared client can show file
    names and sizes without more lookups. The dict also has the authors of the
    replies, as in the comment list.
    """
    from zou.app.models.attachment_file import AttachmentFile

    comment = comments_service.get_comment(comment_id, relations=True)
    ids = comment.get("attachment_files") or []
    if ids and all(isinstance(item, str) for item in ids):
        attachments = AttachmentFile.query.filter(
            AttachmentFile.id.in_(ids)
        ).all()
        comment["attachment_files"] = [af.present() for af in attachments]
    comments_service.embed_reply_authors([comment])
    return comment


def add_guest_comment_attachments(comment_id, guest_id, files, token):
    """
    Attach uploaded files to a comment that the given guest wrote. The
    ``token`` limits the function to the playlist of the share link. Return
    the updated comment dict (with relations).
    """

    comment = _load_guest_comment(comment_id, guest_id, token)
    comments_service.add_attachments_to_comment(comment, files)
    return _serialize_enriched_comment(comment_id)


def download_shared_attachment(token, attachment_id, file_name):
    """
    Serve an attachment file of a comment that this share link shows. The
    comment is a guest comment, or has for_client=True, on a task of the
    playlist. If this link does not serve the attachment, raise
    ``GuestCommentNotFound``.
    """
    from flask import send_file as flask_send_file

    attachment = attachment_files_service.get_attachment_file(attachment_id)
    comment_id = attachment.get("comment_id")
    if not comment_id:
        raise GuestCommentNotFound

    comment = comments_service.get_comment(comment_id)
    task_id = comment.get("object_id")
    if not task_id:
        raise GuestCommentNotFound

    # The comment must belong to a task in the playlist that this token
    # shares. It must also be visible (guest or for_client).
    playlist = get_shared_playlist(token)
    task_ids = {
        str(shot.get("preview_file_task_id"))
        for shot in playlist.get("shots", [])
        if shot.get("preview_file_task_id")
    }
    if str(task_id) not in task_ids:
        raise GuestCommentNotFound

    author_is_guest = False
    if comment.get("person_id"):
        person = persons_service.get_person(comment["person_id"])
        author_is_guest = bool(person.get("is_guest"))
    if not (comment.get("for_client") or author_is_guest):
        raise GuestCommentNotFound

    file_path = attachment_files_service.get_attachment_file_path(attachment)
    return flask_send_file(
        file_path,
        conditional=True,
        mimetype=attachment["mimetype"],
        # Serve safe raster images inline. Force a download for all other
        # files. This path has no authentication (share link) and the attacker
        # controls the mimetype. Because of this, an inline HTML/SVG file can
        # cause a stored XSS in the origin of Kitsu.
        as_attachment=not comments_service.is_inline_safe_mimetype(
            attachment["mimetype"]
        ),
        download_name=attachment["name"],
    )


def remove_guest_comment_attachment(
    comment_id, guest_id, attachment_id, token
):
    """
    Remove one attachment from a comment that the given guest wrote. The
    ``token`` limits the function to the playlist of the share link.
    """
    from zou.app.models.attachment_file import AttachmentFile

    _load_guest_comment(comment_id, guest_id, token)
    attachment = AttachmentFile.get(attachment_id)
    if attachment is None or str(attachment.comment_id) != str(comment_id):
        raise GuestCommentNotFound
    attachment_files_service.remove_attachment_file(attachment)


def get_shared_task_comments(task_id):
    """
    Return the comments of a task that the shared context shows: the
    comments with `for_client=True` and the comments of guests. They have
    their attachment files and the authors of their replies. This function
    does not use comments_service.get_comments, because that function
    requires a current user authenticated with a JWT.
    """

    query = comments_service.prepare_query(
        task_id, is_client=True, is_manager=False
    )
    comments, _ = comments_service.run_task_comments_query(query)

    guest_ids = {
        str(person_id)
        for (person_id,) in Person.query.filter_by(is_guest=True)
        .with_entities(Person.id)
        .all()
    }
    visible = []
    for comment in comments:
        author_id = str(comment.get("person_id", ""))
        is_guest_author = author_id in guest_ids
        if not (comment.get("for_client") or is_guest_author):
            continue
        if comment.get("person"):
            comment["person"]["is_guest"] = is_guest_author
        visible.append(comment)

    if visible:
        attachment_file_map = (
            attachment_files_service.build_attachment_map_for_comments(
                [comment["id"] for comment in visible]
            )
        )
        for comment in visible:
            comment["attachment_files"] = attachment_file_map.get(
                comment["id"], []
            )
        comments_service.embed_reply_authors(visible)
    return visible


def _get_shown_task_ids(share_link):
    """
    Return the IDs of the tasks whose comments the page of a share link
    lists. The comment list gets them from the enriched shots:

    - the task of the positioned preview, if it belongs to an entity of the
      playlist.
    - if not, the task that the shot names.

    The function reads only the shots. It does not load the preview
    revisions that the enrichment loads.
    """
    playlist = Playlist.get(share_link["playlist_id"])
    shots = (playlist.shots if playlist is not None else None) or []
    entity_ids = [
        shot.get("id") or shot.get("shot_id") or shot.get("entity_id")
        for shot in shots
    ]
    preview_file_ids = [
        shot["preview_file_id"]
        for shot in shots
        if fields.is_valid_id(shot.get("preview_file_id"))
    ]
    positioned = {}
    if preview_file_ids:
        positioned = {
            str(preview_file_id): str(task_id)
            for preview_file_id, task_id in PreviewFile.query.join(Task)
            .filter(PreviewFile.id.in_(preview_file_ids))
            .filter(Task.entity_id.in_([e for e in entity_ids if e]))
            .with_entities(PreviewFile.id, PreviewFile.task_id)
        }
    task_ids = {
        positioned.get(
            str(shot.get("preview_file_id")), shot.get("preview_file_task_id")
        )
        for shot in shots
    }
    task_ids.discard(None)
    return task_ids


def is_person_shown_by_share_link(share_link, person_id):
    """
    Return True if the page of a validated share link shows the given
    person. The person is the author of a listed comment (with the client
    flag, or from a guest), or of a reply to one. Each avatar of the page
    does this check.
    """
    task_ids = _get_shown_task_ids(share_link)
    if not task_ids:
        return False
    rows = (
        Comment.query.join(Person, Comment.person_id == Person.id)
        .filter(Comment.object_id.in_(task_ids))
        .filter(or_(Comment.for_client.is_(True), Person.is_guest.is_(True)))
        .with_entities(Comment.person_id, Comment.replies)
        .all()
    )
    person_id = str(person_id)
    return any(
        str(author_id) == person_id
        or any(
            str(reply.get("person_id")) == person_id for reply in replies or []
        )
        for author_id, replies in rows
    )


def _enrich_shared_playlist_project_line(playlist_dict):
    """
    Add the project name and fps to the playlist. A shared viewer has no
    authenticated access to the project store.
    """
    project_id = playlist_dict.get("project_id")
    if not project_id:
        return
    project = projects_service.get_project(str(project_id))
    playlist_dict["project_fps"] = project.get("fps")
    playlist_dict["project_name"] = project.get("name")


def _load_task_styling_by_task_id(task_ids):
    """
    Return the (task_type_by_task_id, task_status_color_by_task_id) dicts.
    """
    if not task_ids:
        return {}, {}

    rows = (
        Task.query.join(TaskType, TaskType.id == Task.task_type_id)
        .join(TaskStatus, TaskStatus.id == Task.task_status_id)
        .filter(Task.id.in_(task_ids))
        .add_columns(
            Task.id,
            TaskType.id,
            TaskType.name,
            TaskType.color,
            TaskType.for_entity,
            TaskStatus.color,
        )
        .all()
    )
    task_type_by_task_id = {}
    task_status_color_by_task_id = {}
    for (
        _,
        task_id,
        task_type_id,
        task_type_name,
        task_type_color,
        task_type_for_entity,
        task_status_color,
    ) in rows:
        tid = str(task_id)
        task_type_by_task_id[tid] = {
            "id": str(task_type_id),
            "name": task_type_name,
            "color": task_type_color,
            "for_entity": task_type_for_entity,
        }
        task_status_color_by_task_id[tid] = task_status_color
    return task_type_by_task_id, task_status_color_by_task_id


def _parent_name_for_shot_entry(entity, entity_type_name, parent_map):
    """
    Return the value shown as the parent of a playlist entry. For shot-like
    entities, it is the name of the parent record. For other entities, it is
    the entity type name.
    """
    if entity_type_name in _SHOT_LIKE_ENTITY_TYPE_NAMES:
        if entity.parent_id is None:
            return ""
        return parent_map.get(str(entity.parent_id), "")
    return entity_type_name


def _is_for_all_episodes(playlist_dict):
    """
    Read the flag as the playlist lists do. If a playlist is attached to an
    episode, it belongs to that episode, whatever the value of is_for_all.
    """
    if playlist_dict.get("episode_id"):
        return False
    return bool(playlist_dict.get("is_for_all"))


def _prefix_parents_with_their_episode(parents, parent_map):
    """
    Sequence names repeat across episodes. In a playlist for all episodes,
    add the name of the parent of each parent. For a sequence, this is its
    episode ("E01 / S01"). Return the parent map with these names.
    """
    episode_ids = {str(p.parent_id) for p in parents if p.parent_id}
    if not episode_ids:
        return parent_map
    episode_names = {
        str(episode.id): episode.name
        for episode in Entity.query.filter(Entity.id.in_(episode_ids)).all()
    }
    prefixed_map = dict(parent_map)
    for parent in parents:
        episode_name = episode_names.get(str(parent.parent_id))
        if episode_name:
            prefixed_map[str(parent.id)] = f"{episode_name} / {parent.name}"
    return prefixed_map


def _apply_task_styling_to_shot(
    shot, task_id, task_type_by_task_id, task_status_color_by_task_id
):
    """
    Add the task type and status colors, which a shared viewer cannot get.
    """
    tid = str(task_id)
    task_type = task_type_by_task_id.get(tid)
    if task_type:
        shot["preview_file_task_type"] = task_type
        shot["preview_file_task_type_name"] = task_type["name"]
    color = task_status_color_by_task_id.get(tid)
    if color:
        shot["task_status_color"] = color


def hide_other_revisions(playlist_dict):
    """
    Empty the revision list of each shot of a playlist that a share link
    serves. The link shares only the revision that the playlist positions.
    The preview_file fields contain this revision and its other positions.
    The revisions of all the task types of the entity, with their
    annotations, are only for the revision switcher of the team.

    The list stays an object, because the player reads it on each shot.
    Each shot gets its own list. The positions of a revision are grouped
    per task type. Because of this, they also contain the preview with the same
    number on another task of that type, which the link does not share.
    """
    for shot in playlist_dict.get("shots") or []:
        shot["preview_files"] = {}
        if "preview_file_previews" in shot:
            task_id = shot.get("preview_file_task_id")
            shot["preview_file_previews"] = [
                preview
                for preview in shot["preview_file_previews"]
                if preview.get("task_id") == task_id
            ]
    return playlist_dict


def enrich_shots_with_entity_info(playlist_dict):
    """
    Add `name` and `parent_name` (sequence, episode or asset_type name) to
    each shot entry of the playlist. The stored `playlist.shots` keeps only
    references to previews and entities. In the shared context, consumers
    have no authenticated access to the entity, asset and shot stores.
    Because of this, the function must add the names here. In a playlist for
    all episodes, the sequence of a shot comes with its episode. The function
    also adds the project name and fps, and the task type and task status color
    of each shot.
    """
    _enrich_shared_playlist_project_line(playlist_dict)

    shots = playlist_dict.get("shots") or []
    entity_ids = [shot["id"] for shot in shots if shot.get("id")]
    if not entity_ids:
        return playlist_dict

    entities = Entity.query.filter(Entity.id.in_(entity_ids)).all()
    entity_map = {str(e.id): e for e in entities}

    parent_ids = {str(e.parent_id) for e in entities if e.parent_id}
    parent_map = {}
    if parent_ids:
        parents = Entity.query.filter(Entity.id.in_(parent_ids)).all()
        parent_map = {str(p.id): p.name for p in parents}
        if _is_for_all_episodes(playlist_dict):
            parent_map = _prefix_parents_with_their_episode(
                parents, parent_map
            )

    type_ids = {str(e.entity_type_id) for e in entities if e.entity_type_id}
    type_map = {}
    if type_ids:
        type_map = {
            str(t.id): t.name
            for t in EntityType.query.filter(EntityType.id.in_(type_ids)).all()
        }

    task_ids = {
        s["preview_file_task_id"]
        for s in shots
        if s.get("preview_file_task_id")
    }
    task_type_by_task_id, task_status_color_by_task_id = (
        _load_task_styling_by_task_id(task_ids)
    )

    for shot in shots:
        entity = entity_map.get(str(shot.get("id")))
        if entity is None:
            continue
        shot["name"] = entity.name
        entity_type_name = type_map.get(str(entity.entity_type_id), "")
        shot["parent_name"] = _parent_name_for_shot_entry(
            entity, entity_type_name, parent_map
        )
        task_id = shot.get("preview_file_task_id")
        if not task_id:
            continue
        _apply_task_styling_to_shot(
            shot,
            task_id,
            task_type_by_task_id,
            task_status_color_by_task_id,
        )
    return playlist_dict


def create_guest(token, first_name, last_name=""):
    """
    Create a guest Person for the share link of ``token``.

    Each guest is bound to the share link that created it (through
    ``Person.data['share_link_id']``). The function never finds a guest by
    name. If a viewer types the name of a reviewer who commented before,
    the viewer must not get their identity. The viewer keeps their guest id
    and uses it again through get_guest_for_share_link. The guest always
    has ``is_guest=True`` and ``role=client``.
    """
    share_link = validate_share_token(token)
    share_link_id = str(share_link["id"])
    first_name = (first_name or "Guest").strip()
    last_name = (last_name or "").strip()

    guest = Person.create(
        first_name=first_name,
        last_name=last_name,
        email=f"guest-{uuid.uuid4().hex[:8]}@guest.kitsu",
        role="client",
        is_guest=True,
        data={"share_link_id": share_link_id},
    )
    persons_service.clear_person_cache()
    events.emit("person:new", {"person_id": str(guest.id)})
    return guest.serialize()


def get_guest(guest_id):
    """
    Return a guest person. If the person is not found or is not a guest,
    raise an exception.
    """
    person = persons_service.get_person(guest_id)
    if not person.get("is_guest", False):
        raise PlaylistShareLinkNotFoundException
    return person


def get_guest_for_share_link(guest_id, share_link):
    """
    Return a guest person, but only if the given share link created it.
    Use this function each time a request body gives a ``guest_id``.
    Because of this, an attacker with one share token cannot use the guest UUID
    of another reviewer (leaked from a different link) to impersonate them. If
    the guest does not match, raise
    :class:`PlaylistShareLinkNotFoundException`.
    """
    person = get_guest(guest_id)
    if person.get("data", {}).get("share_link_id") != str(share_link["id"]):
        raise PlaylistShareLinkNotFoundException
    return person


def get_share_link_context(share_link):
    """
    Return the minimum context that is necessary to show the playlist of a
    validated share link:

    - what the link allows.
    - the project.
    - its task types.
    - its task statuses.

    No entity is listed. The shots of the playlist have their names, and
    the main preview of an entity can be a revision that the link does not
    share.
    """
    playlist = playlists_service.get_playlist(share_link["playlist_id"])
    project_id = playlist["project_id"]
    project = projects_service.get_project(project_id)

    task_types = projects_service.get_project_task_types(project_id)
    task_statuses = projects_service.get_project_task_statuses(project_id)
    client_allowed_overrides = projects_service.get_client_allowed_overrides(
        project_id
    )

    return {
        "share_link": {
            "can_comment": share_link["can_comment"],
            "can_download": share_link["can_download"],
        },
        "project": {
            "id": project["id"],
            "name": project["name"],
            "fps": project.get("fps"),
            "ratio": project.get("ratio"),
            "resolution": project.get("resolution"),
            "team": [],  # required by Kitsu
        },
        # Do not send `department_id` with the task types. The shared client
        # never fills the department map. Many widgets (EditCommentModal,
        # comment mentions) crash when they try to find an unknown
        # department.
        "task_types": [
            {
                "id": tt["id"],
                "name": tt["name"],
                "color": tt["color"],
                "for_entity": tt.get("for_entity"),
            }
            for tt in task_types
        ],
        "task_statuses": [
            {
                "id": ts["id"],
                "name": ts["name"],
                "short_name": ts["short_name"],
                "color": ts["color"],
                "is_client_allowed": client_allowed_overrides.get(
                    ts["id"], ts.get("is_client_allowed", False)
                ),
                "is_default": ts.get("is_default", False),
                "for_concept": ts.get("for_concept", False),
            }
            for ts in task_statuses
        ],
    }


def send_share_invitations(
    playlist_id,
    token,
    author_id,
    emails=None,
    person_ids=None,
    message=None,
):
    """
    Email a shared-playlist review invitation to one or more recipients.
    The recipients are free-form emails, existing Persons found by ID, or
    both. Return the list of the email addresses that got an invitation,
    without duplicates and normalized. The service keeps no DB record of
    the invitations.

    The function validates the token against the playlist. Because of this, a
    manager who knows *some* token cannot use the URL of a different playlist
    to invite people to a link that the manager does not own.
    """
    from zou.app import config

    share_link = get_share_link_by_token_raw(token)
    if str(share_link.playlist_id) != str(playlist_id):
        raise PlaylistShareLinkNotFoundException
    check_share_link_usable(share_link)

    playlist = playlists_service.get_playlist(playlist_id)
    project = projects_service.get_project(playlist["project_id"])
    author = persons_service.get_person(author_id)

    # Skip the DNS deliverability checks. The invitations must go out also
    # when the domain of the inviter has no MX record. Also, a live DNS
    # request in a request handler is not reliable.
    recipients = {}
    for raw_email in emails or []:
        normalized = auth.validate_email(raw_email, check_deliverability=False)
        recipients.setdefault(
            normalized.lower(),
            {"email": normalized, "locale": None},
        )
    for person_id in person_ids or []:
        try:
            person = persons_service.get_person(str(person_id))
        except PersonNotFoundException:
            continue
        person_email = person.get("email")
        if not person_email:
            continue
        normalized = auth.validate_email(
            person_email, check_deliverability=False
        )
        recipients[normalized.lower()] = {
            "email": normalized,
            "locale": person.get("locale"),
        }

    share_url = (
        f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}"
        f"/playlists/shared/{token}"
    )

    sent = []
    for entry in recipients.values():
        emails_service.send_share_invitation(
            entry["email"],
            author,
            playlist,
            project,
            share_url,
            message=message,
            locale=entry["locale"],
        )
        sent.append(entry["email"])
    return sent
