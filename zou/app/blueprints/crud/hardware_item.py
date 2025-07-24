from flask import abort, current_app

from sqlalchemy.exc import StatementError
from flask_jwt_extended import jwt_required

from zou.app.models.hardware_item import HardwareItem
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.services import files_service


class HardwareItemsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, HardwareItem)


class HardwareItemResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, HardwareItem)