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

from __future__ import print_function

import Queue
import threading
import time
import logging
import signal
import os
import sys
import json
from urlparse import urlparse
from itertools import izip_longest
from collections import defaultdict
from datetime import datetime, timedelta

from prettytable import PrettyTable
from oslo_config import cfg
from novaclient import client as no_client

from packages import humanize
from controller import SanityController, SanityState
from sanity import util
from sanity import runner
from sanity import scenarios
from sanity import compute
from sanity import network
from sanity import host
from sanity import host_lists
from sanity import fixtures
from sanity import os_sdk

# Try to disable insecurity warnings
try:
    import requests.packages.urllib3
    requests.packages.urllib3.disable_warnings()
except:
    pass

# NOTE(ameade): This is a hack as there is no current way to pass
# request timeouts to openstackclient. This ensures connections
# do not hang indefinitely.
import requests
old_request = requests.sessions.Session.request


def new_request(*args, **kwargs):
    kwargs['timeout'] = 60
    return old_request(*args, **kwargs)


requests.sessions.Session.request = new_request
# End gross hack

LOG_FORMAT = ('%(asctime)s %(threadName)s '
              '%(name)s %(levelname)s %(message)s')


INTRODUCTION = """
# This is a python shell, it will execute python commands.

# First thing to do is initialise the environment
start()
"""

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

keystone_opts = [
    cfg.StrOpt('auth_url',
               default=os.environ.get('OS_AUTH_URL')),
    cfg.StrOpt('username',
               default=os.environ.get('OS_USERNAME')),
    cfg.StrOpt('password',
               default=os.environ.get('OS_PASSWORD')),
    cfg.StrOpt('tenant_name',
               default=os.environ.get('OS_TENANT_NAME')),
    cfg.StrOpt('endpoint_type',
               default=os.environ.get('OS_ENDPOINT_TYPE', 'publicURL')),
    cfg.StrOpt('version',
               default=os.environ.get('OS_IDENTITY_API_VERSION', '2.0')),
]

CONF.register_group(
    cfg.OptGroup(name='keystone', title='Keystone Configuration'))
CONF.register_opts(keystone_opts, 'keystone')

opts = [
    cfg.BoolOpt('verbose', default=False),
    cfg.BoolOpt('debug', default=False),
    cfg.StrOpt('log-file', default=None, help='Path to log file.'),
    cfg.IntOpt('ssh_timeout', default=180,
               help='Timeout for tests to connect to ssh into VMs.'),
    cfg.IntOpt('vnc_timeout', default=60,
               help='Timeout for connection to VNC proxy.'),
]

CONF.register_opts(opts)
CONF.register_cli_opts(opts)


def print_heading(*args, **kwargs):
    heading = ' '.join(args)
    print(heading)
    print(kwargs.get('underline', '=') * len(heading), '\n')


def parse_timestamp(timestamp):
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")


def grouper(n, iterable):
    return izip_longest(*[iter(iterable)]*n)


