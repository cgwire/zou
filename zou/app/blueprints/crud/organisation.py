from flasgger import swag_from
from flask_jwt_extended import jwt_required

from sqlalchemy.inspection import inspect

from zou.app.models.organisation import Organisation, SENSITIVE_FIELDS
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services import (
    organisation_service,
)
from zou.app.exceptions import WrongParameterException
from zou.app.utils.permissions import has_admin_permissions


class OrganisationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Organisation)

    def check_read_permissions(self, options=None):
        return True

    def get_filterable_column_names(self):
        """
        The chat tokens are stripped from the payload for non admins, so
        they must not be answerable through a filter either.
        """
        names = inspect(self.model).all_orm_descriptors.keys()
        if has_admin_permissions():
            return names
        return [name for name in names if name not in SENSITIVE_FIELDS]

    def serialize_list(self, entries, relations=False):
        if has_admin_permissions():
            return [entry.present(relations=relations) for entry in entries]
        return [
            entry.present_minimal(relations=relations) for entry in entries
        ]

    @jwt_required()
    @swag_from("openapi/OrganisationsResource_get.yml")
    def get(self):
        """
        Get organisations
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/OrganisationsResource_post.yml")
    def post(self):
        """
        Create organisation
        """
        return super().post()


class OrganisationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Organisation)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from("openapi/OrganisationResource_get.yml")
    def get(self, instance_id):
        """
        Get organisation
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/OrganisationResource_put.yml")
    def put(self, instance_id):
        """
        Update organisation
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/OrganisationResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete organisation
        """
        return super().delete(instance_id)

    def pre_update(self, instance_dict, data):
        if "hours_by_day" in data:
            try:
                data["hours_by_day"] = float(data["hours_by_day"])
            except (TypeError, ValueError):
                raise WrongParameterException("hours_by_day must be a number.")
        return data

    def serialize_instance(self, data, relations=True):
        if has_admin_permissions():
            return data.present(relations=relations)
        return data.present_minimal(relations=relations)

    def post_update(self, instance_dict, data):
        organisation_service.clear_organisation_cache()
        return instance_dict
