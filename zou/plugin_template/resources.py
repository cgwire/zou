from flask.views import MethodView
from flask_jwt_extended import jwt_required

from .models import Count


class HelloWorld(MethodView):

    @jwt_required()
    def get(self):
        if not Count.query.first():
            c = Count.create()
        else:
            c = Count.query.first()
            c.count += 1
            Count.commit()
        return {"message": "Hello, World!", "count": c.count}
