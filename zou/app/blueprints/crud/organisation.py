from zou.app.models.organisation import Organisation
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services import persons_service


class OrganisationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Organisation)

    def check_read_permissions(self):
        return True


class OrganisationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Organisation)

    def check_read_permissions(self, instance):
        return True

    def pre_update(self, instance_dict, data):
        if "hours_by_day" in data:
            data["hours_by_day"] = float(data["hours_by_day"])
        return data

    def post_update(self, instance_dict, data):
        persons_service.clear_oranisation_cache()
        return instance_dict
