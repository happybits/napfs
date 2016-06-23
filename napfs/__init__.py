import falcon
from .instrumentation import trace, wrap_app
from .rest import Router
from .version import __version__

__all__ = ['Router', 'create_app']

group = "Python/napfs"
Router.on_get = trace(Router.on_get, group=group)
Router.on_post = trace(Router.on_post, group=group)
Router.on_patch = trace(Router.on_patch, group=group)
Router.on_delete = trace(Router.on_delete, group=group)


def create_app(router=None):
    app = falcon.API()
    if router is None:
        router = Router()
    app.add_sink(router, '/')
    return wrap_app(app)
