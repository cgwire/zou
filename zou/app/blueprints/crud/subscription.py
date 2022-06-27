from zou.app.models.subscription import Subscription

from .base import BaseModelResource, BaseModelsResource
from zou.app import name_space_subscriptions


@name_space_subscriptions.route('/')
class SubscriptionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Subscription)


@name_space_subscriptions.route('/<instance_id>')
class SubscriptionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Subscription)
