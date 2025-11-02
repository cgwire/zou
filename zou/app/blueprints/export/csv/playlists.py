from flask_restful import Resource
from flask_jwt_extended import jwt_required
from slugify import slugify

from zou.app.utils import date_helpers

from zou.app.services import (
    entities_service,
    files_service,
    names_service,
    playlists_service,
    persons_service,
    projects_service,
    shots_service,
    user_service,
    tasks_service,
)
from zou.app.utils import csv_utils


class PlaylistCsvExport(Resource):
    @jwt_required()
    def get(self, playlist_id):
        """
        Export playlist csv
        ---
        tags:
          - Export
        description: Export playlist as CSV file. Includes playlist shots
          with preview information, task statuses, comments, and revision
          details.
        produces:
          - text/csv
        parameters:
          - in: path
            name: playlist_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Playlist exported as CSV successfully
              content:
                text/csv:
                  schema:
                    type: string
                  example: "Entity name,Nb Frames,Task Type,Retake count,Revision,Task Status,Last comment author,Last comment date,Last comment\nSH010,120,Animation,2,10,WIP,John Doe,2024-01-15,Good work"
        """
        user_service.block_access_to_vendor()
        playlist = playlists_service.get_playlist(playlist_id)
        user_service.check_playlist_access(playlist, supervisor_access=True)
        project = projects_service.get_project(playlist["project_id"])
        self.task_type_map = tasks_service.get_task_type_map()
        self.task_status_map = tasks_service.get_task_status_map()
        task_ids = []
        for shot in playlist["shots"]:
            preview_file = files_service.get_preview_file(
                shot["preview_file_id"]
            )
            task_ids.append(preview_file["task_id"])
        self.task_comment_map = tasks_service.get_last_comment_map(task_ids)
        episode = self.get_episode(playlist)

        csv_content = []
        headers = self.build_headers(playlist, project, episode)
        csv_content += headers
        for shot in playlist["shots"]:
            csv_content.append(self.build_row(shot))

        file_name = "%s playlist %s" % (project["name"], playlist["name"])
        return csv_utils.build_csv_response(csv_content, slugify(file_name))

    def build_headers(self, playlist, project, episode=None):
        entity_type = "for assets"
        if playlist["for_entity"] == "shot":
            entity_type = "for shots"
        context_name = project["name"]
        if episode:
            context_name += " - %s" % episode["name"]
        context_name += " | %s" % entity_type
        timezone = persons_service.get_current_user()["timezone"]
        created_at = date_helpers.get_date_string_with_timezone(
            playlist["created_at"], timezone
        )
        headers = [
            [
                "Playlist",
                context_name,
                playlist["name"],
                created_at,
                "",
                "",
                "",
            ],
            ["", "", "", "", "", "", ""],
            [
                "Entity name",
                "Nb Frames",
                "Task Type",
                "Retake count",
                "Revision",
                "Task Status",
                "Last comment author",
                "Last comment date",
                "Last comment",
            ],
        ]
        return headers

    def build_row(self, shot):
        entity = entities_service.get_entity(shot["entity_id"])
        name, _, _ = names_service.get_full_entity_name(shot["entity_id"])
        preview_file = files_service.get_preview_file(shot["preview_file_id"])
        task = tasks_service.get_task(preview_file["task_id"])
        task_type = self.task_type_map[task["task_type_id"]]
        task_status = self.task_status_map[task["task_status_id"]]
        comment = self.task_comment_map.get(task["id"], {})
        author = self.get_author(comment)
        date = self.get_date(comment)
        return [
            name,
            entity.get("nb_frames", ""),
            task_type["name"],
            task["retake_count"],
            preview_file["revision"],
            task_status["name"],
            author,
            date,
            comment.get("text", ""),
        ]

    def get_episode(self, playlist):
        episode = None
        if playlist["episode_id"] is not None:
            episode = shots_service.get_episode(playlist["episode_id"])
        return episode

    def get_author(self, comment):
        author = ""
        person_id = comment.get("person_id", None)
        if person_id is not None:
            person = persons_service.get_person(person_id)
            author = person["full_name"]
        return author

    def get_date(self, comment):
        comment_date = comment.get("date", None)
        if comment_date is not None:
            timezone = persons_service.get_current_user()["timezone"]
            return date_helpers.get_date_string_with_timezone(
                comment_date, timezone
            )
        else:
            return ""
