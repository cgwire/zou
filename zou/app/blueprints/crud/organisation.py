from zou.app.models.organisation import Organisation
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services import persons_service
from zou.app.utils.permissions import has_admin_permissions


class OrganisationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Organisation)

    def check_read_permissions(self, options=None):
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

    def serialize_instance(self, data, relations=True):
        return data.serialize(
            relations=relations,
            ignored_attrs=(
                []
                if has_admin_permissions()
                else [
                    "chat_token_slack",
                    "chat_webhook_mattermost",
                    "chat_token_discord",
                ]
            ),
        )

    def post_update(self, instance_dict, data):
        persons_service.clear_organisation_cache()
        return instance_dict
