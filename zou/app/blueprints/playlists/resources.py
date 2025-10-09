import slugify

from flask import request, send_file as flask_send_file
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app import config
from zou.app.mixin import ArgsMixin

from zou.app.services import (
    entities_service,
    notifications_service,
    playlists_service,
    persons_service,
    preview_files_service,
    projects_service,
    shots_service,
    user_service,
)
from zou.app.stores import file_store, queue_store
from zou.app.utils import fs, permissions
from zou.utils.movie import EncodingParameters


class ProjectPlaylistsResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all playlists related to given project.
        Result is paginated and can be sorted.
        ---
        tags:
          - Playlists
        description: Result is paginated and can be sorted.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: page
            required: false
            schema:
              type: integer
            example: 1
          - in: query
            name: sort_by
            required: false
            schema:
              type: string
            example: updated_at
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: All playlists related to given project
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                      name:
                        type: string
                      project_id:
                        type: string
                        format: uuid
        """
        user_service.block_access_to_vendor()
        user_service.check_project_access(project_id)
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


class EpisodePlaylistsResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id, episode_id):
        """
        Retrieve all playlists related to given episode.
        The full list is returned because the number of playlists in an episode is not that big.
        ---
        tags:
          - Playlists
        description: The full list is returned because the number of playlists in an episode is not that big.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: episode_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: All playlists related to given episode
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                      name:
                        type: string
                      episode_id:
                        type: string
                        format: uuid
        """
        user_service.block_access_to_vendor()
        user_service.check_project_access(project_id)
        page = self.get_page()
        sort_by = self.get_sort_by()
        task_type_id = self.get_text_parameter("task_type_id")
        if episode_id not in ["main", "all"]:
            shots_service.get_episode(episode_id)
        return playlists_service.all_playlists_for_episode(
            project_id,
            episode_id,
            for_client=permissions.has_client_permissions(),
            page=page,
            sort_by=sort_by,
            task_type_id=task_type_id,
        )


class ProjectPlaylistResource(Resource):

    @jwt_required()
    def get(self, project_id, playlist_id):
        """
        Retrieve a specific playlist by ID.
        ---
        tags:
          - Playlists
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: Playlist details with preview file revisions
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                    name:
                      type: string
                    project_id:
                      type: string
                      format: uuid
                    shots:
                      type: array
                      items:
                        type: object
          '404':
            description: Playlist not found
        """
        user_service.block_access_to_vendor()
        user_service.check_project_access(project_id)
        return playlists_service.get_playlist_with_preview_file_revisions(
            playlist_id
        )


class EntityPreviewsResource(Resource):

    @jwt_required()
    def get(self, entity_id):
        """
        Retrieve all previews related to a given entity.
        ---
        tags:
          - Playlists
        description: It sends them as a dict. Keys are related task type ids and values are arrays of preview for this task type.
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: All previews related to given entity
            content:
              application/json:
                schema:
                  type: object
                  additionalProperties:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                        name:
                          type: string
          '404':
            description: Entity not found
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return playlists_service.get_preview_files_for_entity(entity_id)


class PlaylistDownloadResource(Resource):

    @jwt_required()
    def get(self, playlist_id, build_job_id):
        """
        Download given playlist build as .mp4.
        ---
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: build_job_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: Given playlist build downloaded as .mp4
            content:
              video/mp4:
                schema:
                  type: string
                  format: binary
          '400':
            description: Build not finished, need to retry later
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: boolean
                    message:
                      type: string
          '404':
            description: Playlist or build job not found
        """
        user_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_playlist_access(playlist, supervisor_access=True)
        project = projects_service.get_project(playlist["project_id"])
        build_job = playlists_service.get_build_job(build_job_id)

        if build_job["status"] != "succeeded":
            return {"error": True, "message": "Build is not finished"}, 400
        else:
            movie_file_path = fs.get_file_path_and_file(
                config,
                file_store.get_local_movie_path,
                file_store.open_movie,
                "playlists",
                build_job_id,
                "mp4",
            )
            context_name = slugify.slugify(project["name"], separator="_")
            if project["production_type"] == "tvshow":
                episode_id = playlist["episode_id"]
                if episode_id is not None:
                    episode = shots_service.get_episode(playlist["episode_id"])
                    episode_name = episode["name"]
                elif playlist["is_for_all"]:
                    episode_name = "all assets"
                else:
                    episode_name = "main pack"
                context_name += "_%s" % slugify.slugify(
                    episode_name, separator="_"
                )
            download_name = "%s_%s_%s.mp4" % (
                slugify.slugify(build_job["created_at"], separator="").replace(
                    "t", "_"
                ),
                context_name,
                slugify.slugify(playlist["name"], separator="_"),
            )
            return flask_send_file(
                movie_file_path,
                conditional=True,
                mimetype="video/mp4",
                as_attachment=True,
                download_name=download_name,
            )


class BuildPlaylistMovieResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, playlist_id):
        """
        Build given playlist as mp4 movie.
        ---
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: full
            required: false
            schema:
              type: boolean
            example: true
        responses:
          '200':
            description: Given playlist built as mp4 movie
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                    status:
                      type: string
                    created_at:
                      type: string
                      format: date-time
          '404':
            description: Playlist not found
        """
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_manager_project_access(playlist["project_id"])

        project = projects_service.get_project(playlist["project_id"])
        (width, height) = preview_files_service.get_preview_file_dimensions(
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
            assert not remote or config.FS_BACKEND in ["s3", "swift"]

            current_user = persons_service.get_current_user()
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
            )
            return job
        else:
            job = playlists_service.build_playlist_movie_file(
                playlist, job, shots, params, full, remote=False
            )
            return job


class PlaylistZipDownloadResource(Resource):

    @jwt_required()
    def get(self, playlist_id):
        """
        Download given playlist as zip.
        ---
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: Given playlist downloaded as zip
            content:
              application/zip:
                schema:
                  type: string
                  format: binary
          '404':
            description: Playlist not found
        """
        user_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_playlist_access(playlist, supervisor_access=True)
        project = projects_service.get_project(playlist["project_id"])
        zip_file_path = playlists_service.build_playlist_zip_file(playlist)

        context_name = slugify.slugify(project["name"], separator="_")
        if project["production_type"] == "tvshow":
            episode_id = playlist["episode_id"]
            if episode_id is not None:
                episode = shots_service.get_episode(playlist["episode_id"])
                episode_name = episode["name"]
            elif playlist["is_for_all"]:
                episode_name = "all assets"
            else:
                episode_name = "main pack"
            context_name += "_%s" % slugify.slugify(
                episode_name, separator="_"
            )
        download_name = "%s_%s.zip" % (
            context_name,
            slugify.slugify(playlist["name"], separator="_"),
        )

        return flask_send_file(
            zip_file_path,
            conditional=True,
            mimetype="application/zip",
            as_attachment=True,
            download_name=download_name,
        )


class BuildJobResource(Resource):

    @jwt_required()
    def get(self, playlist_id, build_job_id):
        """
        Retrieve build job related to given playlist.
        ---
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: build_job_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: Build job related to given playlist
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                    status:
                      type: string
                    created_at:
                      type: string
                      format: date-time
          '404':
            description: Playlist or build job not found
        """
        user_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_playlist_access(playlist)
        return playlists_service.get_build_job(build_job_id)

    @jwt_required()
    def delete(self, playlist_id, build_job_id):
        """
        Remove given build job related to given playlist.
        ---
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: build_job_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '204':
            description: Given build job removed
          '404':
            description: Playlist or build job not found
        """
        user_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_playlist_access(playlist)
        playlists_service.remove_build_job(playlist, build_job_id)
        return "", 204


class ProjectBuildJobsResource(Resource):

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all build jobs related to given project.
        It's mainly used for synchronisation purpose.
        ---
        tags:
          - Playlists
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: All build jobs related to given project
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                      status:
                        type: string
                      created_at:
                        type: string
                        format: date-time
          '404':
            description: Project not found
        """
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        return playlists_service.get_build_jobs_for_project(project_id)


class ProjectAllPlaylistsResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Retrieve all playlists related to given project.
        ---
        tags:
          - Playlists
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: All playlists related to given project
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                      name:
                        type: string
                      project_id:
                        type: string
                        format: uuid
          '404':
            description: Project not found
        """
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        page = self.get_page()
        return playlists_service.get_playlists_for_project(project_id, page)


class TempPlaylistResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, project_id):
        """
        Generate a temporary playlist from task IDs.
        ---
        tags:
          - Playlists
        description: It's mainly used for synchronisation purpose.
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_ids
                properties:
                  task_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
                    example: ["a24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
          '200':
            description: Temporary playlist generated
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                      name:
                        type: string
          '400':
            description: Invalid task IDs
          '404':
            description: Project not found
        """
        user_service.check_project_access(project_id)
        task_ids = request.json.get("task_ids", [])
        sort = self.get_bool_parameter("sort")
        return (
            playlists_service.generate_temp_playlist(task_ids, sort=sort) or []
        )


class NotifyClientsResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, playlist_id):
        """
        Notify clients that given playlist is ready.

        ---
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  studio_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          '200':
            description: Clients notified
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    status:
                      type: string
                      example: success
        """
        studio_id = request.json.get("studio_id", None)
        playlist = playlists_service.get_playlist(playlist_id)
        project_id = playlist["project_id"]
        user_service.check_manager_project_access(project_id)
        notifications_service.notify_clients_playlist_ready(
            playlist, studio_id
        )
        return {"status": "success"}
