from flasgger import swag_from
from flask_jwt_extended import jwt_required
from sqlalchemy import or_

from zou.app.models.playlist import Playlist
from zou.app.services import (
    permissions_service,
    persons_service,
    playlists_service,
    preview_files_service,
    user_service,
)
from zou.app.exceptions import WrongParameterException

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.utils import fields, permissions


def _check_for_entity(data):
    """
    Reject unknown for_entity values at the CRUD boundary.
    """
    if "for_entity" in data and data["for_entity"] is not None:
        if data["for_entity"] not in playlists_service.VALID_FOR_ENTITY_VALUES:
            raise WrongParameterException(
                f'for_entity must be one of {", ".join(playlists_service.VALID_FOR_ENTITY_VALUES)}'
            )


class PlaylistsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Playlist)

    def get_relations_eager_load(self):
        return [Playlist.build_jobs]

    def check_read_permissions(self, options=None):
        permissions_service.block_access_to_vendor()
        return True

    def add_project_permission_filter(self, query):
        if permissions.has_admin_permissions():
            return query
        # Each playlist follows the role held on its own project: on the
        # ones where the user is a client, only the playlists shared with
        # clients are listed, as the playlists route of a production does,
        # and on the ones where they are a vendor, none, as a playlist read
        # refuses them there.
        project_roles = user_service.get_team_project_roles()
        client_project_ids = [
            project_id
            for project_id, role in project_roles.items()
            if role == "client"
        ]
        vendor_project_ids = [
            project_id
            for project_id, role in project_roles.items()
            if role == "vendor"
        ]
        if vendor_project_ids:
            query = query.filter(
                Playlist.project_id.not_in(vendor_project_ids)
            )
        if client_project_ids:
            query = query.filter(
                or_(
                    Playlist.for_client,
                    Playlist.project_id.not_in(client_project_ids),
                )
            )
        return query.filter(
            user_service.build_team_exists_filter(Playlist.project_id)
        )

    @jwt_required()
    @swag_from("openapi/PlaylistsResource_get.yml")
    def get(self):
        """
        Get playlists
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/PlaylistsResource_post.yml")
    def post(self):
        """
        Create playlist
        """
        return super().post()

    def check_create_permissions(self, playlist):
        permissions_service.check_supervisor_project_access(
            playlist["project_id"]
        )

    def update_data(self, data):
        data = super().update_data(data)
        _check_for_entity(data)
        if "episode_id" in data and data["episode_id"] in ["all", "main"]:
            data["episode_id"] = None
        if "task_type_id" in data and not fields.is_valid_id(
            data["task_type_id"]
        ):
            data["task_type_id"] = None
        if isinstance(data.get("shots"), list):
            preview_files_service.unpin_foreign_preview_files(data["shots"])
        data["created_by"] = persons_service.get_current_user()["id"]
        return data


class PlaylistResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Playlist)

    def check_read_permissions(self, playlist):
        permissions_service.check_playlist_read_access(playlist)

    @jwt_required()
    @swag_from("openapi/PlaylistResource_get.yml")
    def get(self, instance_id):
        """
        Get playlist
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/PlaylistResource_put.yml")
    def put(self, instance_id):
        """
        Update playlist
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/PlaylistResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete playlist
        """
        return super().delete(instance_id)

    def pre_delete(self, playlist):
        playlists_service.remove_playlist_dependents(playlist)

    def check_update_permissions(self, playlist, data):
        return permissions_service.check_playlist_update_access(playlist)

    def pre_update(self, instance_dict, data):
        _check_for_entity(data)
        if "shots" in data:
            # An entry without preview is served without the key, and the
            # client saves it back that way: keep it, with no preview.
            shots = [
                {
                    "entity_id": shot.get("entity_id") or shot.get("id"),
                    "preview_file_id": shot.get("preview_file_id"),
                }
                for shot in data["shots"]
                if isinstance(shot, dict)
                and (shot.get("entity_id") or shot.get("id"))
            ]
            data["shots"] = preview_files_service.unpin_foreign_preview_files(
                shots
            )
        return data

    def check_delete_permissions(self, playlist):
        return permissions_service.check_playlist_update_access(playlist)
