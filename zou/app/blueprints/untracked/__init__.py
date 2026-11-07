from flask import Blueprint

from zou.app.blueprints.untracked.resources import (
    ProjectUntrackedResource,
    UntrackedResource,
)
from zou.app.utils.api import configure_api_from_blueprint

routes = [
    ("/data/projects/<project_id>/untracked", ProjectUntrackedResource),
    ("/data/untracked/<untracked_id>", UntrackedResource),
]

blueprint = Blueprint("untracked", "untracked")
api = configure_api_from_blueprint(blueprint, routes)
