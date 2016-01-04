# std lib
import io
import mimetypes
import re
import time

# 3rd-party
import falcon

# internal
from .fs import copy_file, delete_file, open_file, \
    write_file_chunk, read_file_chunk, checksum_response

# we only export the app var
__all__ = ['app']

# regex for matching byte range header
_BYTE_RANGE_HEADER_PATTERN = re.compile(r'^bytes\=([0-9]+)\-([0-9]+)?$')


def _parse_byte_range_header(range_header):
    """
    when the client/browser sends a byte range request header, parse it into
    min/max ints. If the client sends a header in the form of:

      Range: bytes=100-

    with no second param, use an empty string to indicate the wild-card max
    value.

    If we can't parse the header, assume they want the whole file.
    Maybe we should throw an error if it is not the right form?
    And only assume all content if the client sends no range header at all?

    :param range_header: str
    :return: int, int
    """
    try:
        m = re.match(_BYTE_RANGE_HEADER_PATTERN, range_header)
        first_byte = int(m.group(1))
        last_byte = '' if m.group(2) is None else int(m.group(2))
    except(AttributeError, TypeError):
        first_byte = 0
        last_byte = ''
    return first_byte, last_byte


class Router(object):
    """
    This is a falcon sink:
        http://falcon.readthedocs.org/en/stable/api/api.html#falcon.API.add_sink

    We use it to route all the requests based on the request method.
    """

    allowed_methods = ['GET', 'PUT', 'PATCH', 'POST', 'DELETE']

    def __call__(self, req, resp):
        """
        the router for all requests.
        Everything comes through here.
        Based on the method, we route requests to the appropriate handler.

        :param req: falcon.Request
        :param resp: falcon.Response
        :return: None
        """
        method = req.method

        if method == 'GET':
            return self.on_get(req, resp)
        elif method == 'PATCH':
            return self.on_patch(req, resp)
        elif method == 'DELETE':
            return self.on_delete(req, resp)
        elif method == 'PUT':
            return self.on_post(req, resp)
        elif method == 'POST':
            return self.on_post(req, resp)
        else:
            raise falcon.HTTPMethodNotAllowed(
                allowed_methods=self.allowed_methods
            )

    def on_get(self, req, resp):
        """
        Fetch a file or byte range request.

        :param req: falcon.Request
        :param resp: falcon.Response
        :return: None
        """
        path = req.path
        if not path:
            raise falcon.HTTPNotFound()

        first_byte, last_byte = _parse_byte_range_header(
            req.get_header('range'))

        try:
            f = open_file(path, 'rb')
        except IOError:
            raise falcon.HTTPNotFound()

        try:
            f.seek(0, io.SEEK_END)
            max_last_byte = f.tell() - 1
        except OSError:
            raise falcon.HTTPNotFound()

        if last_byte == '' or last_byte > max_last_byte:
            last_byte = max_last_byte

        length = last_byte - first_byte + 1

        response = read_file_chunk(f, first_byte, length)

        # if this was a byte range request by the client, be sure to set the
        # proper response headers to match the byte range request.
        if req.get_header('range'):
            resp.append_header('Accept-Ranges', 'bytes')
            resp.append_header(
                'Content-Range', 'bytes %s-%s/%s' %
                (first_byte, last_byte, max_last_byte + 1))
            resp.status = falcon.HTTP_206
        else:
            resp.status = falcon.HTTP_200

        checksum = req.get_header('x-checksum')

        # if the client wants a checksum of the content instead of the actual
        # content, do a little trickery to read the data from the generator
        # above and substitute the checksum value for the content instead.
        if checksum:
            hexdigest = checksum_response(response, checksum)
            resp.append_header('Content-Length', "%s" % len(hexdigest))
            resp.append_header('Content-Type', 'text/plain')

            def response():
                yield hexdigest.encode('utf-8')
        else:
            resp.append_header('Content-Length', "%s" % length)
            resp.append_header(
                'Content-Type',
                mimetypes.guess_type(path)[0] or 'application/octet-stream')
        resp.stream = response()

    def on_post(self, req, resp):
        """
        create a file. Overwrites if it exists.
        Can copy a file from another source.

        :param req: falcon.Request
        :param resp: falcon.Response
        :return: None
        """
        src = req.get_header('x-source')
        path = req.path
        if src:
            start = time.time()
            if src[0] != '/':
                raise falcon.HTTPInvalidParam(
                    'invalid source %s' % src, param_name='x-source')

            copy_file(src, path)
            resp.body = 'OK'
            resp.append_header('x-start', "%.6f" % start)
            resp.append_header('x-end', "%.6f" % time.time())
        else:
            self.on_delete(req, resp)
            self.on_patch(req, resp)

    def on_patch(self, req, resp):

        """
        patch a file.

        :param req: falcon.Request
        :param resp: falcon.Response
        :return: None
        """

        start = time.time()
        path = req.path
        try:
            offset = int(req.get_param('offset'))
        except TypeError:
            offset = 0

        write_file_chunk(path,
                         stream=req.stream,
                         offset=offset,
                         chunk_size=int(req.get_header('Content-Length')))

        resp.body = 'OK'
        resp.append_header('x-start', "%.6f" % start)
        resp.append_header('x-end', "%.6f" % time.time())

    def on_delete(self, req, resp):
        """
        delete a file

        :param req: falcon.Request
        :param resp: falcon.Response
        :return: None
        """

        path = req.path
        res = delete_file(path)

        if not res:
            raise falcon.HTTPInternalServerError(
                'path still exists: %s' % path,
                description='the file is still present after attempting '
                            'to delete it')

        resp.body = 'OK'


# create the app.
app = falcon.API()

# attach the resource.
app.add_sink(Router(), '/')
