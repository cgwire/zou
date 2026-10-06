from flasgger import swag_from
import slugify

import os

from flask import (
    after_this_request,
    request,
    send_file as flask_send_file,
)
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app import config
from zou.app.mixin import ArgsMixin

from zou.app.blueprints.playlists.schemas import (
    AddEntitiesToPlaylistSchema,
    AddEntityToPlaylistSchema,
    CreatePlaylistShareLinkSchema,
    InviteShareLinkSchema,
    NotifyClientsPlaylistSchema,
    TempPlaylistCreateSchema,
)
from zou.app.services import (
    entities_service,
    notifications_service,
    playlist_sharing_service,
    playlists_service,
    persons_service,
    preview_files_service,
    projects_service,
    shots_service,
    permissions_service,
    user_service,
)
from zou.app.exceptions import (
    BuildJobNotFoundException,
    PlaylistShareLinkNotFoundException,
)
from rq.exceptions import DuplicateJobError
from zou.app.stores import file_store, queue_store
from zou.app.utils import fs, permissions, validation
from zou.utils.movie import EncodingParameters


class ProjectPlaylistsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProjectPlaylistsResource_get.yml")
    def get(self, project_id):
        """
        Get project playlists
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
        page = self.get_page()
        sort_by = self.get_sort_by()
        task_type_id = self.get_text_parameter("task_type_id")
        return playlists_service.all_playlists_for_project(
            project_id,
            for_client=permissions.has_client_permissions(),
            page=page,
            sort_by=sort_by,
            task_type_id=task_type_id,
        )


class EpisodePlaylistsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/EpisodePlaylistsResource_get.yml")
    def get(self, project_id, episode_id):
        """
        Get episode playlists
        """
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()
        page = self.get_page()
        sort_by = self.get_sort_by()
        task_type_id = self.get_text_parameter("task_type_id")
        for_entity = self.get_text_parameter("for_entity")
        if episode_id not in ["main", "all"]:
            shots_service.get_episode(episode_id)
        return playlists_service.all_playlists_for_episode(
            project_id,
            episode_id,
            for_client=permissions.has_client_permissions(),
            page=page,
            sort_by=sort_by,
            task_type_id=task_type_id,
            for_entity=for_entity,
        )


class ProjectPlaylistResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProjectPlaylistResource_get.yml")
    def get(self, project_id, playlist_id):
        """
        Get playlist
        """
        permissions_service.check_project_access(project_id)
        # Refused before the id is looked up, so that a vendor never learns
        # which playlist ids belong to the production.
        permissions_service.block_access_to_vendor()
        playlist = playlists_service.get_project_playlist(
            project_id, playlist_id
        )
        permissions_service.check_playlist_read_access(playlist)
        # The web client loads annotations on demand, so omit the heavy
        # annotation blobs from this payload.
        return playlists_service.get_playlist_with_preview_file_revisions(
            playlist_id, with_annotations=False
        )


class EntityPreviewsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/EntityPreviewsResource_get.yml")
    def get(self, entity_id):
        """
        Get entity previews
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity_id)
        return playlists_service.get_entity_previews_by_task_type(entity_id)


class PlaylistAddEntityResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/PlaylistAddEntityResource_post.yml")
    def post(self, playlist_id):
        """
        Add entity to playlist
        """
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_playlist_update_access(playlist)

        body = validation.validate_request_body(AddEntityToPlaylistSchema)
        [entity] = preview_files_service.unpin_foreign_preview_files(
            [
                {
                    "entity_id": str(body.entity_id),
                    "preview_file_id": (
                        str(body.preview_file_id)
                        if body.preview_file_id
                        else None
                    ),
                }
            ]
        )
        updated_playlist = playlists_service.add_entity_to_playlist(
            playlist_id, entity["entity_id"], entity["preview_file_id"]
        )
        return updated_playlist


class PlaylistAddEntitiesResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/PlaylistAddEntitiesResource_post.yml")
    def post(self, playlist_id):
        """
        Add entities to playlist
        """
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_playlist_update_access(playlist)

        body = validation.validate_request_body(AddEntitiesToPlaylistSchema)
        # A preview of another entity is replaced by the entity's latest.
        entities = preview_files_service.unpin_foreign_preview_files(
            [
                {
                    "entity_id": entity.entity_id,
                    "preview_file_id": entity.preview_file_id,
                }
                for entity in body.entities
            ]
        )
        return playlists_service.add_entities_to_playlist(
            playlist_id, entities
        )