class SimpleSanity(object):
    def __init__(self, sanity):
        self._sanity = sanity

    def start(self):
        self._sanity.setUp()

    def launch_on_each_host(self):
        _host = host.Host(self._sanity)

        self._sanity.wait_for_servers(
            self._sanity.for_hosts(_host.boot_server))

    def launch_on_some_hosts(self, hosts):
        _host = host.Host(self._sanity)
        servers = []
        for hostname in hosts:
            servers.append(_host.boot_server(hostname))
        self._sanity.wait_for_servers(servers)

    def launch_on_one_host(self, hostname):
        _host = host.Host(self._sanity)
        servers = [_host.boot_server(hostname)]
        self._sanity.wait_for_servers(servers)

    def launch_on_hosts_missing_servers(self):
        launched_on = set()

        for server in self.servers():
            launched_on.add(getattr(server, 'OS-EXT-SRV-ATTR:host'))

        servers = []
        _host = host.Host(self._sanity)
        for hostname in self.hosts():
            if hostname in launched_on:
                continue
            servers.append(_host.boot_server(hostname))
        self._sanity.wait_for_servers(servers)

    @util.listify
    def hosts(self):
        for _host in self._sanity.list_hosts():
            yield _host.host

    def servers(self, **kwargs):
        return self._sanity.list_servers(**kwargs)

    def all_servers(self, **kwargs):
        return self._sanity.list_servers(name_startswith=None,
                                         all_tenants=True, **kwargs)

    def terminate_errored_servers(self):
        self._sanity.for_servers_errored(compute.Compute.delete)

    def stop(self):
        try:
            LOG.info("Shutting Down old style Span-Clients")
            self._sanity.wait_for_servers(
                [server.delete() or server
                 for server in self._sanity.list_servers(
                    name_startswith='Span-Client-')])
        except:
            LOG.error("Failed waiting for old style Span-Clients to shutdown")
        try:
            LOG.info("Shutting Down Servers")
            self._sanity.wait_for_servers(
                self._sanity.for_servers(
                    compute.Compute.delete))
        except:
            raise Exception("Failed waiting for servers to shutdown")
        try:
            self._sanity.tearDown()
        except Exception:
            LOG.exception("Error cleaning up")

    def run_baseline(self, servers=[]):
        self.test_boot(servers)
        self.test_console(servers)
        self.test_vncconsole(servers)
        self.test_floatingip(servers)

    def test_boot(self, servers=[]):
        return runner.Runner(
            CONF.keystone.auth_url,
            CONF.keystone.tenant_name,
            CONF.keystone.username,
            CONF.keystone.password,
            CONF.keystone.endpoint_type,
            state=self._sanity.get_state(),
            tests=[scenarios.BootScenario]).run(self._sanity, servers)

    def test_console(self, servers=[]):
        return runner.Runner(
            CONF.keystone.auth_url,
            CONF.keystone.tenant_name,
            CONF.keystone.username,
            CONF.keystone.password,
            CONF.keystone.endpoint_type,
            state=self._sanity.get_state(),
            tests=[scenarios.ConsoleScenario]).run(self._sanity, servers)

    def test_vncconsole(self, servers=[]):
        return runner.Runner(
            CONF.keystone.auth_url,
            CONF.keystone.tenant_name,
            CONF.keystone.username,
            CONF.keystone.password,
            CONF.keystone.endpoint_type,
            state=self._sanity.get_state(),
            tests=[scenarios.VNCConsoleScenario]).run(self._sanity, servers)

    def test_floatingip(self, servers=[]):
        return runner.Runner(
            CONF.keystone.auth_url,
            CONF.keystone.tenant_name,
            CONF.keystone.username,
            CONF.keystone.password,
            CONF.keystone.endpoint_type,
            state=self._sanity.get_state(),
            tests=[scenarios.FloatScenario]).run(self._sanity, servers)

    def print_servers(self, servers=None, with_name=False):
        columns = ['Host ID', 'Server ID']
        if with_name:
            columns.append('Name')
        columns.extend(['State', 'Task State', 'VM State',
                        'Created', 'Updated'])
        pt = PrettyTable(columns)
        pt.align = 'l'

        servers_by_host = defaultdict(list)

        for server in servers or self.servers():
            hostname = getattr(server, 'OS-EXT-SRV-ATTR:host',
                               server.metadata.get('host_id', 'UNKNOWN'))
            servers_by_host[hostname].append(server)
        for _host, servers in sorted(servers_by_host.items()):
            for server in servers:
                created = humanize.naturaltime(
                    datetime.utcnow() - parse_timestamp(server.created))
                updated = humanize.naturaltime(
                    datetime.utcnow() - parse_timestamp(server.updated))
                row = [_host, server.id]
                if with_name:
                    row.append(server.name)
                row.extend([server.status,
                            getattr(server, 'OS-EXT-STS:task_state'),
                            getattr(server, 'OS-EXT-STS:vm_state'),
                            created,
                            updated])
                pt.add_row(row)
        print(pt)

    def print_results(self):
        result_table, missing_hosts = self._sanity.report_results()
        print(result_table)
        print("Untested hosts:")
        for _host in host_lists.compress(missing_hosts):
            print("   ", _host)

    def print_failures(self, verbose=False):
        failures = self._sanity.report_failures()
        for test, results in failures.items():
            if not results:
                continue
            print_heading(test or "UNKNOWN")
            if verbose:
                pt = PrettyTable(['Host ID', 'Server ID',
                                  'Reason', 'Traceback'])
                pt.align = 'l'
                for _host, server, result in results:
                    pt.add_row((_host, server,
                                result.reason, result.traceback))
            else:
                pt = PrettyTable(['Host ID', 'Server ID',
                                  'Reason', 'Exception'])
                pt.align = 'l'
                for _host, server, result in results:
                    pt.add_row((_host, server, result.reason,
                                result.exception))
            print(pt)

    def print_errors(self):
        failures = self._sanity.report_errors()
        for test, results in failures.items():
            if not results:
                continue
            print_heading(test or "UNKNOWN")
            pt = PrettyTable(['Host ID', 'Server ID', 'Traceback'])
            pt.align = 'l'
            for _host, server, result in results:
                pt.add_row((_host, server, result.traceback))
            print(pt)

    def print_aggregates(self, all_hosts=False):
        pt = self._sanity.report_aggregates(all_hosts)
        print(pt)

    def identity(self, obj):
        return obj


