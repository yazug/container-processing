#!/usr/bin/env python
# Copyright (c) 2019, Red Hat, Inc.
#   License: MIT
from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

history = ''

TEST_REQUIRES = ['coverage', 'flake8', 'pytest', 'pytest-datadir', 'tox']

setup(
    name='container_processing',
    version='0.0.1',
    setup_requires=['pytest-runner'],
    install_requires=[],
    tests_require=TEST_REQUIRES,
    extras_require={'test': TEST_REQUIRES},
    license='MIT',
    description=("container_processing is a collection of tools for "
                 "working with containers, integration testing, and koji ."),
    long_description=readme + '\n\n' + history,
    author='Red Hat',
    author_email='jschluet@redhat.com',
    maintainer='Jon Schlueter',
    maintainer_email='jschluet@redhat.com',
    packages=find_packages(),
    url='http://github.com/release-depot/container-processing',
    data_files=[("", ["LICENSE"])],
    test_suite='tests',
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities'],
)
