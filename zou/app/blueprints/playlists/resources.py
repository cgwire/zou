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
        Get project playlists
        ---
        description: Retrieve all playlists related to given project. Result is
          paginated and can be sorted.
        tags:
          - Playlists
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: page
            required: false
            schema:
              type: integer
            description: Page number for pagination
            example: 1
          - in: query
            name: sort_by
            required: false
            schema:
              type: string
            description: Field to sort by
            example: updated_at
          - in: query
            name: task_type_id
            required: false
            schema:
              type: string
              format: uuid
            description: Task type unique identifier to filter by
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
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
                        description: Playlist unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Playlist name
                        example: "Review Playlist"
                      project_id:
                        type: string
                        format: uuid
                        description: Project unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get episode playlists
        ---
        description: Retrieve all playlists related to given episode. The full
          list is returned because the number of playlists in an episode is not
          that big.
        tags:
          - Playlists
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: episode_id
            required: true
            schema:
              type: string
              format: uuid
            description: Episode unique identifier or special value (main, all)
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
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
                        description: Playlist unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Playlist name
                        example: "Review Playlist"
                      episode_id:
                        type: string
                        format: uuid
                        description: Episode unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
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
        Get playlist
        ---
        description: Retrieve a specific playlist by ID with preview file
          revisions.
        tags:
          - Playlists
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            description: Playlist unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Playlist details with preview file revisions
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Playlist unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    name:
                      type: string
                      description: Playlist name
                      example: "Review Playlist"
                    project_id:
                      type: string
                      format: uuid
                      description: Project unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    shots:
                      type: array
                      description: List of shots with preview file revisions
                      items:
                        type: object
                        example: [{"id": "uuid", "preview_file_id": "uuid"}]
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
        Get entity previews
        ---
        description: Retrieve all previews related to a given entity. It sends
          them as a dict. Keys are related task type ids and values are arrays
          of preview for this task type.
        tags:
          - Playlists
        parameters:
          - in: path
            name: entity_id
            required: true
            schema:
              type: string
              format: uuid
            description: Entity unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: All previews related to given entity grouped by task type
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
                          description: Preview file unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          description: Preview file name
                          example: "preview_v001.png"
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        return playlists_service.get_preview_files_for_entity(entity_id)


class PlaylistDownloadResource(Resource):

    @jwt_required()
    def get(self, playlist_id, build_job_id):
        """
        Download playlist build
        ---
        description: Download given playlist build as MP4 file.
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            description: Playlist unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: build_job_id
            required: true
            schema:
              type: string
              format: uuid
            description: Build job unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Playlist build downloaded as MP4 file
            content:
              video/mp4:
                schema:
                  type: string
                  format: binary
          400:
            description: Build not finished, need to retry later
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: boolean
                      description: Error flag
                      example: true
                    message:
                      type: string
                      description: Error message
                      example: "Build is not finished"
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
        Build playlist movie
        ---
        description: Build given playlist as MP4 movie. Starts a build job that
          processes the playlist shots into a video file.
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            description: Playlist unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: full
            required: false
            schema:
              type: boolean
            description: Whether to build full quality movie
            example: true
        responses:
          200:
            description: Build job created for playlist movie
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Build job unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    status:
                      type: string
                      description: Build job status
                      example: "pending"
                    created_at:
                      type: string
                      format: date-time
                      description: Build job creation timestamp
                      example: "2022-07-12T10:30:00Z"
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
        Download playlist zip
        ---
        description: Download given playlist as ZIP file containing all preview
          files.
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            description: Playlist unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Playlist downloaded as ZIP file
            content:
              application/zip:
                schema:
                  type: string
                  format: binary
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
        Get build job
        ---
        description: Retrieve build job related to given playlist.
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            description: Playlist unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: build_job_id
            required: true
            schema:
              type: string
              format: uuid
            description: Build job unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Build job related to given playlist
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Build job unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    status:
                      type: string
                      description: Build job status
                      example: "succeeded"
                    created_at:
                      type: string
                      format: date-time
                      description: Build job creation timestamp
                      example: "2022-07-12T10:30:00Z"
        """
        user_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_playlist_access(playlist)
        return playlists_service.get_build_job(build_job_id)

    @jwt_required()
    def delete(self, playlist_id, build_job_id):
        """
        Delete build job
        ---
        description: Remove given build job related to given playlist.
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            description: Playlist unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: build_job_id
            required: true
            schema:
              type: string
              format: uuid
            description: Build job unique identifier
            example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          204:
            description: Build job removed successfully
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
        Get project build jobs
        ---
        description: Retrieve all build jobs related to given project. It's
          mainly used for synchronisation purpose.
        tags:
          - Playlists
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
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
                        description: Build job unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      status:
                        type: string
                        description: Build job status
                        example: "succeeded"
                      created_at:
                        type: string
                        format: date-time
                        description: Build job creation timestamp
                        example: "2022-07-12T10:30:00Z"
        """
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        return playlists_service.get_build_jobs_for_project(project_id)


class ProjectAllPlaylistsResource(Resource, ArgsMixin):

    @jwt_required()
    def get(self, project_id):
        """
        Get all project playlists
        ---
        description: Retrieve all playlists related to given project. It's
          mainly used for synchronisation purpose.
        tags:
          - Playlists
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
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
                        description: Playlist unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Playlist name
                        example: "Review Playlist"
                      project_id:
                        type: string
                        format: uuid
                        description: Project unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
        """
        permissions.check_admin_permissions()
        projects_service.get_project(project_id)
        page = self.get_page()
        return playlists_service.get_playlists_for_project(project_id, page)


class TempPlaylistResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, project_id):
        """
        Generate temp playlist
        ---
        description: Generate a temporary playlist from task IDs. It's mainly
          used for synchronisation purpose.
        tags:
          - Playlists
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: sort
            required: false
            schema:
              type: boolean
            description: Whether to sort the playlist
            example: true
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
                    description: List of task unique identifiers
                    example: ["a24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
          200:
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
                        description: Preview file unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Preview file name
                        example: "preview_v001.png"
          400:
            description: Invalid task IDs
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
        Notify clients playlist ready
        ---
        description: Notify clients that given playlist is ready for review.
        tags:
          - Playlists
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            description: Playlist unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: false
          content:
            application/json:
              schema:
                type: object
                properties:
                  studio_id:
                    type: string
                    format: uuid
                    description: Studio unique identifier to notify
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          200:
            description: Clients notified successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    status:
                      type: string
                      description: Notification status
                      example: "success"
        """
        studio_id = request.json.get("studio_id", None)
        playlist = playlists_service.get_playlist(playlist_id)
        project_id = playlist["project_id"]
        user_service.check_manager_project_access(project_id)
        notifications_service.notify_clients_playlist_ready(
            playlist, studio_id
        )
        return {"status": "success"}