def main_shell(user_ns):
    try:
        from IPython import embed
        from IPython.config.loader import Config
    except ImportError:
        print("ERROR: The shell dosen't work on CCS RHEL "
              "hosts since IPython (EPEL) is missing.")
        return
    auth_url = user_ns['OS_AUTH_URL']
    cloud_name = urlparse(auth_url).netloc.split('.', 1)[0]
    cfg = Config()
    cfg.PromptManager.in_template = '%s <\\#>: ' % cloud_name

    embed(config=cfg,
          user_ns=user_ns,
          banner1=('\n# Connected to %s' % auth_url) + INTRODUCTION)


class ChildThread(object):
    _stopped = False

    def stop(self):
        self._stopped = True

    @property
    def is_stopped(self):
        return self._stopped

    _finished = False

    def finish(self):
        self._finished = True

    @property
    def is_finished(self):
        return self._finished


class ThreadedBooter(ChildThread):

    def __init__(self, in_queue, out_queue, insanity, launch_wait=10):
        super(ThreadedBooter, self).__init__()
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.insanity = insanity
        self.launch_wait = launch_wait

    def list_services(self):
        return {service.host: service
                for service in self.insanity.state.nova.services.list()
                if service.binary == 'nova-compute'}

    def __call__(self):
        _host = host.Host(self.insanity)
        _services = self.list_services()
        while not self.in_queue.empty():
            if self.is_stopped:
                break

            try:
                hostname = self.in_queue.get_nowait()
            except Queue.Empty:
                break

            # No service exists
            service = _services.get(hostname)
            if not service:
                unbootable_server = scenarios.UnbootableServer(
                    **{'OS-EXT-SRV-ATTR:host': hostname,
                       'metadata': {'host_id': hostname},
                       'name': hostname,
                       'status': "no nova service exists on %s"
                       % hostname})
                self.out_queue.put(unbootable_server)
                continue

            # Nova service state is bad
            unbootable_server = scenarios.UnbootableServer(
                **{'OS-EXT-SRV-ATTR:host': service.host,
                   'metadata': {'host_id': hostname},
                   'name': hostname})
            if service.state != 'up':
                unbootable_server.status = ("nova service state is %s on %s"
                                            % (service.state, hostname))
                self.out_queue.put(unbootable_server)
                continue
            if not CONF.filter_enabled and service.status != 'enabled':
                unbootable_server.status = ("nova service status is %s on %s"
                                            % (service.status, hostname))
                self.out_queue.put(unbootable_server)
                continue

            try:
                server = _host.boot_server(hostname)
                LOG.info("Sent server boot request")
            except Exception:
                LOG.exception("Failed to boot server")
                # Try again later in the queue
                self.in_queue.put(hostname)
            else:
                self.out_queue.put(server)

            self.in_queue.task_done()
            time.sleep(self.launch_wait)
        LOG.info("Finished booting servers.")


class ThreadedLister(ChildThread):

    def __init__(self, in_queue, out_queue, insanity, launch_wait):
        super(ThreadedLister, self).__init__()
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.insanity = insanity
        self.servers = {server.metadata['host_id']: server
                        for server in insanity.list_servers()}

    def __call__(self):
        while not self.in_queue.empty():
            if self.is_stopped:
                break

            try:
                hostname = self.in_queue.get_nowait()
            except Queue.Empty:
                time.sleep(0.1)
                continue
            if hostname in self.servers:
                self.out_queue.put(self.servers[hostname])
            else:
                LOG.warning("Can't find server for %s", hostname)
            self.in_queue.task_done()
        LOG.info("Found servers.")


class BaseRunner(ChildThread):
    _failed_fixtures = None

    def __init__(self):
        super(BaseRunner, self).__init__()

    @property
    def compromised(self):
        if self._failed_fixtures:
            return True
        return False


