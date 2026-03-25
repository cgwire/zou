from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.admin.resources import (
    ConfigCheckResource,
)

routes = [
    ("/admin/config/check", ConfigCheckResource),
]

blueprint = Blueprint("admin", "admin")
api = configure_api_from_blueprint(blueprint, routes)
