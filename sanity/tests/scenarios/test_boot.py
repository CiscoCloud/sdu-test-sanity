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

from unittest import TestCase
import mock

from sanity.scenarios import BootScenario, Success, Failure, UnbootableServer


class TestBootScenario(TestCase):
    def setUp(self):
        self.keystone = mock.Mock()
        self.nova = mock.Mock()
        self.neutron = mock.Mock()
        self.glance = mock.Mock()
        self.state = mock.MagicMock()

        self.scenario = BootScenario(self.keystone, self.nova,
                                     self.neutron, self.glance,
                                     self.state)

    def test_active_server(self):
        server = mock.Mock()
        server.status = 'ACTIVE'
        result = self.scenario.test_server(server)
        self.assertTrue(isinstance(result, Success))

    def test_failed_scheduled_server(self):
        server = mock.MagicMock()
        server.status = 'ERRRR'
        server['OS-EXT-SRV-ATTR:host'] = 'mock_host'
        server.fault = {'message': 'mad cool failure'}
        result = self.scenario.test_server(server)
        self.assertTrue(isinstance(result, Failure))
        self.assertTrue('ERRRR' in result.reason,
                        '"ERRRR" not in %r' % result.reason)
        self.assertEqual(result.exception, 'mad cool failure')

    def test_failed_unscheduled_server(self):
        server = mock.MagicMock()
        server.status = 'ERRRR'
        setattr(server, 'OS-EXT-SRV-ATTR:host', None)
        server.fault = {'message': 'mad cool failure'}
        result = self.scenario.test_server(server)
        self.assertTrue(isinstance(result, Failure))
        self.assertTrue('ERRRR' in result.reason,
                        '"ERRRR" not in %s' % result.reason)
        self.assertTrue('never scheduled' in result.reason,
                        '"never scheduled" not in %r' % result.reason)
        self.assertEqual(result.exception, 'mad cool failure')

    def test_unbootable_server(self):
        result = self.scenario.test_server(UnbootableServer())
        self.assertTrue(isinstance(result, Failure))
