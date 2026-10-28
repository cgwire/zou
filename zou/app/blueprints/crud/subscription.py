from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.subscription import Subscription
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/subscription.yml")


class SubscriptionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Subscription)

    @jwt_required()
    @swag_from(SPECS["SubscriptionsResource_get"])
    def get(self):
        """
        Get subscriptions
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["SubscriptionsResource_post"])
    def post(self):
        """
        Create subscription
        """
        return super().post()


class SubscriptionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Subscription)

    @jwt_required()
    @swag_from(SPECS["SubscriptionResource_get"])
    def get(self, instance_id):
        """
        Get subscription
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["SubscriptionResource_put"])
    def put(self, instance_id):
        """
        Update subscription
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["SubscriptionResource_delete"])
    def delete(self, instance_id):
        """
        Delete subscription
        """
        return super().delete(instance_id)
