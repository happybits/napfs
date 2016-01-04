#!/usr/bin/env python

# std lib imports
from wsgiref.simple_server import make_server
import argparse

# import library
import napfs

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='kick off the napfs server')
    parser.add_argument('-p', '--port', default=3035, type=int,
                        help="specify the port to listen to")

    parser.add_argument('-d', '--data-dir', type=str, default="/tmp/napfs",
                        help="specify the directory to use to write the files")

    args = parser.parse_args()
    httpd = make_server(
        '127.0.0.1',
        args.port,
        napfs.create_app(args.data_dir))

    print("starting server on port %s" % args.port)
    print("data-dir %s" % args.data_dir)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("done")
