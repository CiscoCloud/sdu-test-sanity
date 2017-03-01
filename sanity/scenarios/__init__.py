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

from sanity.results import Error, Skipped, Failure  # NOQA
from sanity import results


LOG = logging.getLogger(__name__)


class UnbootableServer(dict):
    def __init__(self, *args, **kwargs):
        if not kwargs.get('id'):
            kwargs['id'] = self.__class__.__name__
        if not kwargs.get('metadata'):
            kwargs['metadata'] = {}
        if not kwargs.get('status'):
            kwargs['status'] = None
        super(UnbootableServer, self).__init__(*args, **kwargs)
        self.__dict__ = self


def has_booted(server):
    return not isinstance(server, UnbootableServer)


class Success(results.Result):
    def __init__(self, *args, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __str__(self):
        seconds = self.duration.seconds
        return ('PASS {:02}:{:02}'.format(
            seconds % 3600 // 60, seconds % 60))

    def to_dict(self):
        return {
            'result': self.__class__.__name__,
            'duration': self.duration.seconds,
        }


class SanityScenario(object):
    name = None
    log = LOG

    def __init__(self, keystone, nova, neutron, glance, state):
        self.keystone = keystone
        self.nova = nova
        self.neutron = neutron
        self.glance = glance
        self._state = state

    @property
    def _flavor(self):
        return self._state['flavor']

    @property
    def _external_net(self):
        return self._state['external_net']

    @property
    def _availability_zone(self):
        return self._state['availability_zone']

    @property
    def _image(self):
        return self._state['image']

    @property
    def _keypair(self):
        return self._state['keypair']

    @property
    def _security_group(self):
        return self._state['security_group']

    @property
    def _router(self):
        return self._state['router']

    @property
    def _network(self):
        return self._state['network']

    def setUp(self):
        """The class setup function.

        Should be able to be called multiple times."""
        start = datetime.utcnow()
        if hasattr(self, '_setUp'):
            try:
                result = self._setUp()
            except:
                result = Error()
        else:
            result = Success()
        end = datetime.utcnow()
        result.duration = end - start
        return result

    def test_server(self, server, *fixtures):
        start = datetime.utcnow()
        try:
            result = self._test_server(server, *fixtures)
        except:
            result = Error()
        end = datetime.utcnow()
        result.duration = end - start
        return result

    def tearDown(self):
        """The class tear down function

        Should be able to be called without having a successful setup."""
        start = datetime.utcnow()
        if hasattr(self, '_tearDown'):
            try:
                result = self._tearDown()
            except:
                result = Error()
        else:
            result = Success()
        end = datetime.utcnow()
        result.duration = end - start
        return result


from sanity.scenarios.boot import BootScenario  # noqa
from sanity.scenarios.console import ConsoleScenario  # noqa
from sanity.scenarios.float import FloatScenario  # noqa
from sanity.scenarios.ping import PingScenario  # noqa
from sanity.scenarios.vnc_console import VNCConsoleScenario  # noqa

TESTS = {
    BootScenario.shortname: BootScenario,
    ConsoleScenario.shortname: ConsoleScenario,
    FloatScenario.shortname: FloatScenario,
    PingScenario.shortname: PingScenario,
    VNCConsoleScenario.shortname: VNCConsoleScenario,
}

DEFAULT = [BootScenario.shortname,
           ConsoleScenario.shortname,
           VNCConsoleScenario.shortname,
           FloatScenario.shortname]


def get_enabled_tests(tests=[]):
    test_classes = []
    for test in tests or DEFAULT:
        if test not in TESTS:
            raise ValueError('Test %s is not one of %s'
                             % (test, list(TESTS.keys())))
        test_classes.append(TESTS[test])
    return test_classes
