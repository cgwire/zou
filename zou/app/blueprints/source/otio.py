import os
import pathlib
import opentimelineio as otio
import re

from string import Template

from flask import request, current_app
from flask_restful import Resource, inputs
from flask_jwt_extended import jwt_required

from zou.app import config

from zou.app.mixin import ArgsMixin
from zou.app.services import (
    shots_service,
    projects_service,
    user_service,
    persons_service,
)

from zou.app.models.task_type import TaskType
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task_type import TaskType


from zou.app.services.tasks_service import (
    create_tasks,
)

mapping_substitutions_to_regex = {
    "${project_name}": r"(?P<project_name>\w*)",
    "$project_name": r"(?P<project_name>\w*)",
    "${episode_name}": r"(?P<episode_name>\w*)",
    "$episode_name": r"(?P<episode_name>\w*)",
    "${sequence_name}": r"(?P<sequence_name>\w*)",
    "$sequence_name": r"(?P<sequence_name>\w*)",
    "${shot_name}": r"(?P<shot_name>\w*)",
    "$shot_name": r"(?P<shot_name>\w*)",
}


class OTIOBaseResource(Resource, ArgsMixin):

    @jwt_required()
    def post(self, project_id, episode_id=None):
        """
        Import otio base
        ---
        description: Base resource for importing OTIO files. This method is
          overridden by subclasses. Import an OTIO file to set frame_in,
          frame_out, and nb_frames for shots.
        tags:
          - Import
        consumes:
          - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            description: Project unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            type: file
            required: true
            description: OTIO file to import (EDL, OTIO, etc.)
        responses:
          201:
            description: Shots imported successfully
          400:
            description: Invalid file format or parsing error
        """
        args = self.post_args()
        user_service.check_manager_project_access(project_id)
        uploaded_file = request.files["file"]
        file_name = uploaded_file.filename
        file_path = os.path.join(config.TMP_DIR, file_name)
        uploaded_file.save(file_path)
        try:
            result = self.run_import(
                file_path,
                project_id,
                episode_id,
                args["naming_convention"],
                args["match_case"],
            )
        except Exception as e:
            current_app.logger.error(
                f"Import OTIO failed: {type(e).__name__}: {str(e)}"
            )
            return {
                "error": True,
                "message": f"{type(e).__name__}: {str(e)}",
            }, 400
        finally:
            os.remove(file_path)
        return result, 201

    def post_args(self):
        return {}

    def prepare_import(
        self, project_id, episode_id, naming_convention, match_case
    ):
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
        self.current_user_id = persons_service.get_current_user()["id"]

        self.naming_convention = naming_convention
        regex_naming_convention = naming_convention
        for k, v in mapping_substitutions_to_regex.items():
            regex_naming_convention = regex_naming_convention.replace(k, v)
        self.regex_pattern = re.compile(regex_naming_convention)
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

        template = Template(self.naming_convention)
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

    def run_import(
        self,
        file_path,
        project_id,
        episode_id,
        naming_convention,
        match_case,
    ):
        result = {"updated_shots": [], "created_shots": []}
        try:
            kwargs = {}
            extension = pathlib.Path(file_path).suffix
            if extension == ".edl":
                kwargs["rate"] = projects_service.get_project_fps(project_id)
                kwargs["ignore_timecode_mismatch"] = True
            timeline = otio.adapters.read_from_file(file_path, **kwargs)
        except Exception as e:
            raise Exception(f"Failed to parse OTIO file: {str(e)}")

        self.prepare_import(
            project_id,
            episode_id,
            naming_convention,
            match_case,
        )
        for video_track in timeline.video_tracks():
            for track in video_track:
                if isinstance(track, otio.schema.Clip):
                    name = os.path.splitext(track.name)[0]
                    if not name:
                        if getattr(track.media_reference, "name_prefix", None):
                            name = track.media_reference.name_prefix
                        elif getattr(track.media_reference, "name", None):
                            name, _ = os.path.splitext(
                                track.media_reference.name
                            )[0]
                        elif getattr(
                            track.media_reference, "target_url", None
                        ):
                            name, _ = os.path.splitext(
                                os.path.basename(
                                    track.media_reference.target_url
                                )
                            )[0]
                    name_to_search = name if self.match_case else name.lower()
                    if name_to_search in self.shot_map:
                        shot_id = self.shot_map[name_to_search]
                        future_shot_values = shots_service.get_shot(shot_id)
                    else:
                        shot_id = None
                        matched_values = re.match(self.regex_pattern, name)
                        if matched_values is None:
                            raise KeyError(
                                "No matched value while extracting shot informations."
                            )
                        shot_infos_extracted = matched_values.groupdict()
                        if "sequence_name" not in shot_infos_extracted.keys():
                            raise KeyError(
                                "No sequence name found while extracting shot informations."
                            )
                        if "shot_name" not in shot_infos_extracted.keys():
                            raise KeyError(
                                "No shot name found while extracting shot informations."
                            )

                        sequence_id = self.sequence_map.get(
                            shot_infos_extracted["sequence_name"]
                        )
                        if sequence_id is None:
                            sequence_id = shots_service.create_sequence(
                                self.project_id,
                                self.episode_id,
                                shot_infos_extracted["sequence_name"],
                                created_by=self.current_user_id,
                            )["id"]
                            self.sequence_map[
                                shot_infos_extracted["sequence_name"]
                            ] = sequence_id

                        future_shot_values = {
                            "project_id": self.project_id,
                            "sequence_id": sequence_id,
                            "name": shot_infos_extracted["shot_name"],
                            "data": None,
                        }

                    data = future_shot_values["data"] or {}
                    try:
                        try:
                            data["frame_in"] = (
                                track.trimmed_range_in_parent().start_time.to_frames()
                            )
                        except:
                            data["frame_in"] = (
                                track.trimmed_range().start_time.to_frames()
                            )
                    except Exception as e:
                        current_app.logger.error(
                            f"Parsing frame_in failed: {type(e).__name__}: {str(e)}"
                        )
                    try:
                        try:
                            data["frame_out"] = (
                                track.trimmed_range_in_parent()
                                .end_time_inclusive()
                                .to_frames()
                            )
                        except:
                            data["frame_out"] = (
                                track.trimmed_range()
                                .end_time_inclusive()
                                .to_frames()
                            )
                    except Exception as e:
                        current_app.logger.error(
                            f"Parsing frame_out failed: {type(e).__name__}: {str(e)}"
                        )

                    future_shot_values["data"] = data

                    try:
                        future_shot_values["nb_frames"] = (
                            track.source_range.duration.to_frames()
                        )
                    except Exception as e:
                        current_app.logger.error(
                            f"Parsing nb_frames failed: {type(e).__name__}: {str(e)}"
                        )

                    if shot_id is None:
                        shot = shots_service.create_shot(
                            **future_shot_values,
                            created_by=self.current_user_id,
                        )
                        result["created_shots"].append(shot)
                    else:
                        shot = shots_service.update_shot(
                            shot_id, future_shot_values
                        )
                        result["updated_shots"].append(shot)

        for task_type in self.task_types_in_project_for_shots:
            create_tasks(task_type.serialize(), result["created_shots"])

        return result


