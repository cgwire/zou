from flask.views import MethodView
from flask_jwt_extended import jwt_required
from slugify import slugify

from zou.app.exceptions import WrongParameterException
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    breakdown_service,
    permissions_service,
    projects_service,
)
from zou.app.utils import csv_utils
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class CastingCsvExport(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from(SPECS["CastingCsvExport_get"])
    def get(self, project_id):
        """
        Export casting csv
        """
        project = projects_service.get_project(project_id)  # Check existence
        self.check_permissions(project_id)

        episode_id = self.get_episode_id()

        is_shot_casting = self.get_bool_parameter("is_shot_casting")

        is_tv_show = projects_service.is_tv_show(project)
        if episode_id == "main" and not is_tv_show:
            raise WrongParameterException(
                "The main pack exists only in a TV show."
            )

        results = self.build_results(
            project_id,
            is_tv_show=is_tv_show,
            episode_id=episode_id,
            is_shot_casting=is_shot_casting,
        )
        headers = self.build_headers(
            is_tv_show=is_tv_show, episode_id=episode_id
        )

        csv_content = [headers]
        for result in results:
            csv_content.append(
                self.build_row(
                    result, is_tv_show=is_tv_show, episode_id=episode_id
                )
            )

        file_name = f"{project['name']} casting"
        return csv_utils.build_csv_response(csv_content, slugify(file_name))

    def check_permissions(self, project_id):
        permissions_service.check_project_access(project_id)
        permissions_service.block_access_to_vendor()

    def build_headers(self, is_tv_show=False, episode_id=None):
        headers = [
            "Parent",
            "Name",
            "Asset Type",
            "Asset",
            "Occurences",
            "Label",
        ]
        if is_tv_show and episode_id not in ["all"]:
            return ["Episode"] + headers
        else:
            return headers

    def build_row(self, result, is_tv_show=False, episode_id=None):
        if is_tv_show and episode_id not in ["all"]:
            (
                episode_name,
                target_parent_name,
                target_entity_type_name,
                target_name,
                asset_type_name,
                asset_name,
                entity_link_nb_occurences,
                entity_link_label,
            ) = result
            row = [
                episode_name or "",
                target_parent_name or target_entity_type_name,
                target_name,
                asset_type_name,
                asset_name,
                entity_link_nb_occurences,
                entity_link_label or "",
            ]
        else:
            (
                target_parent_name,
                target_entity_type_name,
                target_name,
                asset_type_name,
                asset_name,
                entity_link_nb_occurences,
                entity_link_label,
            ) = result
            row = [
                target_parent_name or target_entity_type_name,
                target_name,
                asset_type_name,
                asset_name,
                entity_link_nb_occurences,
                entity_link_label or "",
            ]
        return row

    def build_results(
        self,
        project_id,
        is_tv_show=False,
        episode_id=None,
        is_shot_casting=False,
    ):
        results = []
        if episode_id == "main":
            results = breakdown_service.get_main_pack_casting_export_rows(
                project_id
            )
        elif episode_id == "all":
            results = breakdown_service.get_episodes_casting_export_rows(
                project_id
            )
        elif is_shot_casting:
            results = breakdown_service.get_shot_casting_export_rows(
                project_id, is_tv_show, episode_id
            )
        else:
            results = breakdown_service.get_asset_casting_export_rows(
                project_id, is_tv_show, episode_id
            )
        return results
