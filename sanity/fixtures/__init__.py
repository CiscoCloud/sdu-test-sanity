# -*- coding: utf-8 -*-
# Copyright 2015-2016 Cisco Systems, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
from datetime import datetime

from sanity.results import Success, Error, Skipped, Failure  # NOQA


class Fixture():
    result = Success()
    LOG = logging.getLogger(__name__)

    def __init__(self, keystone, nova, neutron, glance, state):
        self.keystone = keystone
        self.nova = nova
        self.neutron = neutron
        self.glance = glance
        self.state = state

    def setUp(self):
        start = datetime.utcnow()
        if hasattr(self, '_setUp'):
            try:
                result = self._setUp()
            except:
                result = Error()
        else:
            result = self.result
        end = datetime.utcnow()
        result.duration = end - start
        return result

    def tearDown(self):
        start = datetime.utcnow()
        if hasattr(self, '_tearDown'):
            try:
                result = self._tearDown()
            except:
                result = Error()
        else:
            result = self.result
        end = datetime.utcnow()
        result.duration = end - start
        return result

    def enableFixture(self, server):
        if self.result.is_failure():
            return self.result
        start = datetime.utcnow()
        try:
            result = self._enableFixture(server)
        except:
            result = Error()
        end = datetime.utcnow()
        result.duration = end - start
        return result

    def disableFixture(self, server):
        if self.result.is_failure():
            return self.result
        start = datetime.utcnow()
        try:
            result = self._disableFixture(server)
        except:
            result = Error()
        end = datetime.utcnow()
        result.duration = end - start
        return result


def useFixture(fixture):
    """Decorate classes that require fixtures"""
    def wrapper(f):
        if not hasattr(f, '_fixtures'):
            f._fixtures = []
        f._fixtures.append(fixture)
        return f
    return wrapper


def getFixtures(method):
    """Return a methods fixtures"""
    method_name = method.__name__
    inst = method.__self__

    if hasattr(inst, '_' + method_name):
        method = getattr(inst, '_' + method_name)
    return getattr(method, '_fixtures', [])


from sanity.fixtures.floatingip import FloatingIPFixture  # NOQA

FIXTURES = {
    FloatingIPFixture.shortname: FloatingIPFixture,
}


def get_enabled_fixtures(fixtures=[]):
    fixture_classes = []
    for fixture in fixtures:
        if fixture not in FIXTURES:
            raise ValueError('Test %s is not one of %s'
                             % (fixture, list(FIXTURES.keys())))
        fixture_classes.append(FIXTURES[fixture])
    return fixture_classes