class OTIOImportResource(OTIOBaseResource):

    @jwt_required()
    def post(self, **kwargs):
        """
        Import otio EDL
        ---
        tags:
          - Import
        description: Import an OTIO file to set frame_in, frame_out, and
          nb_frames for shots. Supports any OpenTimelineIO adapter format like
          EDL or OTIO. Uses naming convention to match shots.
        consumes:
          - multipart/form-data
        parameters:
          - in: path
            name: project_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: naming_convention
            required: false
            schema:
              type: string
            default: "${project_name}_${sequence_name}-${shot_name}"
            example: "${project_name}_${sequence_name}-${shot_name}"
            description: Template for matching shot names from the file
          - in: query
            name: match_case
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to match shot names case-sensitively
          - in: formData
            name: file
            type: file
            required: true
            description: OTIO file to import (EDL, OTIO, etc.)
        responses:
            201:
              description: Shots imported successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      updated_shots:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              example: a24a6ea4-ce75-4665-a070-57453082c25
                            name:
                              type: string
                              example: SH010
                            project_id:
                              type: string
                              format: uuid
                              example: b24a6ea4-ce75-4665-a070-57453082c25
                            nb_frames:
                              type: integer
                              example: 120
                            data:
                              type: object
                              properties:
                                frame_in:
                                  type: integer
                                  example: 1001
                                frame_out:
                                  type: integer
                                  example: 1120
                      created_shots:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              example: c24a6ea4-ce75-4665-a070-57453082c25
                            name:
                              type: string
                              example: SH020
                            project_id:
                              type: string
                              format: uuid
                              example: b24a6ea4-ce75-4665-a070-57453082c25
                            nb_frames:
                              type: integer
                              example: 96
                            data:
                              type: object
                              properties:
                                frame_in:
                                  type: integer
                                  example: 2001
                                frame_out:
                                  type: integer
                                  example: 2096
            400:
              description: Invalid file format or parsing error
        """
        return super().post(**kwargs)

    def post_args(self):
        return self.get_args(
            [
                (
                    "naming_convention",
                    "${project_name}_${sequence_name}-${shot_name}",
                    False,
                    str,
                ),
                ("match_case", True, False, inputs.boolean),
            ]
        )


