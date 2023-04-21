import os
import uuid
import opentimelineio as otio
import re

from string import Template

from flask import request, current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app import config

from zou.app.mixin import ArgsMixin
from zou.app.services import shots_service, projects_service, user_service
from zou.app.blueprints.previews.resources import ALLOWED_MOVIE_EXTENSION

from zou.app.models.task_type import TaskType
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task_type import TaskType


from zou.app.services.tasks_service import (
    create_tasks,
)

mapping_substitutions_to_regex = {
    "${project_name}": "(?P<project_name>\w*)",
    "$project_name": "(?P<project_name>\w*)",
    "${episode_name}": "(?P<episode_name>\w*)",
    "$episode_name": "(?P<episode_name>\w*)",
    "${sequence_name}": "(?P<sequence_name>\w*)",
    "$sequence_name": "(?P<sequence_name>\w*)",
    "${shot_name}": "(?P<shot_name>\w*)",
    "$shot_name": "(?P<shot_name>\w*)",
}


class EDLBaseResource(Resource, ArgsMixin):
    def post(self, project_id, episode_id=None):
        args = self.post_args()
        user_service.check_manager_project_access(project_id)
        uploaded_file = request.files["file"]
        file_name = "%s.edl" % uuid.uuid4()
        file_path = os.path.join(config.TMP_DIR, file_name)
        uploaded_file.save(file_path)
        self.prepare_import(
            project_id, episode_id, args["nomenclature"], args["match_case"]
        )
        try:
            result = self.run_import(project_id, file_path)
        except Exception as e:
            current_app.logger.error("Import EDL failed: %s" % (str(e)))
            return {"error": True, "message": str(e)}, 400
        return result, 201

    def post_args(self):
        return {}

    def prepare_import(self, project_id, episode_id, nomenclature, match_case):
        self.sequence_map = {}
        self.shot_map = {}
        self.project_id = project_id
        self.project = projects_service.get_project(project_id)
        self.is_tv_show = projects_service.is_tv_show(self.project)
        self.episode_id = episode_id
        self.task_types_in_project_for_shots = (
            TaskType.query.join(ProjectTaskTypeLink)
            .filter(ProjectTaskTypeLink.project_id == project_id)
            .filter(TaskType.for_entity == "Shot")
        )

        self.nomenclature = nomenclature
        regex_nomenclature = nomenclature
        for k, v in mapping_substitutions_to_regex.items():
            regex_nomenclature = regex_nomenclature.replace(k, v)
        self.regex_pattern = re.compile(regex_nomenclature)
        self.match_case = match_case

        if self.is_tv_show:
            self.episode_id = episode_id
            self.episode = shots_service.get_episode(episode_id)
            sequences = shots_service.get_sequences_for_episode(episode_id)
            shots = shots_service.get_shots_for_episode(episode_id)
        else:
            sequences = shots_service.get_sequences({"project_id": project_id})
            shots = shots_service.get_shots({"project_id": project_id})
        for sequence in sequences:
            self.sequence_map[sequence["id"]] = sequence["name"]

        template = Template(self.nomenclature)
        for shot in shots:
            sequence_key = self.sequence_map[shot["parent_id"]]
            substitutions = {
                "project_name": self.project["name"],
                "sequence_name": sequence_key,
                "shot_name": shot["name"],
            }
            if self.is_tv_show:
                substitutions["episode_name"] = self.episode["name"]
            key = template.substitute(substitutions)
            if not self.match_case:
                key = key.lower()
            self.shot_map[key] = shot["id"]

    def run_import(self, project_id, file_path):
        result = {"updated_shots": [], "created_shots": []}
        try:
            timeline = otio.adapters.read_from_file(
                file_path,
                rate=projects_service.get_project_fps(project_id),
                ignore_timecode_mismatch=True,
            )
        except otio.exceptions.OTIOError:
            raise Exception("Failed to parse EDL file.")
        for video_track in timeline.video_tracks():
            for track in video_track:
                if isinstance(track, otio.schema.Clip):
                    name, extension = os.path.splitext(track.name)
                    if extension not in ALLOWED_MOVIE_EXTENSION:
                        continue
                    name_to_search = name if self.match_case else name.lower()
                    if name_to_search in self.shot_map:
                        shot_id = self.shot_map[name_to_search]
                        future_shot_values = shots_service.get_shot(shot_id)
                    else:
                        shot_id = None
                        matched_values = re.match(self.regex_pattern, name)
                        if matched_values is None:
                            raise Exception(
                                "No matched value while extracting shot informations."
                            )
                        shot_infos_extracted = matched_values.groupdict()

                        sequence_id = self.sequence_map.get(
                            shot_infos_extracted["sequence_name"]
                        )
                        if sequence_id is None:
                            sequence_id = shots_service.create_sequence(
                                self.project_id,
                                self.episode_id,
                                shot_infos_extracted["sequence_name"],
                            )["id"]

                        future_shot_values = {
                            "project_id": self.project_id,
                            "sequence_id": sequence_id,
                            "name": shot_infos_extracted["shot_name"],
                            "data": None,
                        }

                    data = future_shot_values["data"] or {}
                    start_time_frame = (
                        track.trimmed_range_in_parent().start_time.to_frames()
                    )
                    data["frame_in"] = start_time_frame + 1
                    data["frame_out"] = (
                        start_time_frame
                        + track.trimmed_range_in_parent().duration.to_frames()
                    )

                    future_shot_values["data"] = data

                    future_shot_values[
                        "nb_frames"
                    ] = track.source_range.duration.to_frames()

                    if shot_id is None:
                        shot = shots_service.create_shot(**future_shot_values)
                        result["created_shots"].append(shot)
                    else:
                        shot = shots_service.update_shot(
                            shot_id, future_shot_values
                        )
                        result["updated_shots"].append(shot)

                if isinstance(track, otio.schema.Transition):
                    pass

        for task_type in self.task_types_in_project_for_shots:
            create_tasks(task_type.serialize(), result["created_shots"])

        return result


class EDLImportResource(EDLBaseResource):
    @jwt_required()
    def post(self, **kwargs):
        """
        Import an EDL file to enter frame_in / frame_out / nb_frames.
        ---
        tags:
          - Import
        consumes:
          - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            type: file
            required: true
        responses:
            201:
                description: .
            400:
                description: The .EDL file is not properly formatted.
        """
        super().post(**kwargs)

    def post_args(self):
        return self.get_args(
            [
                (
                    "nomenclature",
                    "${project_name}_${sequence_name}-${shot_name}",
                    False,
                    str,
                ),
                ("match_case", True, False, bool),
            ]
        )


class EDLImportEpisodeResource(EDLBaseResource):
    def post(self, **kwargs):
        """
        Import an EDL file to enter frame_in / frame_out / nb_frames.
        ---
        tags:
          - Import
        consumes:
          - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: episode_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            type: file
            required: true
        responses:
            201:
                description: .
            400:
                description: The .EDL file is not properly formatted.
        """
        return super().post(**kwargs)

    def post_args(self):
        return self.get_args(
            [
                (
                    "nomenclature",
                    "${project_name}_${episode_name}-${sequence_name}-${shot_name}",
                    False,
                    str,
                ),
                ("match_case", True, False, bool),
            ]
        )