class Tester(BaseRunner):

    def __init__(self, in_queue, out_queue, insanity):
        super(Tester, self).__init__()
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.no_delete_failed = CONF.action.no_delete_failed
        self.no_delete = CONF.action.no_delete
        self.insanity = insanity
        self.test_runner = runner.Runner(
            CONF.keystone.auth_url,
            CONF.keystone.tenant_name,
            CONF.keystone.username,
            CONF.keystone.password,
            CONF.keystone.endpoint_type,
            state=insanity.get_state(),
            tests=scenarios.get_enabled_tests(CONF.action.test))

    def initialize(self):
        self._failed_fixtures = self.test_runner.setUpFixtures()

    def test_server(self, server):
        if scenarios.has_booted(server):
            LOG.info('Waiting for %s to finish booting' % server.id)
            try:
                self.insanity.wait_for_servers([server])
                LOG.info('Booted %s' % server.id)
            except:
                LOG.exception("Timed out waiting for server %s to boot"
                              % server.id)

        self.test_runner.run_server(self.insanity, server)
        LOG.info("Ran tests for server %s" % server.id)

    def delete_server(self, server):
        if self.no_delete or not scenarios.has_booted(server):
            pass
        elif not self.no_delete_failed:
            LOG.info('Deleting %s' % server.id)
            server.delete()
        elif not self.insanity.has_failed_tests(server):
            LOG.info('Deleting %s' % server.id)
            server.delete()

    def __call__(self):
        while not (self.is_finished and self.in_queue.empty()):
            try:
                server = self.in_queue.get_nowait()
            except Queue.Empty:
                LOG.debug('Awaiting more servers to test')
                time.sleep(0.1)
                continue

            if self.is_stopped:
                try:
                    server.delete()
                except Exception:
                    LOG.exception("Failed while trying to delete server %s"
                                  % server.id)
                finally:
                    self.in_queue.task_done()
                    break

            try:
                self.test_server(server)
            except Exception:
                LOG.exception("Failed to run tests for server %s"
                              % server.id)

            try:
                self.delete_server(server)
            except Exception:
                LOG.exception("Failed while trying to delete server %s"
                              % server.id)

            self.out_queue.put(server)
            self.in_queue.task_done()

        self.test_runner.cleanup()
        LOG.info("Finished testing servers.")


class Fixturer(BaseRunner):

    def __init__(self, in_queue, out_queue, insanity):
        super(Fixturer, self).__init__()
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.insanity = insanity
        state = insanity.state
        self.keystone = state.keystone
        self.nova = state.nova
        self.neutron = state.neutron
        self.glance = state.glance

    def initialize(self):
        pass

    def try_apply_fixture(self, Fixture, server):
        fixture = Fixture(self.keystone, self.nova,
                          self.neutron, self.glance,
                          self.insanity.get_state())

        result = fixture.setUp()
        if result.is_failure():
            LOG.error('Failed to create %s', fixture.shortname)
            LOG.error(result.traceback)
        else:
            result = fixture.enableFixture(server)
            if result.is_failure():
                LOG.error('Failed to add %s to %s',
                          fixture.shortname, server.id)
                LOG.error(result.reason)

    def __call__(self):
        while True:
            try:
                server = self.in_queue.get_nowait()
            except Queue.Empty:
                if self.is_finished:
                    LOG.info('Finish triggered, exiting')
                    break
                time.sleep(0.1)
                continue

            if self.is_stopped:
                server.delete()
                break

            LOG.info('Waiting for %s to finish booting' % server.id)
            if scenarios.has_booted(server):
                try:
                    self.insanity.wait_for_servers([server])
                    LOG.info('Booted %s' % server.id)
                except:
                    LOG.exception("Timed out waiting for server to boot.")
                _server = self.nova.servers.get(server)
                for Fixture in fixtures.get_enabled_fixtures(
                        CONF.action.with_fixture):
                    self.try_apply_fixture(Fixture, _server)

            else:
                LOG.error(server.status)

            self.out_queue.put(server)
            self.in_queue.task_done()

        LOG.info("Finished booting servers.")


