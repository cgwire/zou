from zou.app.models.playlist import Playlist
from zou.app.services import user_service, playlists_service

from .base import BaseModelResource, BaseModelsResource


class PlaylistsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Playlist)

    def check_read_permissions(self):
        return True

    def check_create_permissions(self, playlist):
        user_service.check_manager_project_access(playlist["project_id"])

    def update_data(self, data):
        if "episode_id" in data and data["episode_id"] in ["all", "main"]:
            data["episode_id"] = None
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

    def delete(self, instance_id):
        playlists_service.remove_playlist(instance_id)
        return "", 204