class OTIOImportEpisodeResource(OTIOBaseResource):

    @jwt_required()
    def post(self, **kwargs):
        """
        Import episode otio
        ---
        tags:
          - Import
        description: Import an OTIO file to set frame_in, frame_out, and
          nb_frames for shots in an episode. Supports any OpenTimelineIO
          adapter format like EDL or OTIO. Uses naming convention with episode
          name to match shots.
        consumes:
          - multipart/form-data
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
            example: b24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: naming_convention
            required: false
            schema:
              type: string
            default: "${project_name}_${episode_name}-${sequence_name}-${shot_name}"
            example: "${project_name}_${episode_name}-${sequence_name}-${shot_name}"
            description: Template for matching shot names from the file
          - in: query
            name: match_case
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to match shot names case-sensitively
          - in: formData
            name: file
            type: file
            required: true
            description: OTIO file to import (EDL, OTIO, etc.)
        responses:
            201:
              description: Shots imported successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      updated_shots:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              example: a24a6ea4-ce75-4665-a070-57453082c25
                            name:
                              type: string
                              example: SH010
                            project_id:
                              type: string
                              format: uuid
                              example: c24a6ea4-ce75-4665-a070-57453082c25
                            nb_frames:
                              type: integer
                              example: 120
                            data:
                              type: object
                              properties:
                                frame_in:
                                  type: integer
                                  example: 1001
                                frame_out:
                                  type: integer
                                  example: 1120
                      created_shots:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: string
                              format: uuid
                              example: d24a6ea4-ce75-4665-a070-57453082c25
                            name:
                              type: string
                              example: SH020
                            project_id:
                              type: string
                              format: uuid
                              example: c24a6ea4-ce75-4665-a070-57453082c25
                            nb_frames:
                              type: integer
                              example: 96
                            data:
                              type: object
                              properties:
                                frame_in:
                                  type: integer
                                  example: 2001
                                frame_out:
                                  type: integer
                                  example: 2096
            400:
              description: Invalid file format or parsing error
        """
        return super().post(**kwargs)

    def post_args(self):
        return self.get_args(
            [
                (
                    "naming_convention",
                    "${project_name}_${episode_name}-${sequence_name}-${shot_name}",
                    False,
                    str,
                ),
                ("match_case", True, False, inputs.boolean),
            ]
        )
