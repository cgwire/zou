from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.day_off import DayOff
from zou.app.services import (
    permissions_service,
    time_spents_service,
)
from zou.app.utils import permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/day_off.yml")


class DayOffsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, DayOff)

    def check_create_permissions(self, data):
        return permissions_service.check_day_off_access(data)

    @jwt_required()
    @swag_from(SPECS["DayOffsResource_get"])
    def get(self):
        """
        Get day offs
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["DayOffsResource_post"])
    def post(self):
        """
        Create day off
        """
        return super().post()

    def check_creation_integrity(self, data):
        if time_spents_service.get_day_offs_between(
            data["date"], data["end_date"], data["person_id"]
        ):
            raise WrongParameterException(
                "Day off already exists for this period"
            )
        return data

    def post_creation(self, instance):
        time_spents_service.remove_time_spents_covered_by_day_off(instance)
        return instance.serialize(relations=True)


class DayOffResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, DayOff)
        self.with_description = True

    @jwt_required()
    @swag_from(SPECS["DayOffResource_get"])
    def get(self, instance_id):
        """
        Get day off
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["DayOffResource_put"])
    def put(self, instance_id):
        """
        Update day off
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["DayOffResource_delete"])
    def delete(self, instance_id):
        """
        Delete day off
        """
        return super().delete(instance_id)

    def check_delete_permissions(self, instance_dict):
        return permissions_service.check_day_off_access(instance_dict)

    def check_read_permissions(self, instance_dict):
        # Reading follows the person routes: admins, the person and the
        # managers of a production they are part of get the whole record,
        # the supervisors of such a production the dates only. Writing
        # stays between the person and the admins.
        self.with_description = permissions_service.check_day_off_read_access(
            instance_dict["person_id"]
        )
        return True

    def clean_get_result(self, data):
        if not self.with_description:
            data.pop("description", None)
        return data

    def check_update_permissions(self, instance_dict, data):
        if (
            "person_id" in data.keys()
            and instance_dict["person_id"] != data["person_id"]
            and not permissions.has_admin_permissions()
        ):
            raise permissions.PermissionDenied()
        return permissions_service.check_day_off_access(instance_dict)

    def post_update(self, instance_dict, data):
        time_spents_service.remove_time_spents_covered_by_day_off(
            self.instance
        )
        return instance_dict

    def pre_update(self, instance_dict, data):
        if time_spents_service.get_day_offs_between(
            data.get("date", instance_dict["date"]),
            data.get("end_date", instance_dict["end_date"]),
            data.get("person_id", instance_dict["person_id"]),
            exclude_id=instance_dict["id"],
        ):
            raise WrongParameterException(
                "Day off already exists for this period"
            )
        return data
