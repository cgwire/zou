import datetime
import uuid

from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.person import Person
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.services import (
    persons_service,
    playlists_service,
    tasks_service,
    projects_service,
)
from zou.app.services.exception import (
    PlaylistShareLinkNotFoundException,
    PlaylistNotFoundException,
)
from zou.app.utils import fields


def create_share_link(
    playlist_id,
    person_id,
    expiration_date=None,
    can_comment=True,
    password=None,
):
    """
    Generate a share link for a playlist. Only managers and above
    should call this (enforced at the resource level).
    """
    playlists_service.get_playlist(playlist_id)
    token = str(uuid.uuid4())
    share_link = PlaylistShareLink.create(
        token=token,
        playlist_id=playlist_id,
        created_by=person_id,
        expiration_date=(
            fields.get_date_object(expiration_date)
            if expiration_date
            else None
        ),
        can_comment=can_comment,
        password=password,
    )
    return share_link.serialize()


def get_share_links_for_playlist(playlist_id):
    """
    Return all active share links for a playlist.
    """
    playlists_service.get_playlist(playlist_id)
    links = PlaylistShareLink.get_all_by(
        playlist_id=playlist_id, is_active=True
    )
    return [link.serialize() for link in links]


def revoke_share_link(token):
    """
    Deactivate a share link without deleting it.
    """
    share_link = get_share_link_by_token_raw(token)
    share_link.update({"is_active": False})
    return share_link.serialize()


def get_share_link_by_token_raw(token):
    """
    Return the raw ORM share link for a token.
    Raises PlaylistShareLinkNotFoundException if not found.
    """
    share_link = PlaylistShareLink.get_by(token=token)
    if share_link is None:
        raise PlaylistShareLinkNotFoundException
    return share_link


def validate_share_token(token, password=None):
    """
    Validate that a share token is active and not expired.
    Returns the serialized share link on success.
    Raises appropriate exceptions on failure.
    """
    share_link = get_share_link_by_token_raw(token)
    if not share_link.is_active:
        raise PlaylistShareLinkNotFoundException

    if share_link.expiration_date is not None:
        now = datetime.datetime.now(datetime.timezone.utc)
        expiration = share_link.expiration_date
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=datetime.timezone.utc)
        if now > expiration:
            raise PlaylistShareLinkNotFoundException

    if share_link.password is not None and share_link.password != "":
        if password != share_link.password:
            raise PlaylistShareLinkNotFoundException

    return share_link.serialize()


def get_shared_playlist(token):
    """
    Return the playlist data accessible via a share token.
    Validates the token first.
    """
    share_link = validate_share_token(token)
    playlist = playlists_service.get_playlist(share_link["playlist_id"])
    return playlist


class GuestCommentForbidden(Exception):
    pass


class GuestCommentNotFound(Exception):
    pass


def _load_guest_comment(comment_id, guest_id):
    """
    Fetch a comment by id and ensure it was authored by the given guest.
    Raises :class:`GuestCommentForbidden` or :class:`GuestCommentNotFound`.
    """
    if not guest_id:
        raise GuestCommentForbidden
    # Ensure the guest actually exists.
    get_guest(guest_id)
    try:
        comment = tasks_service.get_comment(comment_id)
    except Exception:
        raise GuestCommentNotFound
    if str(comment.get("person_id")) != str(guest_id):
        raise GuestCommentForbidden
    return comment


def update_guest_comment(comment_id, guest_id, data):
    """
    Update a comment authored by a guest. Accepts ``text``, ``checklist`` and
    ``task_status_id`` in ``data``. Triggers the same post-update side effects
    as the regular CRUD path (reset mentions, cache, events, task status
    reset when needed).
    """
    from zou.app.models.comment import Comment
    from zou.app.services import comments_service, notifications_service
    from zou.app.utils import events

    instance = _load_guest_comment(comment_id, guest_id)

    new_status_id = data.get("task_status_id")
    status_changed = bool(
        new_status_id and instance.get("task_status_id") != new_status_id
    )
    previous_status_id = instance.get("task_status_id")

    comment_row = Comment.get(comment_id)
    if "text" in data:
        comment_row.text = data["text"] or ""
    if "checklist" in data:
        comment_row.checklist = data["checklist"] or []
    if new_status_id:
        comment_row.task_status_id = new_status_id
    comment_row.editor_id = guest_id
    comment_row.save()

    # reset_mentions walks the mentions table; feed it the relations-loaded
    # dict so it has the `mentions` / `department_mentions` keys it expects.
    tasks_service.clear_comment_cache(comment_id)
    updated = tasks_service.get_comment(comment_id, relations=True)
    comments_service.reset_mentions(updated)

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
    tasks_service.clear_comment_cache(comment_id)
    try:
        notifications_service.reset_notifications_for_mentions(updated)
    except KeyError:
        # Some serialized dicts lack the `mentions` key; guest comments
        # never carry mentions anyway, so ignore.
        pass
    events.emit(
        "comment:update",
        {"comment_id": updated["id"], "task_id": task_id},
        project_id=task["project_id"],
    )
    return _serialize_enriched_comment(comment_id)


