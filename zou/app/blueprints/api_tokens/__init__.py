from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.api_tokens.resources import (
    RegenerateApiTokenResource,
)

routes = [
    (
        "/actions/persons/<api_token_id>/change-password",
        RegenerateApiTokenResource,
    ),
]

blueprint = Blueprint("persons", "persons")
api = configure_api_from_blueprint(blueprint, routes)
