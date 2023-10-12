from flask import current_app
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.status_automation import StatusAutomation
from zou.app.models.project import ProjectStatusAutomationLink
from zou.app.services import status_automations_service, user_service


class StatusAutomationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, StatusAutomation)

    def check_read_permissions(self):
        user_service.block_access_to_vendor()
        return True

    def post_creation(self, status_automation):
        status_automations_service.clear_status_automation_cache()
        return status_automation.serialize()


class StatusAutomationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, StatusAutomation)

    def post_update(self, status_automation, data):
        status_automations_service.clear_status_automation_cache()
        return status_automation

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete status automation corresponding at given ID and return it as a JSON
        object.
        """
        instance = self.get_model_or_404(instance_id)
        instance_dict = instance.serialize()
        links = ProjectStatusAutomationLink.query.filter_by(
            status_automation_id=instance_dict["id"]
        ).all()
        if len(links) > 0:
            return {"message": "This automation is used in a project."}, 400

        try:
            self.check_delete_permissions(instance_dict)
            self.pre_delete(instance_dict)
            instance.delete()
            self.emit_delete_event(instance_dict)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        return "", 204

    def post_delete(self, status_automation):
        status_automations_service.clear_status_automation_cache()
        return status_automation
