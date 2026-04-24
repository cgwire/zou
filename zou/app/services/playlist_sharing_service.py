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
    Generate a share link for a playlist. Only supervisors and above
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
    Create a guest Person tied to a shared playlist session.
    The guest has is_guest=True, role=client, and no password.
    """
    validate_share_token(token)
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
        "task_types": [
            {
                "id": tt["id"],
                "name": tt["name"],
                "color": tt["color"],
                "for_entity": tt.get("for_entity"),
                "department_id": tt.get("department_id"),
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
