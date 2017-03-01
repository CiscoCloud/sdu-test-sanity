#!/usr/bin/env python
# -*- coding: utf-8 -*-


from setuptools import setup, find_packages


with open('README.rst') as readme_file:
    readme = readme_file.read()

requirements = [
    'openstacksdk>=0.9.6',
    'pbr',
    'python-novaclient',
    'prettytable',
    'paramiko',
    'six',
    'passlib',
    'oslo.config>=2.7.0',
]

test_requirements = [
    # TODO: put package test requirements here
]

setup(
    name='sanity',
    version='0.1.0',
    description="Host based functional testing for clouds.",
    long_description=readme,
    author="Russell Sim",
    author_email='rusim@cisco.com',
    url='',
    packages=find_packages(),
    package_dir={'sanity':
                 'sanity'},
    include_package_data=True,
    install_requires=requirements,
    license="BSD",
    zip_safe=False,
    keywords='sanity',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    test_suite='tests',
    tests_require=test_requirements,
    entry_points={
        'console_scripts': [
            'sanity = sanity.cli:main',
        ],
    },
)
