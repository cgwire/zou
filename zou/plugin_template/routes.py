from flask_restful import Resource
from .models import Count


class HelloWorld(Resource):
    def get(self):
        if not Count.query.first():
            c = Count.create()
        else:
            c = Count.query.first()
            c.count += 1
            Count.commit()
        return {"message": "Hello, World!", "count": c.count}
