from .helpers import parse_byte_ranges_from_list, \
    get_last_contiguous_byte


class MetaData(object):
    __slots__ = ['disabled', 'headers', 'parts']

    HEADER_EXPIRE_TIMEOUT = 3600
    PARTS_EXPIRE_TIMEOUT = 86400 * 3

    def __init__(self, path, headers=None, parts=None, reset=False, db=None):
        self.disabled = True if db is None else False
        self.headers = {}
        self.parts = []
        if self.disabled:
            return

        callbacks = []
        pipe = db.pipeline(transaction=False)
        headers_key = 'H{%s}' % path
        parts_key = 'P{%s}' % path
        if reset:
            pipe.delete(headers_key)
            callbacks.append(None)
            pipe.delete(parts_key)
            callbacks.append(None)

        if headers:
            pipe.hmset(headers_key, headers)
            callbacks.append(None)
            pipe.expire(headers_key, self.HEADER_EXPIRE_TIMEOUT)
            callbacks.append(None)

        pipe.hgetall(headers_key)
        callbacks.append(self._handle_header_results)

        if parts is not None:
            for element in parts:
                pipe.sadd(parts_key, element)
                callbacks.append(None)
            pipe.expire(parts_key, self.PARTS_EXPIRE_TIMEOUT)
            callbacks.append(None)

        pipe.smembers(parts_key)
        callbacks.append(self._handle_parts_results)

        for i, result in enumerate(pipe.execute()):
            callback = callbacks[i]
            if callback is None:
                continue

            callback(result)

        if parts is None:
            return

        byte_ranges = parse_byte_ranges_from_list(self.parts)

        if len(byte_ranges) < 4:
            return

        to_remove = []
        max_len = get_last_contiguous_byte(byte_ranges)
        for offset, last in byte_ranges:
            if last > max_len:
                break
            to_remove.append((offset, last))

        pipe = db.pipeline(transaction=False)
        for offset, last in to_remove:
            pipe.srem(parts_key, "%s-%s" % (offset, last))
            pipe.sadd(parts_key, '0-%s' % max_len)
        pipe.expire(parts_key, self.PARTS_EXPIRE_TIMEOUT)
        pipe.smembers(parts_key)
        res = pipe.execute().pop()
        self._handle_parts_results(res)

    def _handle_header_results(self, results):
        if results is None:
            return
        for k, v in results.items():
            self.headers[k.decode('ascii')] = v.decode('ascii')

    def _handle_parts_results(self, results):
        if results is None:
            return
        for row in results:
            self.parts.append(row.decode('ascii'))
