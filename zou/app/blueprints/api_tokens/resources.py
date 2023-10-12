import datetime

from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions
from zou.app.services import api_tokens_service


class RegenerateApiTokenResource(Resource, ArgsMixin):
    """
    Allow an admin to regenerate access token for API Token.
    """

    @jwt_required()
    @permissions.admin_permission.require(403)
    @permissions.person_permission.require(403)
    def post(self, api_token_id):
        """
        Allow an admin to regenerate access token for API Token.
        ---
        description: An admin can regenerate access token for API Token.
                     It will invalidate the previous access token.
                     It's possible to regenerate the access token for an expired
                     access token.
        tags:
            - API Tokens
        parameters:
          - in: path
            name: api_token_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: days_duration
            required: False
            type: integer
            default: None
        responses:
          200:
            description: New access token
          400:
            description: Wrong parameters
        """
        args = self.get_args(("days_duration", None, False, int))
        api_token = api_tokens_service.get_api_token_raw(api_token_id)
        api_token.days_duration = args["days_duration"]
        return api_tokens_service.create_access_token_from_instance(api_token)
