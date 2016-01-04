#!/usr/bin/env python

import unittest
import os
import napfs
import string
import random
import webtest
import napfs.fs
import napfs.rest


class TestMain(unittest.TestCase):
    def test_read_simple(self):
        uri = '/%s' % self.random_string(10)
        path = napfs.fs.PATH_TPL % uri
        input = self.random_string()
        with open(path, 'w+b') as fp:
            fp.write(input)
        try:
            app = webtest.TestApp(napfs.rest.app)
            res = app.get(uri)
            self.assertEqual(res.status_int, 200)
            self.assertEqual(res.body, input)

        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_read_write(self):
        data = self.random_string()
        uri = "/test/%s/%s/%s.txt" % (
            self.random_string(2),
            self.random_string(2),
            self.random_string(10))

        path = napfs.fs.PATH_TPL % uri
        try:
            app = webtest.TestApp(napfs.rest.app)
            res = app.get(uri, expect_errors=True)
            self.assertEqual(res.status_code, 404)
            res = app.patch(uri, params=data,
                            headers={'Content-Type': 'text/plain'})
            self.assertEqual(res.status_code, 200)

            res = app.get(uri)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.body, data)

            chunk = self.random_string()
            res = app.patch('%s?offset=%s' % (uri, len(data)), params=chunk,
                            headers={'Content-Type': 'text/plain'})

            res = app.get(uri)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.body, data + chunk)

            res = app.get(uri, headers={'Range': 'bytes=100-'})
            self.assertEqual(res.status_code, 206)
            self.assertEqual(res.body, data[100:] + chunk)

            res = app.delete(uri)
            self.assertEqual(res.status_code, 200)

            res = app.get(uri, expect_errors=True)
            self.assertEqual(res.status_code, 404)

        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_copy(self):
        data = self.random_string()
        src = "test/%s/%s/%s.txt" % (
            self.random_string(2),
            self.random_string(2),
            self.random_string(10))
        dst = "test/%s/%s/%s.txt" % (
            self.random_string(2),
            self.random_string(2),
            self.random_string(10))

        try:
            app = webtest.TestApp(napfs.rest.app)
            res = app.post('/%s' % src, params=data,
                           headers={'Content-Type': 'text/plain'})
            self.assertEqual(res.status_code, 200)

            res = app.post('/%s' % dst, headers={'x-source': '/%s' % src})
            self.assertEqual(res.status_code, 200)

            res = app.get('/%s' % dst)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.body, data)

        finally:
            if os.path.exists(napfs.fs.PATH_TPL % src):
                os.unlink(napfs.fs.PATH_TPL % src)

            if os.path.exists(napfs.fs.PATH_TPL % dst):
                os.unlink(napfs.fs.PATH_TPL % dst)

    def test_checksum(self):
        uri = "/%s" % self.random_string(10)
        path = napfs.fs.PATH_TPL % uri
        input = self.random_string()
        napfs.fs._initialize_file_path(path)
        with open(path, 'w+b') as fp:
            fp.write(input)
        try:
            app = webtest.TestApp(napfs.rest.app)
            res = app.get(uri, headers={'x-checksum': 'sha1'})
            # print res.body
            self.assertEqual(res.status_code, 200)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def random_string(self, length=1024):
        return ''.join(
            [random.choice(string.ascii_letters + string.digits) for n in
                range(length)]).encode('utf-8')


if __name__ == '__main__':
    unittest.main(verbosity=2)
