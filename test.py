#!/usr/bin/env python
import unittest
import string
import random
import webtest
import os
import shutil
import redislite
import napfs
import falcon
import hashlib
from napfs.helpers import condense_byte_ranges, \
    get_last_contiguous_byte

redis_connection = redislite.StrictRedis(dbfilename='/tmp/test-napfs.db')
NAPFS_DATA_DIR = '/tmp/test-napfs'


def create_app():
    if not os.path.exists(NAPFS_DATA_DIR):
        os.mkdir(NAPFS_DATA_DIR)
    return webtest.TestApp(napfs.create_app(
        data_dir=NAPFS_DATA_DIR, redis_connection=redis_connection))


def create_router_app(router):
    if not os.path.exists(NAPFS_DATA_DIR):
        os.mkdir(NAPFS_DATA_DIR)
    app = falcon.API()
    app.add_sink(router, '/')
    return webtest.TestApp(app)


def create_app_no_redis():
    return webtest.TestApp(napfs.create_app(data_dir=NAPFS_DATA_DIR))


def random_string(length=1024):
    return ''.join(
        [random.choice(string.ascii_letters + string.digits) for _ in
         range(length)]).encode('utf-8')


def clean():
    shutil.rmtree(NAPFS_DATA_DIR)
    if redis_connection:
        redis_connection.flushdb()


class TestMain(unittest.TestCase):
    def test_read_write(self):
        data = random_string()
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        app = create_app()
        res = app.get(uri, expect_errors=True)
        self.assertEqual(res.status_code, 404)
        res = app.patch(uri, params=data,
                        headers={'Content-Type': 'text/plain',
                                 'x-head-foo': 'bar'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers['x-parts'], '0-1023')

        res = app.get(uri)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.body, data)
        self.assertEqual(res.headers['x-parts'], '0-1023')
        self.assertEqual(res.headers['x-head-foo'], 'bar')

        chunk = random_string()
        app.patch('%s?offset=%s' % (uri, len(data)), params=chunk,
                  headers={'Content-Type': 'text/plain',
                           'x-head-bazz': 'test', 'x-head-uploadrate': '1234'})

        res = app.get(uri)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.body, data + chunk)
        self.assertEqual(res.headers['x-parts'], '0-2047')

        res = app.get(uri, headers={'Range': 'bytes=100-'})
        self.assertEqual(res.status_code, 206)
        self.assertEqual(res.body, data[100:] + chunk)
        self.assertEqual(res.headers['x-head-foo'], 'bar')
        self.assertEqual(res.headers['x-head-bazz'], 'test')

        app.patch('%s?offset=%s' % (uri, len(data + chunk) + 100),
                  params='test',
                  headers={'Content-Type': 'text/plain'})

        res = app.get(uri)
        self.assertEqual(res.body, data + chunk)
        self.assertEqual(res.headers['x-parts'], '0-2047,2148-2151')

        res = app.delete(uri)
        self.assertEqual(res.status_code, 200)

        res = app.get(uri, expect_errors=True)
        self.assertEqual(res.status_code, 404)

    def test_copy(self):
        data = random_string()
        src = "test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))
        dst = "test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        app = create_app()

        res = app.post('/%s' % src, params=data,
                       headers={'Content-Type': 'text/plain'})
        self.assertEqual(res.status_code, 200)

        res = app.post('/%s' % dst, headers={'x-source': '/%s' % src})
        self.assertEqual(res.status_code, 200)

        res = app.get('/%s' % dst)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.body, data)

    def test_checksum(self):
        uri = "/%s" % random_string(10)
        data = random_string()
        app = create_app()
        app.post(uri, headers={'Content-Type': 'text/plain'}, params=data)
        res = app.get(uri, headers={'x-checksum': 'sha1'})
        self.assertEqual(res.status_code, 200)


class ByteRangeTests(unittest.TestCase):
    def test_gap(self):
        byte_ranges = [[0, 9], [10, 19], [20, 29], [40, 49]]
        res = condense_byte_ranges(byte_ranges)
        self.assertEqual(res, [[0, 29], [40, 49]])

    def test_empty(self):
        byte_ranges = []
        res = condense_byte_ranges(byte_ranges)
        self.assertEqual(res, [])

    def test_overlap(self):
        byte_ranges = [[0, 9], [0, 19], [20, 29], [40, 49]]
        res = condense_byte_ranges(byte_ranges)
        self.assertEqual(res, [[0, 29], [40, 49]])


