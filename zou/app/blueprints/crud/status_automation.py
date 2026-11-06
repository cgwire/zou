from flask import current_app
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.blueprints.crud.base import (
    BaseModelResource,
    BaseModelsResource,
    build_db_error_message,
)
from zou.app.models.status_automation import StatusAutomation
from zou.app.services import (
    permissions_service,
    status_automations_service,
)
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/status_automation.yml")


class StatusAutomationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, StatusAutomation)

    def check_read_permissions(self, options=None):
        permissions_service.block_access_to_vendor()
        return True

    @jwt_required()
    @swag_from(SPECS["StatusAutomationsResource_get"])
    def get(self):
        """
        Get status automations
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["StatusAutomationsResource_post"])
    def post(self):
        """
        Create status automation
        """
        return super().post()

    def update_data(self, data):
        # First: it refuses a body the base method cannot read.
        data = status_automations_service.normalize_trigger(data)
        return super().update_data(data)

    def post_creation(self, status_automation):
        status_automations_service.clear_status_automation_cache()
        return status_automation.serialize(relations=True)


class StatusAutomationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, StatusAutomation)

    @jwt_required()
    @swag_from(SPECS["StatusAutomationResource_get"])
    def get(self, instance_id):
        """
        Get status automation
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["StatusAutomationResource_put"])
    def put(self, instance_id):
        """
        Update status automation
        """
        return super().put(instance_id)

    def update_data(self, data, instance_id):
        # First: it refuses a body the base method cannot read.
        data = status_automations_service.normalize_trigger(
            data, self.instance.serialize()
        )
        return super().update_data(data, instance_id)

    def post_update(self, status_automation, data):
        status_automations_service.clear_status_automation_cache()
        return status_automation

    @jwt_required()
    @swag_from(SPECS["StatusAutomationResource_delete"])
    def delete(self, instance_id):
        """
        Delete status automation
        """
        instance = self.get_model_or_404(instance_id)
        instance_dict = instance.serialize()
        self.check_delete_permissions(instance_dict)
        status_automations_service.guard_status_automation_deletion(
            instance_dict["id"]
        )

        try:
            self.pre_delete(instance_dict)
            instance.delete()
            self.emit_delete_event(instance_dict)
            self.post_delete(instance_dict)

        except (IntegrityError, StatementError) as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": build_db_error_message(exception)}, 400

        return "", 204

    def post_delete(self, status_automation):
        status_automations_service.clear_status_automation_cache()
        return status_automation
