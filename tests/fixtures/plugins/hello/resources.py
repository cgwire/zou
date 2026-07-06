from flask.views import MethodView


class HelloResource(MethodView):
    def get(self):
        return {"Hello": "world"}
