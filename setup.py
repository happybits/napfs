#!/usr/bin/env python

import glob
import os
from os import path
from setuptools import setup, Extension
import sys
import imp

# allow to build with cython, but disable by default.
# build by doing CYTHON_ENABLED=1 python setup.py build_ext --inplace
CYTHON_ENABLED = True if os.getenv('CYTHON_ENABLED', False) else False

MYDIR = path.abspath(os.path.dirname(__file__))
long_description = open(os.path.join(MYDIR, 'README.md')).read()

version = imp.load_source('version',
                          path.join('.', 'napfs', 'version.py')).__version__

JYTHON = 'java' in sys.platform

PYPY = True if getattr(sys, 'pypy_version_info', None) else False

if PYPY or JYTHON:
    CYTHON = False
else:
    try:
        from Cython.Distutils import build_ext
        CYTHON = True
    except ImportError:
        print('\nNOTE: Cython not installed. '
              'hbom will still work fine, but may run '
              'a bit slower.\n')
        CYTHON = False

if CYTHON and CYTHON_ENABLED:
    def list_modules(dirname):
        filenames = glob.glob(path.join(dirname, '*.py'))

        module_names = []
        for name in filenames:
            module, ext = path.splitext(path.basename(name))
            if module != '__init__':
                module_names.append(module)

        return module_names

    ext_modules = [
        Extension('napfs.' + ext, [path.join('napfs', ext + '.py')])
        for ext in list_modules(path.join(MYDIR, 'napfs'))]

    cmdclass = {'build_ext': build_ext}

else:
    cmdclass = {}
    ext_modules = []


setup(
    name='napfs',
    version=version,
    description='NapFS',
    author='John Loehrer',
    author_email='john@happybits.co',
    url='https://github.com/happybits/napfs',
    packages=['napfs'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
    ],
    license='MIT',
    install_requires=[
        'falcon>=0.3.0'
    ],
    include_package_data=True,
    long_description=long_description,
    cmdclass=cmdclass,
    ext_modules=ext_modules
)
