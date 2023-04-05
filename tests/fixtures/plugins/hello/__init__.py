from .resources import HelloResource

routes = [
    ("/hello", HelloResource),
]

name = __name__