class MainBase(object):
    Controller = None

    def __init__(self):
        self.sig_inted_at = datetime.utcnow()
        self.thread_controllers = []
        self.threads = []
        self.start_time = datetime.utcnow()

    def __call__(self, user_ns):
        self.user_ns = user_ns
        from datetime import datetime
        start = user_ns['start']
        insanity = user_ns['insanity']
        host_list = CONF.action.host
        if CONF.action.host_file:
            with open(CONF.action.host_file) as f:
                host_list += [s.strip() for s in f.readlines()]
        if getattr(CONF.action, 'no_boot', False):
            self.ServerSource = ThreadedLister
        else:
            self.ServerSource = ThreadedBooter
        self.host_list = self.expand_hosts(host_list)
        self.start_time = datetime.utcnow()

        if not self.host_list:
            LOG.info("No hosts matched. Nothing to do.")
            return

        if getattr(CONF.action, 'show_plan', False):
            return self.print_plan()

        self.pre_start(**user_ns)
        start()
        self.post_start(**user_ns)

        signal.signal(signal.SIGTERM, self.sig_term)
        signal.signal(signal.SIGINT, self.sig_int)

        hosts_queue = Queue.Queue()
        for h in self.host_list:
            hosts_queue.put(h)
        server_queue_kw = {}
        if hasattr(CONF.action, 'max_servers'):
            server_queue_kw['maxsize'] = CONF.action.max_servers
        servers_queue = Queue.Queue(**server_queue_kw)
        completed = Queue.Queue()

        controller = \
            self.ServerSource(hosts_queue, servers_queue, insanity,
                              launch_wait=CONF.action.launch_wait)
        self.thread_controllers.append(controller)
        thread = threading.Thread(target=controller)
        thread.setName('%s-1' % self.ServerSource.__name__)
        thread.daemon = True
        self.threads.append(thread)

        test_controllers = []
        for i in range(1, CONF.action.threads + 1)[:len(self.host_list)]:
            controller = self.Controller(servers_queue, completed, insanity)
            controller.initialize()
            test_controllers.append(controller)

        # Use only properly initialized controllers, if none, then just use
        # them all.
        def controller_filter(controller):
            return not controller.compromised

        test_controllers = (
            filter(controller_filter, test_controllers) or
            test_controllers)

        LOG.info("Using %s testing threads.", len(test_controllers))
        self.thread_controllers.extend(test_controllers)

        for i, controller in enumerate(self.thread_controllers):
            thread = threading.Thread(target=controller)
            thread.setName('%s-%s' % (controller.__class__.__name__, str(i)))
            thread.daemon = True
            self.threads.append(thread)

        # Start all threads
        for thread in self.threads:
            thread.start()

        self.start_tests = datetime.utcnow()
        completed_servers = []
        while threading.active_count() > 1:
            # Check if all the servers are booted, if they are then
            # tell the testing threads to stop once they finish
            # testing.
            all_booted = True
            for thread in threading.enumerate():
                if thread.getName().startswith('ThreadedBooter-') \
                   or thread.getName().startswith('ThreadedLister-'):
                    if thread.is_alive():
                        all_booted = False
            if all_booted:
                for controller in self.thread_controllers:
                    controller.finish()

            time.sleep(0.1)

            try:
                completed_servers.append(completed.get_nowait())
                if len(completed_servers) % 5 == 0:
                    self.print_eta(completed_servers)
            except Queue.Empty:
                pass

        self.pre_clean(**user_ns)
        if not getattr(CONF.action, 'no_delete', False):
            self.clean([server for server in completed_servers
                        if scenarios.has_booted(server)])
        self.post_clean(**user_ns)

    def pre_start(self, **kwargs):
        print('Started at: %s' % self.start_time)

    def post_start(self, **kwargs):
        pass

    def pre_clean(self, **kwargs):
        pass

    def clean(self, servers):
        pass

    def post_clean(self, **kwargs):
        finished_time = datetime.utcnow()

        print('\nTotal Run Time: %s'
              % (finished_time - self.start_time))

    def sig_term(self, signum, frame):
        print("SIGTERM handler.  Shutting Down.")
        sys.exit()

    def sig_int(self, signum, frame):
        if (datetime.utcnow() - self.sig_inted_at) < timedelta(seconds=3):
            print("Stopping all threads. Shutting down.")
            for controller in self.thread_controllers:
                controller.stop()
        else:
            self.sig_inted_at = datetime.utcnow()
            self.print_all()
            print("SIGINT handler. Press Ctrl-C again within "
                  "3 seconds to exit.")

    def expand_hosts(self, hosts):
        valid_hosts = self.user_ns['hosts']()
        if hosts:
            hosts_to_test = []
            # Match qualified and unqualified hostnames, but always return
            # the qualified version.
            valid_hosts_map = {_host: _host for _host in valid_hosts}
            valid_hosts_map.update({
                _host.split('.', 1)[0]: _host for _host in valid_hosts})
            for _host in hosts:
                for canonical_host in set(host_lists.expand(_host)):
                    host_with_fqdn = valid_hosts_map.get(canonical_host)
                    if host_with_fqdn:
                        hosts_to_test.append(host_with_fqdn)
                    else:
                        hosts_to_test.append(canonical_host)
        else:
            hosts_to_test = valid_hosts
        return hosts_to_test

    def _eta(self, completed_hosts, remaining_hosts):
        if remaining_hosts:
            return (((datetime.utcnow() - self.start_time) /
                     completed_hosts) *
                    remaining_hosts)

    def print_eta(self, completed_hosts):
        remaining_hosts = len(self.host_list) - len(completed_hosts)
        completed_hosts = len(completed_hosts)
        LOG.info('CHECKPOINT: Processed %s hosts in %s.'
                 '  %s Remaining hosts, ETA %s',
                 completed_hosts,
                 (datetime.utcnow() - self.start_time),
                 remaining_hosts,
                 self._eta(completed_hosts,
                           remaining_hosts))

    def print_plan(self):
        print_heading("Test plan")
        print("Hosts to test:")
        for _host in host_lists.compress(self.host_list):
            print("   ", _host)
        print()
        print("Tests to run:")
        for test in scenarios.get_enabled_tests():
            print("   ", test.name)


