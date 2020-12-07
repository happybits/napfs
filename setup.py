#!/usr/bin/env python
import os
from os import path
from setuptools import setup
import importlib.machinery

MYDIR = path.abspath(os.path.dirname(__file__))
long_description = open(os.path.join(MYDIR, 'README.md')).read()
version = importlib.machinery.SourceFileLoader(
    'version',
    path.join('.', 'napfs', 'version.py')
).load_module().__version__

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
        'Programming Language :: Python',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Environment :: Web Environment',
        'Operating System :: POSIX',
    ],
    license='MIT',
    install_requires=[
        'falcon>=0.3.0',
    ],
    include_package_data=True,
    long_description=long_description,
    cmdclass=cmdclass,
    ext_modules=ext_modules
)
