from ua_parser import user_agent_parser
from werkzeug.user_agent import UserAgent
from werkzeug.utils import cached_property
from flask.json.provider import JSONProvider
from flask import Response, request, abort

import orjson

orjson_options = orjson.OPT_NON_STR_KEYS


class ORJSONProvider(JSONProvider):
    def __init__(self, *args, **kwargs):
        self.options = kwargs
        super().__init__(*args, **kwargs)

    def loads(self, s, **kwargs):
        return orjson.loads(s)

    def dumps(self, obj, **kwargs):
        return orjson.dumps(obj, option=orjson_options).decode("utf-8")


class ParsedUserAgent(UserAgent):
    @cached_property
    def _details(self):
        return user_agent_parser.Parse(self.string)

    @property
    def platform(self):
        return self._details["os"]["family"]

    @property
    def browser(self):
        return self._details["user_agent"]["family"]

    @property
    def version(self):
        return ".".join(
            part
            for key in ("major", "minor", "patch")
            if (part := self._details["user_agent"][key]) is not None
        )


def is_from_browser(user_agent):
    return user_agent.browser in [
        "Brave",
        "Chrome",
        "Chrome Mobile",
        "Chrome Mobile iOS",
        "Edge",
        "Firefox",
        "Mobile Safari",
        "Opera",
        "Safari",
        "Vivaldi",
    ]


def rows_response(header, rows, stream=False):
    """
    Answer a listing described by a header, either as a single JSON object
    carrying every row, or as NDJSON: the header on the first line, then one
    row per line.

    Streaming exists so that a full production never sits in memory at once,
    so rows stays a generator until the last moment: the non streamed branch
    is the only one that spends it.
    """
    if not stream:
        return {**header, "rows": list(rows)}

    def generate():
        yield orjson.dumps(header) + b"\n"
        for row in rows:
            yield orjson.dumps(row) + b"\n"

    return Response(generate(), mimetype="application/x-ndjson")


def wrong_auth_handler(identity_user=None):
    if request.path not in ["/auth/login", "/auth/logout"]:
        abort(401)
    else:
        return identity_user
