from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.subscription import Subscription

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class SubscriptionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Subscription)

    @jwt_required()
    @swag_from("openapi/SubscriptionsResource_get.yml")
    def get(self):
        """
        Get subscriptions
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/SubscriptionsResource_post.yml")
    def post(self):
        """
        Create subscription
        """
        return super().post()


class SubscriptionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Subscription)

    @jwt_required()
    @swag_from("openapi/SubscriptionResource_get.yml")
    def get(self, instance_id):
        """
        Get subscription
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/SubscriptionResource_put.yml")
    def put(self, instance_id):
        """
        Update subscription
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/SubscriptionResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete subscription
        """
        return super().delete(instance_id)
