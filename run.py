#!/usr/bin/env python

# std lib imports
from wsgiref import simple_server
import argparse

# import library
import napfs

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='kick off the napfs server')
    parser.add_argument('-p', '--port', default=3035, type=int,
                        help="specify the port to listen to")
    args = parser.parse_args()
    httpd = simple_server.make_server('127.0.0.1', args.port, napfs.app)
    print("starting server on port %s" % args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("done")
