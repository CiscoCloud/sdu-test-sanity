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
import Queue
import mock

from sanity import cli
from sanity import scenarios


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


class TestTesterThread(TestCase):
    def setup_conf(self, conf, **kwargs):
        conf.keystone = AttrDict()
        conf.keystone.auth_url = 'mock://localhost'
        conf.keystone.tenant_name = 'mock_tenant'
        conf.keystone.username = 'mock_username'
        conf.keystone.password = 'secret'
        conf.keystone.endpoint_type = 'publicURL'
        conf.action = AttrDict(**kwargs)

    def setup_tester(self):
        self.in_queue = Queue.Queue()
        self.out_queue = Queue.Queue()
        self.insanity = mock.Mock()
        tester = cli.Tester(in_queue=self.in_queue,
                            out_queue=self.out_queue,
                            insanity=self.insanity)
        self.assertEqual(self.insanity.mock_calls, [mock.call.get_state()])
        self.insanity.reset_mock()
        self.assertTrue(self.in_queue.empty())
        self.assertTrue(self.out_queue.empty())
        return tester

    def assertAllProcessed(self):
        self.assertTrue(self.in_queue.empty())
        self.assertTrue(self.out_queue.empty())

    @mock.patch('sanity.runner.Runner')
    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_finished_processing(self, cli_conf, mock_runner):
        self.setup_conf(cli_conf,
                        no_delete_failed=False, no_delete=False, test=[])
        tester = self.setup_tester()
        tester.finish()
        tester()

    @mock.patch('sanity.runner.Runner')
    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_processing_a_host(self, cli_conf, mock_runner):
        self.setup_conf(cli_conf,
                        no_delete_failed=False, no_delete=False, test=[])
        tester = self.setup_tester()
        server = mock.Mock()
        self.in_queue.put(server)
        tester.finish()
        tester()
        server = self.out_queue.get_nowait()
        self.assertAllProcessed()
        self.assertEqual(mock_runner().method_calls,
                         [mock.call.run_server(self.insanity, server),
                          mock.call.cleanup()])
        self.assertEqual(server.mock_calls,
                         [mock.call.delete()])
        self.assertEqual(self.insanity.mock_calls,
                         [mock.call.wait_for_servers([server])])

    @mock.patch('sanity.runner.Runner')
    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_processing_an_unbootable_server(self, cli_conf, mock_runner):
        self.setup_conf(cli_conf,
                        no_delete_failed=False, no_delete=False, test=[])
        tester = self.setup_tester()
        server = scenarios.UnbootableServer()
        self.in_queue.put(server)
        tester.finish()
        tester()
        server = self.out_queue.get_nowait()
        self.assertAllProcessed()
        self.assertEqual(mock_runner().method_calls,
                         [mock.call.run_server(self.insanity, server),
                          mock.call.cleanup()])
        self.assertEqual(self.insanity.mock_calls, [])

    @mock.patch('sanity.runner.Runner')
    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_tester_stopped_server_delete_negative(self, cli_conf,
                                                   mock_runner):
        self.setup_conf(cli_conf,
                        no_delete_failed=False, no_delete=False, test=[])
        tester = self.setup_tester()
        server = mock.Mock()
        server.delete.side_effect = Exception('error deleting')
        self.in_queue.put(server)
        tester.finish()
        tester.stop()
        tester()
        self.assertAllProcessed()
        server.delete.assert_called_once_with()
        self.assertEqual(mock_runner().method_calls,
                         [mock.call.cleanup()])
        self.assertEqual(self.insanity.mock_calls, [])

    @mock.patch('sanity.runner.Runner')
    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_tester_stopped_server_delete(self, cli_conf, mock_runner):
        self.setup_conf(cli_conf,
                        no_delete_failed=False, no_delete=False, test=[])
        tester = self.setup_tester()
        server = mock.Mock()
        self.in_queue.put(server)
        tester.finish()
        tester.stop()
        tester()
        self.assertAllProcessed()
        server.delete.assert_called_once_with()
        self.assertEqual(mock_runner().method_calls,
                         [mock.call.cleanup()])
        self.assertEqual(self.insanity.mock_calls, [])

    @mock.patch('sanity.runner.Runner')
    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    @mock.patch.object(cli.Tester, 'test_server')
    def test_server_test_exception(self, test_server, cli_conf, mock_runner):
        self.setup_conf(cli_conf,
                        no_delete_failed=False, no_delete=False, test=[])
        test_server.side_effect = Exception("Failed")
        tester = self.setup_tester()
        server = mock.Mock()
        self.in_queue.put(server)
        tester.finish()
        tester()
        test_server.assert_called_once_with(server)
        server = self.out_queue.get_nowait()
        self.assertAllProcessed()
        self.assertEqual(mock_runner().method_calls,
                         [mock.call.cleanup()])
        self.assertEqual(self.insanity.mock_calls, [])

    @mock.patch('sanity.runner.Runner')
    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    @mock.patch.object(cli.Tester, 'delete_server')
    def test_delete_server_exception(self, delete_server, cli_conf,
                                     mock_runner):
        self.setup_conf(cli_conf,
                        no_delete_failed=False, no_delete=False, test=[])
        delete_server.side_effect = Exception("Failed")
        tester = self.setup_tester()
        server = mock.Mock()
        self.in_queue.put(server)
        tester.finish()
        tester()
        delete_server.assert_called_once_with(server)
        server = self.out_queue.get_nowait()
        self.assertAllProcessed()
        self.assertEqual(mock_runner().method_calls,
                         [mock.call.run_server(self.insanity, server),
                          mock.call.cleanup()])
        self.assertEqual(self.insanity.mock_calls,
                         [mock.call.wait_for_servers([server])])