class MainTest(MainBase):
    Controller = Tester

    def pre_start(self, stop, **kwargs):
        if CONF.action.no_boot:
            CONF.action.no_initial_clean = True
            CONF.action.no_delete = True
        if CONF.action.no_initial_clean:
            return
        try:
            stop()
        except:
            pass

    def pre_clean(self, **kwargs):
        self.print_all()
        if CONF.action.write_retry:
            self.write_retry_file('sanity.retry')

        if CONF.action.output_json:
            self.dump_json_report(CONF.action.output_json)

    def print_all(self):
        print_results = self.user_ns['print_results']
        print_failures = self.user_ns['print_failures']
        print_errors = self.user_ns['print_errors']
        print_aggregates = self.user_ns['print_aggregates']

        # print all results
        print('\nErrors')
        print('========')
        print_errors()

        print('\nFailures')
        print('========')
        print_failures()

        print('\n\nAggregates')
        print('=======')
        print_aggregates()

        print('\n\nResults')
        print('=======')
        print_results()

    def dump_json_report(self, filename):
        insanity = self.user_ns['insanity']

        results = {}
        for test in insanity._test_results:
            results[test] = []
            for key, result in insanity._test_results[test].items():
                host, server = key
                results[test].append((host, server, result.to_dict()))

        with open(filename, 'w') as outfile:
            json.dump(results, outfile)

    def write_retry_file(self, filename):
        insanity = self.user_ns['insanity']
        failures = insanity.report_failures()
        failed_hosts = set()
        for test, results in failures.items():
            for _host, server, result in results:
                failed_hosts.add(_host)
        if failed_hosts:
            with open(filename, 'w') as outfile:
                for _host in sorted(failed_hosts):
                    outfile.write('{}\n'.format(_host))
            LOG.info('Wrote retry file to %s.', filename)
            LOG.info('Re-test failed hosts with `--host-file %s`.', filename)

    def clean(self, servers):
        insanity = self.user_ns['insanity']
        if CONF.action.no_delete_failed or CONF.action.no_delete:
            return
        # Wait for any servers to delete
        LOG.info('Waiting for servers to delete.')
        try:
            insanity.wait_for_servers(servers)
        except:
            try:
                insanity.wait_for_servers(servers)
            except:
                LOG.exception("Timed out waiting for servers.")

        try:
            insanity.tearDown()
        except:
            LOG.info('Stop failed. Retrying')
            try:
                insanity.tearDown()
            except:
                LOG.exception("Failed during tearDown")


