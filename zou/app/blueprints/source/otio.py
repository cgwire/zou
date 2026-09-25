from flasgger import swag_from
import os
import pathlib
import re

from string import Template

from flask import request, current_app
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app import config

from zou.app.mixin import ArgsMixin
from zou.app.exceptions import WrongParameterException
from zou.app.utils import fields
from zou.app.services import (
    shots_service,
    projects_service,
    permissions_service,
    user_service,
    persons_service,
)


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


class OTIOBaseResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/OTIOBaseResource_post.yml")
    def post(self, project_id, episode_id=None):
        """
        Import otio base
        """
        args = self.post_args()
        permissions_service.check_manager_project_access(project_id)
        uploaded_file = request.files["file"]
        # run_import selects the OTIO adapter from the extension.
        extension = os.path.splitext(uploaded_file.filename or "")[1]
        extension = re.sub(r"[^A-Za-z0-9.]", "", extension)
        file_path = os.path.join(
            config.TMP_DIR, f"{fields.gen_uuid()}{extension}"
        )
        uploaded_file.save(file_path)
        try:
            result = self.run_import(
                file_path,
                project_id,
                episode_id,
                args["naming_convention"],
                args["match_case"],
            )
        except WrongParameterException:
            # User input error (unsupported or unparseable file): the global
            # handler answers 400, no server-error log.
            raise
        except Exception as e:
            # An unparseable timeline is client input: warn and answer 400
            # rather than reporting it as a server error.
            current_app.logger.warning(
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
            projects_service.get_project_task_types_raw(project_id, "Shot")
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
        import opentimelineio as otio

        suffix = pathlib.Path(file_path).suffix.lstrip(".").lower()
        supported = otio.adapters.suffixes_with_defined_adapters(read=True)
        if suffix not in supported:
            raise WrongParameterException(
                f"Unsupported file type '.{suffix}'. Supported formats: "
                f"{', '.join(sorted(supported))}."
            )
        try:
            kwargs = {}
            if suffix == "edl":
                kwargs["rate"] = projects_service.get_project_fps(project_id)
                kwargs["ignore_timecode_mismatch"] = True
            timeline = otio.adapters.read_from_file(file_path, **kwargs)
        except Exception as e:
            raise WrongParameterException(
                f"Failed to parse OTIO file: {str(e)}"
            )

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
                            name = os.path.splitext(
                                track.media_reference.name
                            )[0]
                        elif getattr(
                            track.media_reference, "target_url", None
                        ):
                            name = os.path.splitext(
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
                                track.range_in_parent().start_time.to_frames()
                            )
                        except Exception:
                            data["frame_in"] = (
                                track.trimmed_range().start_time.to_frames()
                            )
                    except Exception as e:
                        current_app.logger.warning(
                            f"Parsing frame_in failed: {type(e).__name__}: {str(e)}"
                        )
                    try:
                        try:
                            data["frame_out"] = (
                                track.range_in_parent()
                                .end_time_inclusive()
                                .to_frames()
                            )
                        except Exception:
                            data["frame_out"] = (
                                track.trimmed_range()
                                .end_time_inclusive()
                                .to_frames()
                            )
                    except Exception as e:
                        current_app.logger.warning(
                            f"Parsing frame_out failed: {type(e).__name__}: {str(e)}"
                        )

                    future_shot_values["data"] = data

                    try:
                        future_shot_values["nb_frames"] = (
                            track.source_range.duration.to_frames()
                        )
                    except Exception as e:
                        current_app.logger.warning(
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
    @swag_from("openapi/OTIOImportResource_post.yml")
    def post(self, **kwargs):
        """
        Import otio EDL
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
                ("match_case", True, False, fields.boolean),
            ]
        )


class OTIOImportEpisodeResource(OTIOBaseResource):

    @jwt_required()
    @swag_from("openapi/OTIOImportEpisodeResource_post.yml")
    def post(self, **kwargs):
        """
        Import episode otio
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
                ("match_case", True, False, fields.boolean),
            ]
        )
