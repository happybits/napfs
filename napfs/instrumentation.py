import functools
import os
import sys
import falcon

try:
    import newrelic
except ImportError:
    newrelic = None
    pass

if newrelic is not None:
    # 3rd-party
    from newrelic.agent import (
        callable_name,
        FunctionTrace,
        current_transaction,
        set_transaction_name,
        record_exception,
        initialize,
        WSGIApplicationWrapper,
    )

    def trace(f, group=None):
        txn_name = callable_name(f, ".")

        @functools.wraps(f)
        def inner(*args, **kwargs):
            if group == "Python/speedaemon":
                set_transaction_name(txn_name)
            with FunctionTrace(
                transaction=current_transaction(),
                name=txn_name,
                group=group

            ):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if not isinstance(e, falcon.HTTPNotFound):
                        record_exception(*sys.exc_info())
                    raise

        return inner

    # noinspection PyBroadException
    try:
        newrelic_config = os.getenv('NEW_RELIC_CONFIG_FILE',
                                    '/etc/newrelic-speedaemon.ini')
        if newrelic_config and os.path.getsize(newrelic_config) > 0:
            initialize(newrelic_config, os.getenv('NAPFS_ENV', 'development'))
    except Exception:
        pass

    def wrap_app(app):
        return WSGIApplicationWrapper(app)

else:

    # noinspection PyUnusedLocal
    def trace(f, group=None):
        return f

    def wrap_app(app):
        return app
