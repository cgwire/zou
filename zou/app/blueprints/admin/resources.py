from flask import abort, current_app, request
from flask_restful import Resource
from sqlalchemy.exc import OperationalError, ProgrammingError

from zou.app import config
from zou.app.models.person import Person
from zou.app.stores import config_store


class ConfigCheckResource(Resource):

    def get(self):
        token = request.headers.get("Authorization", "")
        if not token.startswith("Bearer ") or token[7:] != config.ADMIN_TOKEN:
            abort(403)

        comparison = config_store.get_config_comparison()
        try:
            comparison["active_users"] = Person.query.filter(
                Person.active,
                Person.is_bot.isnot(True),
                Person.is_guest.isnot(True),
            ).count()
        except (ProgrammingError, OperationalError) as exc:
            current_app.logger.warning(
                f"Config check could not count active users: {exc}"
            )
            comparison["active_users"] = None
        return comparison
