from functools import wraps

from flask import g, request

from zou.app.services import playlist_sharing_service


def require_valid_playlist_share_link():
    """
    Validate the token of the path. If the link has a password, validate
    the ``password`` query parameter too. Then store the share link dict on
    ``g.playlist_share_link`` for the request.
    """

    def decorator(view_fn):
        @wraps(view_fn)
        def wrapped(self, token, *args, **kwargs):
            playlist_sharing_service.check_share_link_password(
                token, request.args.get("password")
            )
            g.playlist_share_link = (
                playlist_sharing_service.validate_share_token(token)
            )
            return view_fn(self, token, *args, **kwargs)

        return wrapped

    return decorator
