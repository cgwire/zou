import datetime
import uuid

from zou.app.models.person import Person
from zou.app.models.playlist_share_link import PlaylistShareLink
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
            expiration = expiration.replace(
                tzinfo=datetime.timezone.utc
            )
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
    playlist = playlists_service.get_playlist(
        share_link["playlist_id"]
    )
    return playlist


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
    playlist = playlists_service.get_playlist(
        share_link["playlist_id"]
    )
    project_id = playlist["project_id"]
    project = projects_service.get_project(project_id)

    task_types = projects_service.get_project_task_types(project_id)
    task_statuses = projects_service.get_project_task_statuses(
        project_id
    )

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
                    "preview_file_id": entity.get(
                        "preview_file_id"
                    ),
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
            {"id": tt["id"], "name": tt["name"], "color": tt["color"]}
            for tt in task_types
        ],
        "task_statuses": [
            {
                "id": ts["id"],
                "name": ts["name"],
                "short_name": ts["short_name"],
                "color": ts["color"],
            }
            for ts in task_statuses
        ],
        "entities": list(entity_names.values()),
    }
