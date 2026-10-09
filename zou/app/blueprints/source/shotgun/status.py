from flasgger import swag_from
from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.models.task_status import TaskStatus
from zou.app.utils import colors
from zou.app.services import (
    task_types_service,
)
from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunStatusResource(BaseImportShotgunResource):
    @jwt_required()
    @swag_from("openapi/ImportShotgunStatusResource_post.yml")
    def post(self):
        """
        Import shotgun task statuses
        """
        return super().post()

    def import_entry(self, data):
        task_status = self.get_existing_status(data)
        if task_status is None:
            task_status = TaskStatus(**data)
            task_status.save()
            current_app.logger.info(f"TaskStatus created: {task_status}")
        else:
            task_status.update(data)
            task_types_service.clear_task_status_cache(str(task_status.id))
            current_app.logger.info(f"TaskStatus updated: {task_status}")
        return task_status

    def extract_data(self, sg_status):
        color = sg_status.get("bg_color", "0,0,0")
        if color is None:
            color = "0,0,0"

        return {
            "name": sg_status["name"],
            "short_name": sg_status["code"],
            "shotgun_id": sg_status["id"],
            "color": colors.rgb_to_hex(color),
        }

    def get_existing_status(self, data):
        task_status = TaskStatus.get_by(shotgun_id=data["shotgun_id"])
        if task_status is None:
            task_status = TaskStatus.get_by(short_name=data["short_name"])
        return task_status


class ImportRemoveShotgunStatusResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, TaskStatus)

    @jwt_required()
    @swag_from("openapi/ImportRemoveShotgunStatusResource_post.yml")
    def post(self):
        """
        Remove shotgun task status
        """
        return super().post()