class ContiguousTests(unittest.TestCase):
    def test_contiguous(self):
        last = get_last_contiguous_byte([[0, 10], [11, 20]])
        self.assertEqual(last, 20)
        last = get_last_contiguous_byte([[0, 10], [0, 0], [5, 20]])
        self.assertEqual(last, 20)
        last = get_last_contiguous_byte([[0, 10], [22, 100], [11, 20]])
        self.assertEqual(last, 20)


class TestLongPatch(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test(self):
        seed = random_string()
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))
        data = b''
        for i in range(0, 20):
            res = self.app.patch(
                "%s?offset=%d" % (uri, len(data)),
                params=seed,
                headers={'Content-Type': 'text/plain'})
            data += seed
            self.assertEqual(res.headers['x-parts'], '0-%d' % (len(data) - 1))
            res = self.app.get(uri)
            self.assertEqual(res.body, data)
            self.assertEqual(res.headers['content-length'], '%d' % len(data))

        new_uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        self.app.post(new_uri, headers={'x-source': uri})
        res = self.app.get(new_uri)
        self.assertEqual(res.body, data)
        self.assertEqual(res.headers['content-length'], '%d' % len(data))

        res = self.app.delete(uri)
        self.assertEqual(res.body, b'OK')

        res = self.app.delete(new_uri)
        self.assertEqual(res.body, b'OK')


class NonSequentialTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test(self):
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        self.app.patch("%s?offset=0" % uri, params='aaa',
                       headers={'Content-Type': 'text/plain'})

        self.app.patch("%s?offset=6" % uri, params='ccc',
                       headers={'Content-Type': 'text/plain'})

        res = self.app.get(uri)
        self.assertEqual(res.body, b'aaa')
        self.assertEqual(res.headers['x-parts'], '0-2,6-8')

        self.app.patch("%s?offset=3" % uri, params='bbb',
                       headers={'Content-Type': 'text/plain'})

        res = self.app.get(uri)
        self.assertEqual(res.body, b'aaabbbccc')
        self.assertEqual(res.headers['x-parts'], '0-8')


class MissingFirstTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test(self):
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        self.app.patch("%s?offset=10" % uri, params='aaa',
                       headers={'Content-Type': 'text/plain'})

        self.app.patch("%s?offset=13" % uri, params='ccc',
                       headers={'Content-Type': 'text/plain'})

        res = self.app.get(uri, expect_errors=True)
        self.assertEqual(res.status_code, 404)


class FirstLastTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test(self):
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        self.app.patch("%s?offset=3" % uri, params='bbb',
                       headers={'Content-Type': 'text/plain'})

        res = self.app.get(uri, headers={'Range': 'bytes=0-*'},
                           expect_errors=True)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.headers['Content-Length'], '0')

        self.app.patch("%s?offset=0" % uri, params='aaa',
                       headers={'Content-Type': 'text/plain'})


class ExpireDataTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test(self):
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        self.app.patch("%s?offset=0" % uri, params='aaa',
                       headers={'Content-Type': 'text/plain'})

        redis_connection.flushdb()

        res = self.app.get(uri, expect_errors=True)
        self.assertEqual(res.status_code, 404)

        self.app.patch("%s?offset=0" % uri, params='aa',
                       headers={'Content-Type': 'text/plain'})

        res = self.app.get(uri)

        self.assertEqual(b'aa', res.body)


class SingleByteTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test(self):
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        self.app.patch("%s?offset=0" % uri, params=b'a',
                       headers={'Content-Type': 'text/plain'})

        res = self.app.get(uri)
        self.assertEqual(res.body, b'a')


class SingleByteOffsetTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test(self):
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        self.app.patch("%s?offset=1" % uri, params='a',
                       headers={'Content-Type': 'text/plain'})

        res = self.app.get(uri, expect_errors=True)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.body, b'')


class ChecksumPartTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test_fail(self):
        uri = "/test/%s.txt" % random_string(10)
        res = self.app.patch("%s" % uri, params='a',
                             headers={'Content-Type': 'text/plain',
                                      'x-checksum': 'garbage'},
                             expect_errors=True)
        self.assertEqual(res.status_code, 412)
        self.assertEqual(res.headers['x-error-code'], 'CHECKSUM_FAIL')

        res = self.app.get(uri, expect_errors=True)
        self.assertEqual(res.status_code, 404)

    def test_success(self):
        uri = "/test/%s.txt" % random_string(10)
        body = 'a'
        checksum = hashlib.sha1()
        checksum.update(body.encode('utf-8'))
        res = self.app.patch("%s" % uri, params=body,
                             headers={'Content-Type': 'text/plain',
                                      'x-checksum': checksum.hexdigest()})
        self.assertEqual(res.status_code, 200)

        res = self.app.get(uri)
        self.assertEqual(res.status_code, 200)


class PassthroughHeadersTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

        router = napfs.Router(data_dir=NAPFS_DATA_DIR,
                              redis_connection=redis_connection,
                              passthrough_headers=['x-YO'])
        self.passthru_app = create_router_app(router)

    def tearDown(self):
        clean()

    def test_stripping_headers(self):
        uri = "/test/1/2/3"
        self.app.patch(uri, params='a',
                       headers={'x-yo': 'yoback'})
        res = self.app.get(uri)
        self.assertFalse('x-yo' in res.headers)

    def test_passthrough_headers(self):
        uri = "/test/1/2/3"
        self.passthru_app.patch(uri, params='a', headers={'x-yo': 'yoBack'})
        res = self.passthru_app.get(uri)
        self.assertEqual(res.headers['x-yo'], 'yoBack')


class VideoContentTypeCheck(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def tearDown(self):
        clean()

    def test(self):
        uri = "/test/%s/%s/%s.mp4" % (
            random_string(2),
            random_string(2),
            random_string(10))

        video_file_path = os.path.join(os.path.dirname(__file__),
                                       'sample-video.mp4')
        with open(video_file_path, 'rb') as f:
            video_content = f.read()
        self.app.patch(uri, params=video_content,
                       headers={'Content-Type': 'video/mp4'})

        res = self.app.get(uri)
        self.assertEqual(res.body, video_content)
        self.assertEqual(res.headers['content-type'], 'video/mp4')


class NoRedisTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app_no_redis()

    def tearDown(self):
        clean()

    def test_read_write(self):
        data = random_string()
        uri = "/test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        app = self.app
        res = app.get(uri, expect_errors=True)
        self.assertEqual(res.status_code, 404)
        res = app.patch(uri, params=data,
                        headers={'Content-Type': 'text/plain'})
        self.assertEqual(res.status_code, 200)

        res = app.get(uri)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.body, data)

        chunk = random_string()
        app.patch('%s?offset=%s' % (uri, len(data)), params=chunk,
                  headers={'Content-Type': 'text/plain'})

        res = app.get(uri)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.body, data + chunk)

        res = app.get(uri, headers={'Range': 'bytes=100-'})
        self.assertEqual(res.status_code, 206)
        self.assertEqual(res.body, data[100:] + chunk)

        res = app.get(uri)
        self.assertEqual(res.body, data + chunk)

        res = app.delete(uri)
        self.assertEqual(res.status_code, 200)

        res = app.get(uri, expect_errors=True)
        self.assertEqual(res.status_code, 404)

    def test_copy(self):
        data = random_string()
        src = "test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))
        dst = "test/%s/%s/%s.txt" % (
            random_string(2),
            random_string(2),
            random_string(10))

        app = self.app

        res = app.post('/%s' % src, params=data,
                       headers={'Content-Type': 'text/plain'})
        self.assertEqual(res.status_code, 200)

        res = app.post('/%s' % dst, headers={'x-source': '/%s' % src})
        self.assertEqual(res.status_code, 200)

        res = app.get('/%s' % dst)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.body, data)

    def test_checksum(self):
        uri = "/%s" % random_string(10)
        data = random_string()
        app = self.app
        app.post(uri, headers={'Content-Type': 'text/plain'}, params=data)
        res = app.get(uri, headers={'x-checksum': 'sha1'})
        self.assertEqual(res.status_code, 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