class PlaylistDownloadResource(MethodView):

    @jwt_required()
    @swag_from("openapi/PlaylistDownloadResource_get.yml")
    def get(self, playlist_id, build_job_id):
        """
        Download playlist build
        """
        permissions_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_playlist_access(
            playlist, supervisor_access=True
        )
        build_job = playlists_service.get_build_job(build_job_id)
        if str(build_job["playlist_id"]) != str(playlist_id):
            raise BuildJobNotFoundException

        if build_job["status"] != "succeeded":
            return {"error": True, "message": "Build is not finished"}, 400

        project = projects_service.get_project(playlist["project_id"])
        movie_file_path = fs.get_file_path_and_file(
            config,
            file_store.get_local_movie_path,
            file_store.open_movie,
            "playlists",
            build_job_id,
            "mp4",
        )
        context_name = playlists_service.get_playlist_download_context_name(
            project, playlist
        )
        download_name = (
            f"{slugify.slugify(build_job['created_at'], separator='').replace('t', '_')}"
            f"_{context_name}_"
            f"{slugify.slugify(playlist['name'], separator='_')}.mp4"
        )
        return flask_send_file(
            movie_file_path,
            conditional=True,
            mimetype="video/mp4",
            as_attachment=True,
            download_name=download_name,
        )


class BuildPlaylistMovieResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/BuildPlaylistMovieResource_get.yml")
    def get(self, playlist_id):
        """
        Build playlist movie
        """
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_manager_project_access(
            playlist["project_id"]
        )

        project = projects_service.get_project(playlist["project_id"])
        width, height = preview_files_service.get_preview_file_dimensions(
            project
        )
        fps = preview_files_service.get_preview_file_fps(project)
        full = self.get_bool_parameter("full")
        params = EncodingParameters(width=width, height=height, fps=fps)

        shots = [
            {"preview_file_id": x.get("preview_file_id")}
            for x in playlist["shots"]
        ]

        job = playlists_service.start_build_job(playlist)
        if config.ENABLE_JOB_QUEUE:
            remote = config.ENABLE_JOB_QUEUE_REMOTE
            # remote worker can not access files local to the web app
            if remote and config.FS_BACKEND not in ["s3", "swift"]:
                return {
                    "error": True,
                    "message": "Remote job queue requires s3 or swift backend",
                }, 400

            current_user = persons_service.get_current_user()
            try:
                queue_store.job_queue.enqueue(
                    playlists_service.build_playlist_job,
                    args=(
                        playlist,
                        job,
                        shots,
                        params,
                        current_user["email"],
                        full,
                        remote,
                    ),
                    job_timeout=int(config.JOB_QUEUE_TIMEOUT),
                    unique=True,
                    job_id=f"build_playlist_{playlist['id']}",
                    result_ttl=60,
                    failure_ttl=60,
                )
            except DuplicateJobError:
                playlists_service.remove_build_job(playlist, job["id"])
                return {
                    "error": True,
                    "message": "A build is already in progress for this playlist",
                }, 409
            return job
        else:
            job = playlists_service.build_playlist_movie_file(
                playlist, job, shots, params, full, remote=False
            )
            return job


class PlaylistZipDownloadResource(MethodView):

    @jwt_required()
    @swag_from("openapi/PlaylistZipDownloadResource_get.yml")
    def get(self, playlist_id):
        """
        Download playlist zip
        """
        permissions_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_playlist_access(
            playlist, supervisor_access=True
        )
        project = projects_service.get_project(playlist["project_id"])
        zip_file_path = playlists_service.build_playlist_zip_file(playlist)
        context_name = playlists_service.get_playlist_download_context_name(
            project, playlist
        )
        download_name = (
            f"{context_name}_"
            f"{slugify.slugify(playlist['name'], separator='_')}.zip"
        )

        @after_this_request
        def cleanup(response):
            try:
                os.remove(zip_file_path)
            except OSError:
                pass
            return response

        return flask_send_file(
            zip_file_path,
            conditional=True,
            mimetype="application/zip",
            as_attachment=True,
            download_name=download_name,
        )


class BuildJobResource(MethodView):

    @jwt_required()
    @swag_from("openapi/BuildJobResource_get.yml")
    def get(self, playlist_id, build_job_id):
        """
        Get build job
        """
        permissions_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_playlist_access(playlist)
        build_job = playlists_service.get_build_job(build_job_id)
        if str(build_job["playlist_id"]) != str(playlist_id):
            raise BuildJobNotFoundException
        return build_job

    @jwt_required()
    @swag_from("openapi/BuildJobResource_delete.yml")
    def delete(self, playlist_id, build_job_id):
        """
        Delete build job
        """
        permissions_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_playlist_access(playlist)
        build_job = playlists_service.get_build_job(build_job_id)
        if str(build_job["playlist_id"]) != str(playlist_id):
            raise BuildJobNotFoundException
        playlists_service.remove_build_job(playlist, build_job_id)
        return "", 204


class ProjectBuildJobsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ProjectBuildJobsResource_get.yml")
    def get(self, project_id):
        """
        Get project build jobs
        """
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        return playlists_service.get_build_jobs_for_project(project_id)


class ProjectAllPlaylistsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ProjectAllPlaylistsResource_get.yml")
    def get(self, project_id):
        """
        Get all project playlists
        """
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        page = self.get_page()
        return playlists_service.get_playlists_for_project(project_id, page)


class TempPlaylistResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/TempPlaylistResource_post.yml")
    def post(self, project_id):
        """
        Generate temp playlist
        """
        permissions_service.check_project_access(project_id)
        body = validation.validate_request_body(TempPlaylistCreateSchema)
        task_ids = [str(t) for t in body.task_ids] + [
            task_id
            for task_id in map(
                playlists_service.get_playlist_task_id_for_entity,
                map(str, body.entity_ids),
            )
            if task_id
        ]
        for task_id in task_ids:
            permissions_service.check_task_access(task_id)
        sort = self.get_bool_parameter("sort")
        return (
            playlists_service.generate_temp_playlist(task_ids, sort=sort) or []
        )


class NotifyClientsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/NotifyClientsResource_post.yml")
    def post(self, playlist_id):
        """
        Notify clients playlist ready
        """
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_manager_project_access(
            playlist["project_id"]
        )
        body = validation.validate_request_body(
            NotifyClientsPlaylistSchema,
            data=request.get_json(silent=True) or {},
        )
        studio_id = str(body.studio_id) if body.studio_id else None
        department_id = str(body.department_id) if body.department_id else None
        notifications_service.notify_clients_playlist_ready(
            playlist, studio_id, department_id
        )
        return {"status": "success"}


class PlaylistShareLinksResource(MethodView):
    """
    Manage share links for a playlist (manager+).
    """

    @jwt_required()
    @swag_from("openapi/PlaylistShareLinksResource_get.yml")
    def get(self, playlist_id):
        """
        List the share links of a playlist
        """
        permissions.check_manager_permissions()
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_manager_project_access(
            playlist["project_id"]
        )
        return playlist_sharing_service.get_share_links_for_playlist(
            playlist_id
        )

    @jwt_required()
    @swag_from("openapi/PlaylistShareLinksResource_post.yml")
    def post(self, playlist_id):
        """
        Create a share link for a playlist
        """
        permissions.check_manager_permissions()
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_manager_project_access(
            playlist["project_id"]
        )
        person = persons_service.get_current_user()
        body = validation.validate_request_body(CreatePlaylistShareLinkSchema)
        share_link = playlist_sharing_service.create_share_link(
            playlist_id,
            person["id"],
            expiration_date=body.expiration_date,
            can_comment=body.can_comment,
            password=body.password,
        )
        return share_link, 201


class PlaylistShareLinkResource(MethodView):
    """
    Revoke a specific share link (manager+).
    """

    @jwt_required()
    @swag_from("openapi/PlaylistShareLinkResource_delete.yml")
    def delete(self, playlist_id, token):
        """
        Revoke a share link
        """
        permissions.check_manager_permissions()
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_manager_project_access(
            playlist["project_id"]
        )
        share_link = playlist_sharing_service.get_share_link_by_token_raw(
            token
        )
        # Path playlist_id must match the share link's own playlist_id;
        # otherwise a manager who knows any token could revoke it via any
        # playlist URL they DO have access to.
        if str(share_link.playlist_id) != str(playlist_id):
            raise PlaylistShareLinkNotFoundException
        return playlist_sharing_service.revoke_share_link(token)


class PlaylistShareLinkInviteResource(MethodView):
    """
    Email a share link to one or more recipients (manager+).

    Recipients can be free-form emails and/or existing Person ids
    (e.g. clients on the project) — the server resolves person ids to
    their email server-side. The endpoint is fire-and-forget: no DB
    record of the invitation is kept.
    """

    @jwt_required()
    @swag_from("openapi/PlaylistShareLinkInviteResource_post.yml")
    def post(self, playlist_id, token):
        """
        Invite reviewers to a shared playlist
        """
        permissions.check_manager_permissions()
        playlist = playlists_service.get_playlist(playlist_id)
        permissions_service.check_manager_project_access(
            playlist["project_id"]
        )
        share_link = playlist_sharing_service.get_share_link_by_token_raw(
            token
        )
        if str(share_link.playlist_id) != str(playlist_id):
            raise PlaylistShareLinkNotFoundException

        body = validation.validate_request_body(InviteShareLinkSchema)
        person = persons_service.get_current_user()
        from zou.app.utils.auth import EmailNotValidException

        try:
            sent = playlist_sharing_service.send_share_invitations(
                playlist_id,
                token,
                person["id"],
                emails=body.emails or [],
                person_ids=[str(pid) for pid in (body.person_ids or [])],
                message=body.message,
            )
        except EmailNotValidException as exc:
            return {"error": str(exc)}, 400
        return {"sent": sent}
