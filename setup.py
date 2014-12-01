#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2014, Deutsche Telekom AG - Laboratories (T-Labs)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from setuptools import setup, find_packages


setup(name='litedesk-lib-active_directory',
    version='0.0.1',
    description='Active Directory library for LiteDesk',
    author='Łukasz Biernot',
    author_email='lukasz.biernot@lgmail.com',
    url='http://laboratories.telekom.com',
    packages=find_packages(),
    package_dir={
        'litedesk.lib.active_directory': 'src/litedesk/lib/active_directory',
        'litedesk.lib.active_directory.classes': 'src/litedesk/lib/active_directory/classes',
    },
    namespace_packages=['litedesk', 'litedesk.lib'],
    install_requires=['python-ldap', ],
    zip_safe=False,
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache License 2.0',
        'Operating System :: Linux',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX',
        'Programming Language :: Python',
    ],
    keywords='litedesk active_directory',
)