class MainBoot(MainBase):
    Controller = Fixturer

    def pre_clean(self, insanity, **kwargs):
        pt = PrettyTable(['Host ID', 'Server ID', 'State',
                          'Task State', 'VM State', 'Created',
                          'Updated', 'IP Addresses'])
        pt.align = 'l'
        for server in insanity.list_servers():
            hostname = getattr(server, 'OS-EXT-SRV-ATTR:host',
                               server.metadata.get('host_id', 'UNKNOWN'))
            created = humanize.naturaltime(
                datetime.utcnow() - parse_timestamp(server.created))
            updated = humanize.naturaltime(
                datetime.utcnow() - parse_timestamp(server.updated))
            ip_addresses = ', '.join([port['addr']
                                      for address in server.addresses.values()
                                      for port in address])
            row = [hostname,
                   server.id,
                   server.status,
                   getattr(server, 'OS-EXT-STS:task_state'),
                   getattr(server, 'OS-EXT-STS:vm_state'),
                   created,
                   updated,
                   ip_addresses]
            pt.add_row(row)
        print(str(pt))

        if CONF.action.output_json:
            self.dump_json_report(CONF.action.output_json)
        if CONF.action.output_ip:
            self.dump_floating_ips(CONF.action.output_ip)

    def dump_json_report(self, filename):
        insanity = self.user_ns['insanity']

        results = {}
        for server in insanity.list_servers():
            hostname = getattr(server, 'OS-EXT-SRV-ATTR:host',
                               server.metadata.get('host_id', 'UNKNOWN'))
            ip_addresses = ', '.join([port['addr']
                                      for address in server.addresses.values()
                                      for port in address])
            results[hostname] = {}
            results[hostname]['ip_addresses'] = ip_addresses

        with open(filename, 'w') as outfile:
            json.dump(results, outfile)

    def dump_floating_ips(self, filename):
        insanity = self.user_ns['insanity']

        ips = []
        for server in insanity.list_servers():
            print(server.addresses.values())
            ip_addresses = ''.join([port['addr']
                                    for address in server.addresses.values()
                                    for port in address
                                    if port['OS-EXT-IPS:type'] == 'floating'])
            if ip_addresses:
                ips.append(ip_addresses)

        with open(filename, 'w') as outfile:
            outfile.write('\n'.join(ips))


def main_stop(user_ns):
    stop = user_ns['stop']
    # Cleanup
    try:
        stop()
    except:
        print('Stop failed. Retrying')
        try:
            stop()
        except:
            pass


def main_host_list(user_ns):
    hosts = user_ns['hosts']
    for _host in host_lists.compress(hosts()):
        print(_host)


def main_exec(user_ns):
    execfile(CONF.action.file, globals(), user_ns)


def add_parsers(subparsers):
    shell = subparsers.add_parser(
        'shell', help='Interactive sanity shell.')
    shell.set_defaults(func=main_shell)

    test = subparsers.add_parser(
        'test', help='Run automated tests on some hosts.')
    test.add_argument('-w', '--host', action='append', default=[])
    test.add_argument(
        '--host-file',
        help='A file containing a list of hosts to test.')
    test.add_argument(
        '--threads', action='store', default=10, type=int,
        help='How many threads to run.')
    test.add_argument(
        '--max-servers', action='store', default=30, type=int,
        help='The maximum number of servers to have running at any one time.')
    test.add_argument(
        '--launch-wait', action='store', default=5, type=int,
        help='The time to wait between booting servers.')
    test.add_argument(
        '--no-initial-clean', action='store_true',
        help="Don't clean up anything before starting.")
    test.add_argument(
        '--no-boot', action='store_true',
        help="Don't boot servers, test existing ones only. "
        "Implies no-initial-clean and no-delete")
    test.add_argument(
        '--no-delete', action='store_true',
        help="Don't delete servers after testing.")
    test.add_argument(
        '--no-delete-failed', action='store_true',
        help="Don't delete servers that fail tests.")
    test.add_argument(
        '--external-test-ip', action='store', default='8.8.8.8',
        help="The IP address used to confirm "
        "that we have outgoing connectivity.")
    test.add_argument(
        '--test', action='append',
        default=[],
        choices=scenarios.TESTS.keys(),
        help="The tests to run.")
    test.add_argument(
        '--output-json', action='store',
        help="The location of the file to print the JSON report to.")
    test.add_argument(
        '--write-retry', action='store_true',
        help="The the failed nodes to a file for re-running.")
    test.add_argument(
        '--show-plan', action='store_true',
        help="Don't do anything, just show what would happen.")
    test.set_defaults(func=MainTest())

    host_list = subparsers.add_parser(
        'host-list', help='List the hosts available for testing.')
    host_list.set_defaults(func=main_host_list)

    stop = subparsers.add_parser(
        'stop', help='Stop all running sanity hosts and cleanup.')
    stop.set_defaults(func=main_stop)

    script = subparsers.add_parser(
        'script', help='Run a script.')
    script.add_argument(
        '--file', required=True,
        help="The file with the script to run.")
    script.set_defaults(func=main_exec)

    boot = subparsers.add_parser(
        'boot', help=('Boot a bunch of instances'))
    boot.add_argument('-w', '--host', action='append', default=[])
    boot.add_argument(
        '--host-file',
        help='A file containing a list of hosts to boot on.')
    boot.add_argument(
        '--threads', action='store', default=10, type=int,
        help='How many threads to run.')
    boot.add_argument(
        '--launch-wait', action='store', default=10, type=int,
        help='The time to wait between booting servers.')
    boot.add_argument(
        '--output-json', action='store',
        help="The location of the file to print the JSON report to.")
    boot.add_argument(
        '--with-fixture', action='append',
        default=[],
        choices=fixtures.FIXTURES.keys(),
        help="A list of the fixtures to add to the servers.")
    boot.add_argument(
        '--output-ip', action='store',
        help="The location of the file to print the floating IP report to.")
    boot.set_defaults(func=MainBoot())


