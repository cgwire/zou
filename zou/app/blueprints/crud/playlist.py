from zou.app.models.playlist import Playlist
from zou.app.services import user_service, playlists_service

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.utils import fields


class PlaylistsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Playlist)

    def check_read_permissions(self):
        return True

    def check_create_permissions(self, playlist):
        user_service.check_supervisor_project_access(playlist["project_id"])

    def update_data(self, data):
        data = super().update_data(data)
        if "episode_id" in data and data["episode_id"] in ["all", "main"]:
            data["episode_id"] = None
        if "task_type_id" in data and not fields.is_valid_id(
            data["task_type_id"]
        ):
            data["task_type_id"] = None
        return data


class PlaylistResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Playlist)

    def check_read_permissions(self, playlist):
        user_service.check_project_access(playlist["project_id"])
        user_service.block_access_to_vendor()

    def check_update_permissions(self, playlist, data):
        user_service.check_project_access(playlist["project_id"])
        user_service.block_access_to_vendor()

    def pre_update(self, instance_dict, data):
        if "shots" in data:
            shots = [
                {
                    "entity_id": shot.get("entity_id", shot.get("id", "")),
                    "preview_file_id": shot["preview_file_id"],
                }
                for shot in data["shots"]
                if "preview_file_id" in shot
            ]
            data["shots"] = shots
        return data

    def delete(self, instance_id):
        playlists_service.remove_playlist(instance_id)
        return "", 204
