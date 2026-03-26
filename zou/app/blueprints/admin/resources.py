from flask import abort, request
from flask_restful import Resource

from zou.app import config
from zou.app.models.person import Person
from zou.app.stores import config_store


class ConfigCheckResource(Resource):

    def get(self):
        token = request.headers.get("Authorization", "")
        if not token.startswith("Bearer ") or token[7:] != config.ADMIN_TOKEN:
            abort(403)

        comparison = config_store.get_config_comparison()
        comparison["active_users"] = Person.query.filter(
            Person.active, Person.is_bot.isnot(True)
        ).count()
        return comparison
