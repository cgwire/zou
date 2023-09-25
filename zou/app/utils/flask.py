from ua_parser import user_agent_parser
from werkzeug.user_agent import UserAgent
from werkzeug.utils import cached_property
from flask.json.provider import JSONProvider
from flask import make_response
import orjson

orjson_options = orjson.OPT_NON_STR_KEYS


def output_json(data, code, headers=None):
    """Makes a Flask response with a JSON encoded body"""
    dumped = orjson.dumps(data, option=orjson_options)

    resp = make_response(dumped, code)
    resp.headers.extend(headers or {})
    return resp


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
