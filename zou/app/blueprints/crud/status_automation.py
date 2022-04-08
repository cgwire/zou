from zou.app.models.status_automation import StatusAutomation

from .base import BaseModelsResource, BaseModelResource

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

    def post_update(self, status_automation):
        status_automations_service.clear_status_automation_cache()
        return status_automation

    def post_delete(self, status_automation):
        status_automations_service.clear_status_automation_cache()
        return status_automation