class UnitTestTesterThread(TestCase):
    def setup_conf(self, conf):
        conf.keystone = AttrDict()
        conf.keystone.auth_url = 'mock://localhost'
        conf.keystone.tenant_name = 'mock_tenant'
        conf.keystone.username = 'mock_username'
        conf.keystone.password = 'secret'
        conf.keystone.endpoint_type = 'publicURL'

    @mock.patch('sanity.runner.Runner')
    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_initialize(self, cli_conf, mock_runner):
        in_queue = Queue.Queue()
        out_queue = Queue.Queue()
        insanity = mock.Mock()
        self.setup_conf(cli_conf)
        conf = AttrDict(no_delete_failed=False, no_delete=False, test=[])
        cli_conf.action = conf
        tester = cli.Tester(in_queue=in_queue,
                            out_queue=out_queue,
                            insanity=insanity)
        mock_runner().setUpFixtures.return_value = None
        tester.initialize()
        self.assertEqual(tester.compromised, False)

        mock_runner().setUpFixtures.return_value = mock.sentinel
        tester.initialize()
        self.assertEqual(tester.compromised, True)


class TestFixturerThread(TestCase):
    def setup_conf(self, conf, **kwargs):
        conf.keystone = AttrDict()
        conf.keystone.auth_url = 'mock://localhost'
        conf.keystone.tenant_name = 'mock_tenant'
        conf.keystone.username = 'mock_username'
        conf.keystone.password = 'secret'
        conf.keystone.endpoint_type = 'publicURL'
        conf.action = AttrDict(**kwargs)

    def setup_tester(self):
        self.in_queue = Queue.Queue()
        self.out_queue = Queue.Queue()
        self.insanity = mock.Mock()
        tester = cli.Fixturer(in_queue=self.in_queue,
                              out_queue=self.out_queue,
                              insanity=self.insanity)
        self.assertEqual(self.insanity.mock_calls, [])
        self.insanity.reset_mock()
        self.assertTrue(self.in_queue.empty())
        self.assertTrue(self.out_queue.empty())
        return tester

    def assertAllProcessed(self):
        self.assertTrue(self.in_queue.empty())
        self.assertTrue(self.out_queue.empty())

    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_finished_processing(self, cli_conf):
        self.setup_conf(cli_conf, no_delete_failed=False, with_fixture=[])
        tester = self.setup_tester()
        tester.finish()
        tester()

    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_processing_a_host(self, cli_conf):
        self.setup_conf(cli_conf, no_delete_failed=False, with_fixture=[])
        tester = self.setup_tester()
        server = mock.Mock()
        self.in_queue.put(server)
        tester.finish()
        tester()
        server = self.out_queue.get_nowait()
        self.assertAllProcessed()
        self.assertEqual(server.mock_calls, [])
        self.assertEqual(self.insanity.mock_calls,
                         [mock.call.wait_for_servers([server]),
                          mock.call.state.nova.servers.get(server)])

    @mock.patch('sanity.cli.CONF', new_callable=AttrDict)
    def test_initialize(self, cli_conf):
        self.setup_conf(cli_conf, no_delete_failed=False, with_fixture=[])
        tester = self.setup_tester()
        tester.initialize()
        self.assertEqual(tester.compromised, False)
