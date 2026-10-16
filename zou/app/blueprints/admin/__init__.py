from flask import Blueprint

from zou.app.blueprints.admin.resources import (
    ConfigCheckResource,
)
from zou.app.utils.api import configure_api_from_blueprint

routes = [
    ("/admin/config/check", ConfigCheckResource),
]

blueprint = Blueprint("admin", "admin")
api = configure_api_from_blueprint(blueprint, routes)
