import io
import mimetypes
import time
import falcon

from .fs import open_file, read_file_chunk, checksum_response, copy_file, \
    delete_file, write_file_chunk
from .data import MetaData

from .helpers import parse_byte_range_header, \
    get_last_contiguous_byte, parse_byte_ranges_from_list, \
    condense_byte_ranges, InvalidChecksumException


class Router(object):
    allowed_methods = ['GET', 'PUT', 'PATCH', 'POST', 'DELETE']

    __slots__ = ['data_dir', 'path_tpl', '_db', 'passthru']

    def __init__(self, data_dir, redis_connection=None,
                 passthrough_headers=None):
        self.data_dir = data_dir
        self.path_tpl = data_dir + "%s"
        self._db = redis_connection
        self.passthru = passthrough_headers or []
        self.passthru = [x.lower() for x in self.passthru]

    def get_local_path(self, uri):
        return self.path_tpl % uri

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
        elif method == 'HEAD':
            return self.on_head(req, resp)
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

    def _get_byte_range(self, data, req, resp):
        first_byte, last_byte = parse_byte_range_header(
            req.get_header('range'))

        if data.disabled:
            return first_byte, last_byte

        byte_ranges = parse_byte_ranges_from_list(data.parts)

        last_contig_byte = get_last_contiguous_byte(byte_ranges)
        if last_byte == '' or last_byte > last_contig_byte:
            last_byte = last_contig_byte

        if not byte_ranges:
            raise falcon.HTTPNotFound()

        min_first_byte = min([row[0] for row in byte_ranges])

        if min_first_byte > 0:
            raise falcon.HTTPNotFound()

        return first_byte, last_byte

    def on_get(self, req, resp):
        return self._get(req, resp, True)

    def on_head(self, req, resp):
        return self._get(req, resp, False)

    def _get(self, req, resp, body):
        """
        Fetch a file or byte range request.

        :param req: falcon.Request
        :param resp: falcon.Response
        :return: None
        """
        path = req.path

        if not path:
            raise falcon.HTTPNotFound()

        data = self._data(path=req.path)

        first_byte, last_byte = self._get_byte_range(data, req, resp)

        self._add_metadata_to_resp(resp, data)

        try:
            f = open_file(self.get_local_path(path), 'rb')
        except IOError:
            raise falcon.HTTPNotFound()

        try:
            f.seek(0, io.SEEK_END)
            last_file_byte = f.tell() - 1
        except OSError:
            raise falcon.HTTPNotFound()

        if last_byte == '' or last_byte > last_file_byte:
            last_byte = last_file_byte

        length = last_byte - first_byte + 1

        response = read_file_chunk(f, first_byte, length)

        # if this was a byte range request by the client, be sure to set the
        # proper response headers to match the byte range request.
        if req.get_header('range'):
            resp.append_header('Accept-Ranges', 'bytes')
            resp.append_header(
                'Content-Range', 'bytes %s-%s/%s' %
                                 (first_byte, last_byte, last_file_byte + 1))
            resp.status = falcon.HTTP_206
        else:
            resp.status = falcon.HTTP_200

        checksum = req.get_header('x-checksum')

        # if the client wants a checksum of the content instead of the actual
        # content, do a little trickery to read the data from the generator
        # above and substitute the checksum value for the content instead.
        # if the client is requesting the head, add it to the header as the
        # body will be truncated.
        if checksum:
            hexdigest = checksum_response(response, checksum)
            resp.append_header('Content-Length', "%s" % len(hexdigest))
            resp.append_header('Content-Type', 'text/plain')
            if not body:
                resp.append_header('X-Signature', '%s=%s' %
                                   (checksum, hexdigest.encode('utf-8')))

            def response():
                yield hexdigest.encode('utf-8')
        else:
            if length > 0:
                resp.append_header('Content-Length', "%d" % length)
            resp.append_header(
                'Content-Type',
                mimetypes.guess_type(path)[0] or 'application/octet-stream')
        if body:
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
        headers = self._extract_headers(req)

        path = req.path
        if src:
            start = time.time()
            if src[0] != '/':
                self._error_to_response(resp, falcon.HTTPInvalidParam(
                    'invalid source %s' % src, param_name='x-source'))

            copy_file(self.get_local_path(src), self.get_local_path(path))
            src_data = self._data(path=src)
            headers.update(src_data.headers)
            data = self._data(path=path, reset=True, parts=src_data.parts,
                              headers=headers)

            resp.text = 'OK'
            resp.append_header('x-start', "%.6f" % start)
            resp.append_header('x-end', "%.6f" % time.time())

        else:
            start = time.time()
            content_length = int(req.get_header('Content-Length'))
            path = req.path
            delete_file(self.get_local_path(path))
            write_file_chunk(self.get_local_path(path),
                             stream=req.stream,
                             offset=0,
                             chunk_size=content_length,
                             checksum=req.get_header('x-checksum'),
                             checksum_type=req.get_header('x-checksum-type'))

            resp.text = 'OK'
            resp.append_header('x-start', "%.6f" % start)
            resp.append_header('x-end', "%.6f" % time.time())
            data = self._data(path=path,
                              parts=['%d-%d' % (0, content_length - 1)],
                              headers=headers, reset=True)

        self._add_metadata_to_resp(resp, data)

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

        content_length = int(req.get_header('Content-Length'))

        try:
            write_file_chunk(self.get_local_path(path),
                             stream=req.stream,
                             offset=offset,
                             chunk_size=content_length,
                             checksum=req.get_header('x-checksum'),
                             checksum_type=req.get_header('x-checksum-type'))
        except InvalidChecksumException:
            self._error_to_response(resp,
                                    falcon.HTTPPreconditionFailed(
                                        'CHECKSUM_FAIL',
                                        'Checksum mismatch.'))

        resp.text = 'OK'
        resp.append_header('x-start', "%.6f" % start)
        resp.append_header('x-end', "%.6f" % time.time())

        path = req.path
        headers = self._extract_headers(req)
        data = self._data(path=path, parts=[
            '%d-%d' % (offset, offset + content_length - 1)], headers=headers)
        self._add_metadata_to_resp(resp, data)

    def on_delete(self, req, resp):
        """
        delete a file

        :param req: falcon.Request
        :param resp: falcon.Response
        :return: None
        """

        path = req.path
        res = delete_file(self.get_local_path(path))

        if not res:
            raise falcon.HTTPInternalServerError(
                'path still exists: %s' % path,
                description='the file is still present after attempting '
                            'to delete it')

        resp.text = 'OK'

        self._data(path=path, reset=True)

    def _extract_headers(self, req):
        try:
            headers = {}
            for k, v in req.headers.items():
                k = k.lower()
                if k in self.passthru:
                    headers[k] = v
                elif k.startswith('x-head-'):
                    headers[k[7:]] = v
            return headers
        except TypeError:
            return {}

    def _add_metadata_to_resp(self, resp, data):
        if data.disabled:
            return
        byte_ranges = \
            condense_byte_ranges(parse_byte_ranges_from_list(data.parts))
        parts = ['%d-%d' % (row[0], row[1]) for row in byte_ranges]
        resp.append_header('x-parts', ','.join(parts))
        for k, v in data.headers.items():
            try:
                resp.append_header(
                    '{prefix}{name}'.format(
                        prefix='' if k in self.passthru else 'x-head-',
                        name=k),
                    '{}'.format(v))
            except Exception:
                pass

    def _data(self, **kwargs):
        return MetaData(db=self._db, **kwargs)

    def _error_to_response(self, resp, ex):
        if ex.title is not None:
            resp.append_header('X-ERROR-CODE', ex.title)
        if ex.description is not None:
            resp.append_header('X-ERROR-MESSAGE', ex.description)
        raise ex