def delete_guest_comment(comment_id, guest_id):
    """
    Delete a comment authored by a guest. Triggers the same side effects as
    the regular CRUD delete: removal via ``deletion_service``, task data
    reset and task status event if the status changed.
    """
    from zou.app.services import deletion_service
    from zou.app.utils import events

    instance = _load_guest_comment(comment_id, guest_id)

    task_id = instance["object_id"]
    task_before = tasks_service.get_task(task_id)
    previous_status_id = task_before["task_status_id"]

    deletion_service.remove_comment(comment_id)
    tasks_service.reset_task_data(task_id)
    tasks_service.clear_comment_cache(comment_id)

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
    Return a comment dict with `attachment_files` expanded to full objects
    (same shape as `_run_task_comments_query`'s output), so the shared client
    can render filenames/sizes without extra lookups.
    """
    from zou.app.models.attachment_file import AttachmentFile

    comment = tasks_service.get_comment(comment_id, relations=True)
    ids = comment.get("attachment_files") or []
    if ids and all(isinstance(item, str) for item in ids):
        attachments = AttachmentFile.query.filter(
            AttachmentFile.id.in_(ids)
        ).all()
        comment["attachment_files"] = [af.present() for af in attachments]
    return comment


def add_guest_comment_attachments(comment_id, guest_id, files):
    """
    Attach uploaded files to a comment authored by the given guest.
    Returns the updated comment dict (with relations).
    """
    from zou.app.services import comments_service

    comment = _load_guest_comment(comment_id, guest_id)
    comments_service.add_attachments_to_comment(comment, files)
    return _serialize_enriched_comment(comment_id)


def download_shared_attachment(token, attachment_id, file_name):
    """
    Serve an attachment file linked to a comment that is visible to this
    share link (guest-posted or for_client=True on a task that's part of the
    playlist). Raises ``GuestCommentNotFound`` if the attachment is not
    served by this link.
    """
    from flask import send_file as flask_send_file
    from zou.app.services import comments_service

    attachment = comments_service.get_attachment_file(attachment_id)
    comment_id = attachment.get("comment_id")
    if not comment_id:
        raise GuestCommentNotFound

    comment = tasks_service.get_comment(comment_id)
    task_id = comment.get("object_id")
    if not task_id:
        raise GuestCommentNotFound

    # The comment must belong to a task in the playlist that this token
    # shares, and must be visible (guest or for_client).
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

    file_path = comments_service.get_attachment_file_path(attachment)
    return flask_send_file(
        file_path,
        conditional=True,
        mimetype=attachment["mimetype"],
        as_attachment=False,
        download_name=attachment["name"],
    )


def remove_guest_comment_attachment(comment_id, guest_id, attachment_id):
    """
    Remove a single attachment from a comment authored by the given guest.
    """
    from zou.app.models.attachment_file import AttachmentFile
    from zou.app.services import deletion_service

    _load_guest_comment(comment_id, guest_id)
    attachment = AttachmentFile.get(attachment_id)
    if attachment is None or str(attachment.comment_id) != str(comment_id):
        raise GuestCommentNotFound
    deletion_service.remove_attachment_file(attachment)


def get_shared_task_comments(task_id):
    """
    Return comments visible in the shared context for a task: those flagged
    `for_client=True` plus those posted by a guest. Bypasses
    tasks_service.get_comments which requires a JWT-authenticated current
    user.
    """
    from zou.app.services.tasks_service import (
        _prepare_query,
        _run_task_comments_query,
    )

    query = _prepare_query(task_id, is_client=True, is_manager=False)
    comments, _ = _run_task_comments_query(query)

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
    return visible


# Entity types for which "parent" is a parent record (shot/seq/episode/…).
# For other types, we show the entity type name as the logical parent
# (e.g. assets).
_SHOT_LIKE_ENTITY_TYPE_NAMES = frozenset(
    ("Shot", "Sequence", "Episode", "Edit", "Concept")
)


def _enrich_shared_playlist_project_line(playlist_dict):
    project_id = playlist_dict.get("project_id")
    if not project_id:
        return
    project = projects_service.get_project(str(project_id))
    playlist_dict["project_fps"] = project.get("fps")
    playlist_dict["project_name"] = project.get("name")


def _load_task_styling_by_task_id(task_ids):
    """Return (task_type_by_task_id, task_status_color_by_task_id) dicts."""
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
    if entity_type_name in _SHOT_LIKE_ENTITY_TYPE_NAMES:
        if entity.parent_id is None:
            return ""
        return parent_map.get(str(entity.parent_id), "")
    return entity_type_name


def _apply_task_styling_to_shot(
    shot, task_id, task_type_by_task_id, task_status_color_by_task_id
):
    tid = str(task_id)
    task_type = task_type_by_task_id.get(tid)
    if task_type:
        shot["preview_file_task_type"] = task_type
        shot["preview_file_task_type_name"] = task_type["name"]
    color = task_status_color_by_task_id.get(tid)
    if color:
        shot["task_status_color"] = color


def enrich_shots_with_entity_info(playlist_dict):
    """
    Augment each shot entry in the playlist with `name` and `parent_name`
    (sequence/episode/asset_type name). The stored `playlist.shots` only
    keeps preview/entity references — in the shared context, consumers
    have no auth'd access to entity/asset/shot stores, so names must be
    inlined here.
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
        parent_map = {
            str(p.id): p.name
            for p in Entity.query.filter(Entity.id.in_(parent_ids)).all()
        }

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
    Return or create a guest Person tied to a shared playlist session.

    If a guest already exists with the same first/last name, we reuse it so
    that a returning reviewer recovers ownership of their previous comments
    (the UUID is otherwise volatile since the link itself is the credential
    and no persistent account backs a guest). The guest always has
    `is_guest=True` and `role=client`.
    """
    validate_share_token(token)
    first_name = (first_name or "Guest").strip()
    last_name = (last_name or "").strip()

    existing = Person.query.filter_by(
        is_guest=True,
        first_name=first_name,
        last_name=last_name,
    ).first()
    if existing is not None:
        return existing.serialize()

    guest = Person.create(
        first_name=first_name,
        last_name=last_name,
        email=f"guest-{uuid.uuid4().hex[:8]}@guest.kitsu",
        role="client",
        is_guest=True,
    )
    return guest.serialize()


def get_guest(guest_id):
    """
    Retrieve a guest person. Raises if not found or not a guest.
    """
    person = persons_service.get_person(guest_id)
    if not person.get("is_guest", False):
        raise PlaylistShareLinkNotFoundException
    return person


def get_shared_playlist_context(token):
    """
    Return the minimal project context needed to display a shared
    playlist: task types, task statuses, and entity names referenced
    by the playlist.
    """
    share_link = validate_share_token(token)
    playlist = playlists_service.get_playlist(share_link["playlist_id"])
    project_id = playlist["project_id"]
    project = projects_service.get_project(project_id)

    task_types = projects_service.get_project_task_types(project_id)
    task_statuses = projects_service.get_project_task_statuses(project_id)

    # Collect entity names from playlist shots
    entity_names = {}
    for shot_entry in playlist.get("shots", []):
        entity_id = shot_entry.get("entity_id")
        if entity_id and entity_id not in entity_names:
            try:
                from zou.app.services import entities_service

                entity = entities_service.get_entity(entity_id)
                entity_names[entity_id] = {
                    "id": entity_id,
                    "name": entity.get("name", ""),
                    "preview_file_id": entity.get("preview_file_id"),
                }
            except Exception:
                pass

    return {
        "project": {
            "id": project["id"],
            "name": project["name"],
            "fps": project.get("fps"),
            "ratio": project.get("ratio"),
            "resolution": project.get("resolution"),
        },
        # Task types are sent without `department_id` on purpose: the shared
        # client never populates the department map, and several widgets
        # (EditCommentModal, comment mentions) crash when they try to look
        # up an unknown department.
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
                "is_client_allowed": ts.get("is_client_allowed", False),
                "is_default": ts.get("is_default", False),
                "for_concept": ts.get("for_concept", False),
            }
            for ts in task_statuses
        ],
        "entities": list(entity_names.values()),
    }
