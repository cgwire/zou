from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.time_spent import TimeSpent
from zou.app.services import permissions_service, time_spents_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/time_spent.yml")


class TimeSpentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TimeSpent)

    @jwt_required()
    @swag_from(SPECS["TimeSpentsResource_get"])
    def get(self):
        """
        Get time spents
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["TimeSpentsResource_post"])
    def post(self):
        """
        Create time spent
        """
        return super().post()

    def apply_filters(self, query, options):
        query = super(TimeSpentsResource, self).apply_filters(query, options)
        start_date = options.get("start_date", None)
        end_date = options.get("end_date", None)
        if not start_date and not end_date:
            return query

        if None in [start_date, end_date]:
            raise WrongParameterException(
                "If querying for a range of dates, both a `start_date` and an "
                "`end_date` must be given."
            )

        return time_spents_service.filter_time_spents_between(
            query, start_date, end_date
        )

    def post_creation(self, instance):
        time_spents_service.update_task_duration(str(instance.task_id))
        return instance.serialize(relations=True)


class TimeSpentResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TimeSpent)

    def check_delete_permissions(self, instance_dict):
        return permissions_service.check_time_spent_access(
            instance_dict["task_id"], instance_dict["person_id"]
        )

    @jwt_required()
    @swag_from(SPECS["TimeSpentResource_get"])
    def get(self, instance_id):
        """
        Get time spent
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["TimeSpentResource_put"])
    def put(self, instance_id):
        """
        Update time spent
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["TimeSpentResource_delete"])
    def delete(self, instance_id):
        """
        Delete time spent
        """
        return super().delete(instance_id)

    def post_update(self, instance_dict, data):
        time_spents_service.update_task_duration(instance_dict["task_id"])
        return instance_dict

    def post_delete(self, instance_dict):
        time_spents_service.update_task_duration(instance_dict["task_id"])
        return instance_dict
