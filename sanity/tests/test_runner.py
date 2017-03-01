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

from sanity import runner
from sanity import results
from sanity import fixtures


class MockFixture(mock.Mock):
    result = results.Result()

    def setUp(self):
        return self.result


class MockTest(mock.Mock):
    result = results.Result()

    def test_server(self, server):
        return self.result


class TestSanityState(TestCase):

    DEFAULT_ARGS = ('http://mock', 'mock-tenant', 'mock-username',
                    'mock-password', 'mock-endpoint')

    def setUp(self):
        pass

    @mock.patch('sanity.runner.os_sdk.create_connection')
    def test_setUpFixtures(self, u_clientmanager):

        class MockTest1(MockTest):
            @fixtures.useFixture(MockFixture)
            def test_server(self, server, fixture):
                return self.result

        r = runner.Runner(*self.DEFAULT_ARGS, state={}, tests=[MockTest1])
        self.assertEqual(r.setUpFixtures(), None)

    @mock.patch('sanity.runner.os_sdk.create_connection')
    def test_setUpFixtures_failure(self, u_clientmanager):

        class MockFixture1(MockFixture):
            result = results.Failure()

        class MockTest1(MockTest):
            @fixtures.useFixture(MockFixture1)
            def test_server(self, server, fixture):
                return self.result

        r = runner.Runner(*self.DEFAULT_ARGS, state={}, tests=[MockTest1])
        result = r.setUpFixtures()
        self.assertTrue(isinstance(result, results.Failure))
        self.assertTrue(result.is_failure())

        # Check we get the same result on a second call
        result = r.setUpFixtures()
        self.assertTrue(isinstance(result, results.Failure))
        self.assertTrue(result.is_failure())
