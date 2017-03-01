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

import six
from novaclient import client as no_client

from sanity import fixtures
from sanity import os_sdk

LOG = logging.getLogger(__name__)


class Runner(object):
    name = None
    log = LOG

    def __init__(self,
                 auth_url,
                 tenant,
                 username,
                 password,
                 endpoint_type,
                 state,
                 tests=[]):
        self._test_results = {}
        clientmanager = os_sdk.create_connection(
            auth_url, tenant, username, password,
            endpoint_type=endpoint_type)
        self.keystone = clientmanager.identity
        self.nova = no_client.Client(
            '2', session=clientmanager.session)
        self.neutron = clientmanager.network
        self.glance = clientmanager.image
        self._state = state
        self.tests = []
        self.fixtures = {}
        for test in tests:
            self.tests.append(
                test(self.keystone, self.nova,
                     self.neutron, self.glance,
                     self._state))

    def update_state(self, state):
        assert state, "Tried to update with an empty state."
        self._state = state

    def get_state(self):
        return self._state

    def _log_failure(self, server, result):
        self.log.info("%s server %s on host %s",
                      result, server.id, server.metadata.get('host_id'))

        if result.traceback:
            traceback = result.traceback.split('\n')
        else:
            traceback = ''

        reason = getattr(result, 'reason', '')
        self.log.info('server %s: %s %s' % (server.id, reason, traceback))

    def run(self, sanity, servers=[]):
        for server in servers:
            self.run_server(sanity, server)
        for fixture in self.fixtures.values():
            fixture.tearDown()
        self.fixtures = {}

    def setUpFixtures(self):
        for test in self.tests:
            for fixture in fixtures.getFixtures(test.test_server):
                if fixture not in self.fixtures:
                    self.fixtures[fixture] = fixture(self.keystone, self.nova,
                                                     self.neutron, self.glance,
                                                     self._state)

                result = self.fixtures[fixture].setUp()
                if result.is_failure():
                    return result

    def run_server(self, sanity, server):
        current_host = (getattr(server, 'OS-EXT-SRV-ATTR:host') or
                        server.metadata['host_id'])
        self.setUpFixtures()
        for test in self.tests:

            result = test.setUp()
            if result.is_failure():
                sanity.add_test_result(test.name, current_host,
                                       server.id, result)
                self.maybe_log_failure(server, result)
                continue

            LOG.info('Running %s: %s' % (test.name, server.id))
            try:
                self._run_test(sanity, test, server)
            except Exception as e:
                LOG.exception(e)

            result = test.tearDown()
            if result.is_failure():
                sanity.add_test_result(test.name, current_host,
                                       server.id, result)
                self.maybe_log_failure(server, result)
                continue

            for fixture in fixtures.getFixtures(test.test_server):
                result = self.fixtures[fixture].disableFixture(server)
                if result.is_failure():
                    self.maybe_log_failure(server, result)

    def cleanup(self):
        for fixture in self.fixtures.values():
            result = fixture.tearDown()
            if result.is_failure():
                if result.traceback:
                    traceback = result.traceback.split('\n')
                else:
                    traceback = ''
                self.log.error('%s %s' % (getattr(result, 'reason', ''),
                                          traceback))

    def maybe_log_failure(self, server, result):
        if result.is_failure():
            self._log_failure(server, result)

    def _run_test(self, sanity, test, server):
        if isinstance(server, six.string_types):
            server = self.nova.servers.get(server)

        # XXX Should we be indicating the source of the hostname
        # somewhere?
        current_host = (getattr(server, 'OS-EXT-SRV-ATTR:host') or
                        server.metadata['host_id'])

        used_fixtures = []
        for fixture in fixtures.getFixtures(test.test_server):
            if fixture not in self.fixtures:
                self.fixtures[fixture] = fixture(self.keystone, self.nova,
                                                 self.neutron, self.glance,
                                                 self._state)
            used_fixtures.append(self.fixtures[fixture])
            result = self.fixtures[fixture].setUp()
            if result.is_failure():
                sanity.add_test_result(test.name, current_host,
                                       server.id, result)
                self.maybe_log_failure(server, result)
                return result

            result = self.fixtures[fixture].enableFixture(server)
            if result.is_failure():
                sanity.add_test_result(test.name, current_host,
                                       server.id, result)
                self.maybe_log_failure(server, result)
                return result

        result = test.test_server(server, *used_fixtures)
        sanity.add_test_result(test.name, current_host, server.id, result)
        self.maybe_log_failure(server, result)
