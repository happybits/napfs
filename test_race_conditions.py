#!/usr/bin/env python

import napfs
import threading
import multiprocessing
import string
import uuid
import random
import argparse
import time
from StringIO import StringIO

try:
    import gevent.monkey
except ImportError:
    gevent = None

import napfs.fs

PRINT_DEBUG = True


results = []


def upload(path, data, offset, chunk_size):
    time.sleep(1 - time.time() % 1)
    start = time.time()
    napfs.fs.write_file_chunk(path, StringIO(data), offset, chunk_size)
    end = time.time()
    r = {'start': start, 'end': end, 'offset': offset}
    if PRINT_DEBUG:
        print("offset=%s start=%.5f end=%.5f" % (
            r['offset'],
            r['start'],
            r['end']))

    results.append(r)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='test race condition in speedy backend')
    parser.add_argument(
        '--shuffle',
        help='randomize order of the requests queued',
        action='store_true',
        default=False)

    parser.add_argument(
        '--use-threads',
        help='use threads - if false will use multi process',
        action='store_true',
        default=False)

    parser.add_argument(
        '--use-gevent',
        help='use gevent',
        action='store_true',
        default=False)

    parser.add_argument(
        '--chunk-count',
        type=int,
        help='number of chunks to write',
        default=5)

    parser.add_argument(
        '--chunk-size',
        type=int,
        help='size of each chunk',
        default=50000)

    args = parser.parse_args()

    if args.use_gevent and gevent:
        gevent.monkey.patch_all()
        args.use_threads = True

    if args.use_threads:
        PRINT_DEBUG = False

    path = "/_test/%s.txt" % uuid.uuid4()

    chunk = ''
    while len(chunk) < args.chunk_size:
        chunk += string.ascii_letters + string.digits
    chunk += "\n"

    results = []

    offset = 0
    reqs = []
    for x in range(0, args.chunk_count):
        d = "    %s - %s" % (x, chunk)
        l = len(d)
        reqs.append((path, d, offset, l))
        offset += l

    threads = []
    for a in reqs:
        if args.use_threads:
            threads.append(threading.Thread(target=upload, args=a))
        else:
            threads.append(multiprocessing.Process(target=upload, args=a))

    if args.shuffle:
        random.shuffle(threads)

    [t.start() for t in threads]
    [t.join() for t in threads]

    print("")
    print(path)

    results = sorted(results, key=lambda _x: _x['start'])

    for r in results:
        print("offset=%s start=%.5f end=%.5f" % (
            r['offset'],
            r['start'],
            r['end']))

    print("")

    with napfs.fs.open_file(path, 'rb') as f:
        content = f.read()

    if content == "".join([r[1] for r in reqs]):
        print("OK")
    else:
        print("FAIL")
        print(content)
