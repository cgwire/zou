from flasgger import swag_from
from flask import abort, current_app, request
from flask.views import MethodView
from sqlalchemy.exc import OperationalError, ProgrammingError

from zou.app import config
from zou.app.services import persons_service
from zou.app.stores import config_store


class ConfigCheckResource(MethodView):

    @swag_from("openapi/ConfigCheckResource_get.yml")
    def get(self):
        """
        Compare the environment and the stored configuration
        """
        token = request.headers.get("Authorization", "")
        if not token.startswith("Bearer ") or token[7:] != config.ADMIN_TOKEN:
            abort(403)

        comparison = config_store.get_config_comparison()
        try:
            comparison["active_users"] = persons_service.count_active_users()
        except (ProgrammingError, OperationalError) as exc:
            current_app.logger.warning(
                f"Config check could not count active users: {exc}"
            )
            comparison["active_users"] = None
        return comparison