def main():
    logging.getLogger('sanity').setLevel(logging.INFO)
    logging.basicConfig(format=LOG_FORMAT, level=logging.WARNING)

    try:
        main1()
    except Exception:
        LOG.exception("Unhandled Error")
        sys.exit(1)


def main1():
    CONF.register_cli_opt(cfg.SubCommandOpt('action', handler=add_parsers))
    CONF()

    log_level = logging.WARNING
    if CONF.verbose is True:
        log_level = logging.INFO
    if CONF.debug is True:
        log_level = logging.DEBUG
    logging.root.setLevel(log_level)

    if CONF.log_file is not None:
        file_log = logging.FileHandler(CONF.log_file)
        file_log.setFormatter(logging.Formatter(LOG_FORMAT))
        logging.root.addHandler(file_log)

    if not CONF.keystone.auth_url:
        LOG.error('You must provide a keystone auth'
                  ' url via env[OS_AUTH_URL]')
        sys.exit(1)
    if not CONF.keystone.tenant_name:
        LOG.error('You must provide a tenant name'
                  ' via env[OS_TENANT_NAME]')
        sys.exit(1)
    if not CONF.keystone.username:
        LOG.error('You must provide a username'
                  ' or user id via env[OS_USERNAME]')
        sys.exit(1)
    if not CONF.keystone.password:
        LOG.error('You must provide a password'
                  ' via env[OS_PASSWORD]')
        sys.exit(1)

    user_ns = {}
    auth_url = user_ns['OS_AUTH_URL'] = CONF.keystone.auth_url
    password = user_ns['OS_PASSWORD'] = CONF.keystone.password
    tenant = user_ns['OS_TENANT_NAME'] = CONF.keystone.tenant_name
    username = user_ns['OS_USERNAME'] = CONF.keystone.username
    endpoint_type = user_ns['OS_ENDPOINT_TYPE'] = CONF.keystone.endpoint_type
    clientmanager = user_ns['clientmanager'] = os_sdk.create_connection(
        auth_url, tenant, username, password, endpoint_type=endpoint_type)
    keystone = user_ns['keystone'] = clientmanager.identity
    nova = user_ns['nova'] = no_client.Client(
        '2', session=clientmanager.session)
    neutron = user_ns['neutron'] = clientmanager.network
    glance = user_ns['glance'] = clientmanager.image
    state = user_ns['state'] = SanityState(
        keystone, nova, glance, neutron,
        # Trim out the OSLO elements
        **{k: v for k, v in CONF.iteritems()
           if not isinstance(v, (cfg.ConfigOpts.SubCommandAttr,
                                 cfg.ConfigOpts.GroupAttr))})
    sanity = user_ns['insanity'] = SanityController(state)
    simple = user_ns['simple'] = SimpleSanity(sanity)

    # All the simple sanity functions should be local
    for k in dir(simple):
        if k.startswith('_'):
            continue
        user_ns[k] = getattr(simple, k)

    # Add for each function
    user_ns['compute'] = compute.Compute(nova)
    user_ns['network'] = network.Network(neutron, sanity)
    user_ns['host'] = host.Host(sanity)

    # Add for_ functions into user space
    for k in dir(sanity):
        if k.startswith('for_'):
            user_ns[k] = getattr(sanity, k)

    # Add wait_ functions into user space
    for k in dir(sanity):
        if k.startswith('wait_'):
            user_ns[k] = getattr(sanity, k)
    CONF.action.func(user_ns)
