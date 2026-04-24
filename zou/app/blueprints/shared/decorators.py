from functools import wraps

from flask import g, request

from zou.app.services import playlist_sharing_service


def require_valid_playlist_share_link(with_password=False):
    """
    Validate the path token and store the serialized share link on
    ``g.playlist_share_link`` for the request.

    :param with_password: When True, pass the optional ``password`` query
        parameter to ``playlist_sharing_service.validate_share_token`` (for
        protected links).
    """

    def decorator(view_fn):
        @wraps(view_fn)
        def wrapped(self, token, *args, **kwargs):
            if with_password:
                password = request.args.get("password")
                g.playlist_share_link = (
                    playlist_sharing_service.validate_share_token(
                        token, password=password
                    )
                )
            else:
                g.playlist_share_link = (
                    playlist_sharing_service.validate_share_token(token)
                )
            return view_fn(self, token, *args, **kwargs)

        return wrapped

    return decorator
