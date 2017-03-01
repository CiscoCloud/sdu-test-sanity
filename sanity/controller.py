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

import operator
from os import path
import re
import time
import random
import string
import logging
from collections import defaultdict

from passlib.hash import sha512_crypt
from prettytable import PrettyTable
from novaclient import exceptions as n_exceptions
from openstack import exceptions as os_exceptions
from oslo_config import cfg

from sanity.host import gethostid
from sanity.util import listify
from sanity.results import Success, Failure, Error
from sanity import scenarios


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

USER_DATA = """#cloud-config

users:
  - default
  - name: sanity
    lock-passwd: false
    sudo: ALL=(ALL) NOPASSWD:ALL
    passwd: %s

disable_root: false
ssh_pwauth: true


"""

opts = [
    cfg.StrOpt('availability-zone', default=None,
               help="The name of the availability zone to use."),
    cfg.StrOpt('keypair-name', default='qaspankey',
               help="The name of the keypair to use."),
    cfg.StrOpt('security-group-name', default='qaspansecg-{0}',
               help="The name of the security group to use."),
    cfg.StrOpt('router-name', default='qa-span-test-router',
               help="The name of the router to use."),
    cfg.StrOpt('network-name', default='qa-span-network',
               help="The name of the network to use."),
    cfg.StrOpt('subnet-name', default='qa-span-subnet',
               help="The name of the subnet to use."),
    cfg.StrOpt('subnet-cidr', default='192.168.50.0/24',
               help="The CIDR of the subnet."),
    cfg.IPOpt('subnet-gateway', default='192.168.50.1',
              help="The IP of the gateway the subnet should use."),
    cfg.StrOpt('external-net-re', default='^public-floating',
               help="The RegExp used to find the"
               " network to use for external connectivity."),
    cfg.StrOpt('image-name-re',
               default='^([cC]ent[oO][sS]-[0-9\.]+|RHEL-[0-9\.]+)$',
               help="The RegExp used to find the image to use."),
    cfg.ListOpt('flavors', default='Micro-Small,GP-Small',
                help="The list of flavors to try and launch with."),
    cfg.StrOpt('public-key', default='~/.ssh/id_rsa.pub',
               help="The public key to use when connecting to hosts."),
    cfg.BoolOpt('filter-enabled', default=True,
                help='Only list hosts with an enabled Nova compute.'),
    cfg.BoolOpt('floating', default=True,
                help="Don't test using floating networks."),
    cfg.IntOpt('build-timeout', default=60,
               help="Maximum time to wait for a server to become ACTIVE."),
]

CONF.register_opts(opts)
CONF.register_cli_opts(opts)


class ImageNotFound(Exception):
    pass


def random_string(length):
    return ''.join([random.choice(string.ascii_letters + string.digits)
                    for _ in range(length)])


def list_servers(client, all_tenants=False, limit=None, **kwargs):
    servers = []
    marker = None
    opts = {}
    if limit:
        opts['limit'] = limit
    if all_tenants:
        opts["all_tenants"] = True
    opts.update(kwargs)

    while True:
        if marker:
            opts["marker"] = marker

        result = client.servers.list(search_opts=opts)

        if not result:
            break

        servers.extend(result)

        if len(servers) > limit:
            return servers

        marker = servers[-1].id
    return servers


class SanityState(object):
    ImageNotFound = ImageNotFound
    _public_key = '~/.ssh/id_rsa.pub'

    _ignored_availability_zones = set(['internal', 'nova'])
    _availability_zone = None
    __availability_zone = None

    _keypair_name = 'qaspankey'
    __keypair = {}

    _security_group_name = 'qaspansecg-{0}'
    __security_group = {}

    _router_name = 'qa-span-test-router'
    __router = {}

    _external_test_ip = '8.8.8.8'

    _subnet_gateway = '192.168.50.1'
    _subnet_name = 'qa-span-subnet'
    _subnet_cidr = '192.168.50.0/24'

    _network_name = 'qa-span-network'
    __network = {}

    _external_net_re = r'^public-floating'
    __external_net = {}

    __image = {}

    _flavors = ['Micro-Small', 'GP-Small']
    __flavor = {}

    __router_ok = False

    def __init__(self, keystone, nova, glance, neutron, **kwargs):
        self.keystone = keystone
        self.nova = nova
        self.glance = glance
        self.neutron = neutron

        self._image_name_re = CONF.image_name_re

        for key, value in kwargs.items():
            if hasattr(self, '_' + key):
                setattr(self, '_' + key, value)

    def setUp(self):
        self.flavor
        self.availability_zone
        self.image
        self.keypair

        self.security_group
        self.create_security_group_rules()

        self.external_net
        if CONF.floating:
            self.router
        self.network
        if CONF.floating:
            self.check_router_ports()

    def tearDown(self):
        LOG.info("Deleting Keypair")
        self.clean_keypair()

        if CONF.floating:
            LOG.info("Deleting Subnet")
            self.clean_subnet()
            LOG.info("Deleting Router")
            self.clean_router()
            LOG.info("Deleting Network")
            self.clean_network()
            LOG.info("Deleting Unused floating IPs")
            self.clean_floatingip()

        self.clean_security_group()

    #
    # Flavor
    #
    def update_flavor(self, *name_or_id):
        self.__flavor = self._get_flavor(*name_or_id)
        self._flavor = name_or_id
        LOG.info("Using flavor %s", self.__flavor.name)
        self.__flavor = self.__flavor.id

    def _get_flavor(self, *name_or_ids):
        for name_or_id in name_or_ids:
            for flavor in self.nova.flavors.list():
                if flavor.id == name_or_id:
                    return flavor
                if flavor.name == name_or_id:
                    return flavor
        raise Exception("Can't find valid flavor.")

    @property
    def flavor(self):
        if not self.__flavor:
            self.update_flavor(*self._flavors)
        return self.__flavor

    #
    # External Net
    #
    def update_external_net(self, name_re):
        self.__external_net = self._get_external_net(name_re)
        LOG.info("Using External Net %s", self.__external_net['name'])
        self._external_net_re = name_re

    def _get_external_net(self, name_re):
        filter = {}
        if CONF.floating:
            filter['router:external'] = True

        for net in self.neutron.networks(**filter):
            if re.match(name_re, net['name']):
                return net
        raise Exception("Can't find valid external network to use.")

    @property
    def external_net(self):
        if not self.__external_net:
            self.update_external_net(self._external_net_re)
        return self.__external_net

    #
    # Image
    #
    def update_image(self, name_re):
        self.__image = self._get_image(name_re)
        LOG.info("Using Image %s", self.__image.name)
        self._image_name_re = name_re

    def _get_image(self, name_re):
        for image in sorted(
                self.glance.images(
                    visibility='public',
                    status='ACTIVE'),
                key=operator.attrgetter('name'),
                reverse=True):
            if re.match(name_re, image.name):
                return image
        raise ImageNotFound("Can't find valid image to use.")

    @property
    def image(self):
        if not self.__image:
            self.update_image(self._image_name_re)
        return self.__image

    #
    # Availability Zone
    #

    def update_availability_zone(self, name=None):
        availability_zone = self._get_availability_zone(name)
        LOG.info("Using Availability Zone %s", availability_zone.zoneName)
        self.__availability_zone = availability_zone.zoneName

    def _get_availability_zone(self, name=None):
        for zone in self.nova.availability_zones.list():
            if zone.zoneName == name or self._availability_zone:
                return zone
            if zone.zoneName in self._ignored_availability_zones:
                continue
            if zone.zoneState.get('available'):
                return zone
        raise Exception("Can't find valid zone to use.")

    @property
    def availability_zone(self):
        if not self.__availability_zone:
            self.update_availability_zone()
        return self.__availability_zone

    #
    # Keypair
    #
    def update_keypair(self, name):
        self.__keypair = self._get_keypair(name)
        if not self.__keypair:
            LOG.info("Creating keypair %s", self._keypair_name)
            self.__keypair = self.create_keypair(name)
        else:
            LOG.info("Using keypair %s", self.__keypair.name)
        self._keypair_name = name

    def create_keypair(self, name):
        key_path = path.abspath(path.expanduser(self._public_key))
        return self.nova.keypairs.create(
            name,
            public_key=open(key_path).read())

    def _get_keypair(self, name):
        try:
            return self.nova.keypairs.get(name)
        except n_exceptions.NotFound:
            return None

    def clean_keypair(self):
        keypair = self.__keypair
        if keypair:
            keypair.delete()

        keypair = self._get_keypair(self._keypair_name)
        if keypair:
            keypair.delete()
        self.__keypair = {}

    @property
    def keypair(self):
        if not self.__keypair:
            self.update_keypair(self._keypair_name)
        return self.__keypair

    #
    # Security Group
    #
    def update_security_group(self, name):
        self.__security_group = self._get_security_group(name)
        if not self.__security_group:
            name = name.format(int(time.time()))
            LOG.info("Creating Security Group %s", name)
            self.__security_group = self.create_security_group(name)
        else:
            LOG.info("Using Security Group %s", self.__security_group['id'])
        self._security_group_name = name

    def create_security_group(self, name):
        group = self.neutron.create_security_group(name=name)
        return self.neutron.get_security_group(group['id'])

    def create_security_group_rules(self):
        # Ping
        try:
            self.neutron.create_security_group_rule(
                **{'direction': 'ingress',
                   'security_group_id': self.security_group['id'],
                   'protocol': 'icmp'})
        except os_exceptions.HttpException as e:
            if e.message.lower() != 'conflict':
                raise

        # SSH
        try:
            self.neutron.create_security_group_rule(
                **{'direction': 'ingress',
                   'security_group_id': self.security_group['id'],
                   'port_range_min': 22,
                   'port_range_max': 22,
                   'protocol': 'tcp',
                   'ethertype': 'IPv4',
                   'remote_ip_prefix': '0.0.0.0/0'})
        except os_exceptions.HttpException as e:
            if e.message.lower() != 'conflict':
                raise

    def _get_security_group(self, name):
        groups = self.neutron.security_groups(
            tenant_id=self.keystone.session.get_project_id())
        re_name = re.compile(name.format('.*'))
        for group in groups:
            if re_name.match(group['name']):
                return group

    def clean_security_group(self):
        group = self.__security_group
        if group:
            LOG.info("Deleting Security Group %s (%s)",
                     group['name'], group['id'])
            self.neutron.delete_security_group(group['id'])
        else:
            group = self._get_security_group(self._security_group_name)
            if group:
                LOG.info("Deleting Security Group %s (%s)",
                         group['name'], group['id'])
                self.neutron.delete_security_group(group['id'])
        self.__security_group = {}

    @property
    def security_group(self):
        if not self.__security_group:
            self.update_security_group(self._security_group_name)
        return self.__security_group

    #
    # Router
    #
    def update_router(self, name):
        self.__router = self._get_router(name)
        if not self.__router:
            LOG.info("Creating router %s", self._router_name)
            self.__router = self.create_router(name)
        else:
            LOG.info("Using router %s", self.__router['id'])
        self._router_name = name

    def create_router(self, name):
        router = self.neutron.create_router(name=name)
        return router

    def attach_router_gateway(self, router):
        LOG.info("Attaching external net gateway to router")
        self.neutron.update_router(
            router,
            **{'external_gateway_info':
               {'network_id': self.external_net['id']}})

    def _get_router(self, name):
        routers = list(self.neutron.routers(
            tenant_id=self.keystone.session.get_project_id(),
            name=name))
        if len(routers) < 1:
            None
        elif len(routers) > 1:
            LOG.info("Too many routers to choose from")
            for router in routers:
                LOG.info(router['id'])
        else:
            return routers[0]

    def clean_router(self):
        router = self.__router
        if router:
            self.neutron.update_router(
                router,
                **{'external_gateway_info': {}})
            self.neutron.delete_router(router['id'])

        router = self._get_router(self._router_name)
        if router:
            self.neutron.update_router(
                router,
                **{'external_gateway_info': {}})
            self.neutron.delete_router(router['id'])
        self.__router = {}

    @property
    def router(self):
        if not self.__router:
            self.update_router(self._router_name)
        return self.__router

    def check_router_ports(self):
        if self.__router_ok is True:
            return
        # check router interface
        ports = list(self.neutron.ports(
            device_id=self.router['id'],
            network_id=self.network['id']))
        if not ports:
            self.attach_network_gateway(self.router)

        # check router gateway
        ports = list(self.neutron.ports(
            device_id=self.router['id'],
            network_id=self.external_net['id']))
        if not ports:
            self.attach_router_gateway(self.router)
        self.__router_ok = True

    #
    # Network
    #
    def update_network(self, name):
        self.__network = self._get_network(name)
        if not self.__network:
            LOG.info("Creating network %s", self._network_name)
            self.__network = self.create_network(name)
            self.create_subnet(self.__network, self.__router)
        else:
            LOG.info("Using network %s", self.__network['id'])
        self._network_name = name

    def create_network(self, name):
        return self.neutron.create_network(name=name)

    def _get_network(self, name):
        networks = list(self.neutron.networks(
            tenant_id=self.keystone.session.get_project_id(),
            name=name))
        if len(networks) < 1:
            return None
        elif len(networks) > 1:
            LOG.info("Too many networks to choose from")
            for network in networks:
                LOG.info(network['id'])
        else:
            return networks[0]

    def clean_network(self):
        network = self.__network
        if network:
            self.neutron.delete_network(network['id'])

        network = self._get_network(self._network_name)
        if network:
            self.neutron.delete_network(network['id'])
        self.__network = {}

    @property
    def network(self):
        if CONF.floating:
            if not self.__network:
                self.update_network(self._network_name)
            return self.__network
        else:
            return self.external_net

    #
    # Subnet
    #
    def create_subnet(self, network, router):
        subnet = self.neutron.create_subnet(
            **{'name': self._subnet_name,
               'network_id': network['id'],
               'enable_dhcp': True,
               'ip_version': '4',
               'cidr': self._subnet_cidr,
               'gateway_ip': self._subnet_gateway})
        self.neutron.add_interface_to_router(router, subnet['id'])
        return subnet

    def attach_network_gateway(self, router, subnet=None):
        if not subnet:
            subnet = self.get_subnet()
        LOG.info("Attaching router interface to network")
        self.neutron.add_interface_to_router(router, subnet['id'])

    def get_subnet(self):
        subnets = list(self.neutron.subnets(
            tenant_id=self.keystone.session.get_project_id(),
            name=self._subnet_name))
        if len(subnets) < 1:
            LOG.info("Can't find subnet %s", self._subnet_name)
        elif len(subnets) > 1:
            LOG.info("Too many subnets to choose from")
            for subnet in subnets:
                LOG.info(subnet['id'])
        else:
            return subnets[0]

    def clean_subnet(self):
        subnet = self.get_subnet()
        if not subnet:
            network = self._get_network(self._network_name)
            if not network:
                return
            for _subnet in network['subnets']:
                subnet = self.neutron.get_subnet(_subnet)['subnet']
        if not subnet:
            return

        # TODO this should only remove the interface if no other ports
        # are currently used by servers.
        router = self.__router or self._get_router(self._router_name)
        if router:
            try:
                self.neutron.remove_interface_from_router(
                    router, subnet['id'])
            except os_exceptions.NotFoundException:
                pass

        try:
            self.neutron.delete_subnet(subnet['id'])
        except os_exceptions.HttpException as e:
            if e.message.lower() == 'conflict':
                LOG.info("Stale ports found.")
                for port in self.neutron.ports(
                        tenant_id=self.keystone.session.get_project_id(),
                        network_id=subnet['network_id']):
                    LOG.info("Delete port %s", port['id'])
                    self.neutron.delete_port(port['id'])
                self.neutron.delete_subnet(subnet['id'])

    #
    # Floating IP
    #
    def clean_floatingip(self):
        floatingips = self.neutron.ips(
            tenant_id=self.keystone.session.get_project_id())
        for ip in floatingips:
            if ip['port_id'] is None:
                LOG.info('Deleting floating IP %s', ip['id'])
                self.neutron.delete_ip(ip['id'])

    def to_dict(self):
        state = {
            'flavor': self.flavor,
            'availability_zone': self.availability_zone,
            'image': self.image.to_dict(),
            'keypair': self.keypair,
            'security_group': self.security_group.to_dict(),
            'external_test_ip': self._external_test_ip,
            'external_net': self.external_net.to_dict(),
            'network': self.network.to_dict(),
        }

        if CONF.floating:
            state['router'] = self.router.to_dict()
            self.check_router_ports()

        return state


class SanityController(object):
    _services = None
    _test_results = {}

    def __init__(self, state):
        self.state = state

    def setUp(self):
        self.state.setUp()

    def tearDown(self):
        self.state.tearDown()

    def add_test_result(self, test_name, host, server, result):
        if test_name not in self._test_results:
            self._test_results[test_name] = {}
        self._test_results[test_name][(host, server)] = result

    def get_test_result(self, test_name, host, server):
        if test_name not in self._test_results:
            self._test_results[test_name] = {}
        return self._test_results[test_name].get((host, server))

    def get_state(self):
        return self.state.to_dict()

    #
    # Hosts
    #
    def list_hosts(self):
        services = []
        for service in self.state.nova.services.list():
            if service.binary != 'nova-compute':
                continue
            services.append(service)
        self._services = sorted(services, key=operator.attrgetter('host'))
        return self._services

    @listify
    def for_hosts(self, fn, *args, **kwargs):
        for h in self.list_hosts():
            yield fn(h, *args, **kwargs)

    @listify
    def for_hosts_missing_servers(self, fn, *args, **kwargs):
        """Operate on all the Hosts that currently don't have a VM launched on them.

        """
        hosts = {gethostid(host): host for host in self.list_hosts()}
        for server in self.list_servers():
            host_id = server.metadata['host_id']
            if host_id in hosts:
                del hosts[host_id]
        hosts = sorted(hosts.values(), key=operator.attrgetter('host'))
        for h in hosts:
            yield fn(h, *args, **kwargs)

    @listify
    def for_hosts_with_servers(self, fn, *args, **kwargs):
        """Operate on all the Hosts that currently have a VM launched on them.

        """
        hosts = {gethostid(host): host for host in self.list_hosts()}
        for server in self.list_servers():
            host_id = server.metadata['host_id']
            if host_id not in hosts:
                del hosts[host_id]
        hosts = sorted(hosts.values(), key=operator.attrgetter('host'))
        for h in hosts:
            yield fn(h, *args, **kwargs)

    #
    # Servers
    #
    def boot_server_on_host(self, host):
        password = random_string(8)
        hashed_password = sha512_crypt.encrypt(password)
        return self.state.nova.servers.create(
            name="Sanity-%s" % gethostid(host).split('.', 1)[0],
            image=self.state.image.id,
            flavor=self.state.flavor,
            key_name=self.state.keypair.name,
            nics=[{'net-id': self.state.network['id']}],
            meta={'host_id': gethostid(host),
                  'user_name': 'sanity',
                  'user_password': password},
            security_groups=[self.state.security_group['name']],
            availability_zone=':'.join([self.state.availability_zone,
                                        gethostid(host)]),
            userdata=USER_DATA % hashed_password)

    @listify
    def list_servers(self, name_startswith='Sanity-', **kwargs):
        for server in list_servers(self.state.nova, **kwargs):
            if name_startswith and not server.name.startswith(name_startswith):
                continue
            yield server

    @listify
    def for_servers(self, fn, *args, **kwargs):
        for server in self.list_servers():
            yield fn(server, *args, **kwargs)

    @listify
    def for_servers_failed(self, testname, fn, *args, **kwargs):
        servers = {server.id: server for server in self.list_servers()}
        for host_and_server, result in self._test_results[testname].items():
            host, server = host_and_server
            if server in servers and issubclass(result.__class__, Failure):
                yield fn(servers[server], *args, **kwargs)

    @listify
    def for_servers_passed(self, testname, fn, *args, **kwargs):
        servers = {server.id: server for server in self.list_servers()}
        for host_and_server, result in self._test_results[testname].items():
            host, server = host_and_server
            if server in servers and issubclass(result.__class__, Success):
                yield fn(servers[server], *args, **kwargs)

    @listify
    def for_servers_active(self, fn, *args, **kwargs):
        for server in self.list_servers():
            if not server.status == 'ACTIVE':
                continue
            yield fn(server, *args, **kwargs)

    @listify
    def for_servers_errored(self, fn, *args, **kwargs):
        for server in self.list_servers():
            if server.status == 'ERROR':
                yield fn(server, *args, **kwargs)

    @listify
    def for_servers_building(self, fn, *args, **kwargs):
        for server in self.list_servers():
            if server.status == 'BUILD':
                yield fn(server, *args, **kwargs)

    def has_failed_tests(self, server):
        servers = {
            host_and_server[1]: host_and_server
            for testname in self._test_results.keys()
            for host_and_server, result in self._test_results[testname].items()
            if issubclass(result.__class__, Failure)}
        if server.id in servers:
            return True
        return False

    @listify
    def wait_for_servers(self, servers,
                         states=('ACTIVE', 'ERROR'),
                         timeout=None):
        """Wait for servers to end up in one of the specified states.

        """
        if timeout is None:
            timeout = CONF.build_timeout
        count = timeout
        finished = False
        uuids = set([server.id for server in servers])
        if not uuids:
            return []
        while count > 0:
            # If there are no servers then return
            server_list = self.list_servers()
            if not server_list:
                return []

            for server in server_list:
                if server.id not in uuids:
                    continue
                if server.status not in states:
                    finished = False
                    break
                if getattr(server, 'OS-EXT-STS:task_state'):
                    # Break if a VM isn't in a stable state
                    finished = False
                    break
                finished = True
            count -= 1
            if finished is True:
                return servers
            time.sleep(1)
        raise Exception("Timed out waiting for servers.")

    def report_results(self):
        test_combinations = set()
        for results in self._test_results.values():
            test_combinations = test_combinations.union(set(results.keys()))
        test_combinations = sorted(list(test_combinations))

        tests = []
        for ordered_test in [scenarios.BootScenario.name,
                             scenarios.ConsoleScenario.name,
                             scenarios.VNCConsoleScenario.name,
                             scenarios.FloatScenario.name]:
            if ordered_test in self._test_results.keys():
                tests.append(ordered_test)
        tests = tests + [test for test in self._test_results.keys()
                         if test not in tests]

        pt = PrettyTable(['Host ID', 'Server ID'] + tests)
        pt.align = 'l'
        missing_hosts = set(service.host for service in self.list_hosts())

        for host, server in test_combinations:
            if host in missing_hosts:
                missing_hosts.remove(host)
            row = [host, server]
            for test in tests:
                row.append(str(self.get_test_result(test, host, server)))
            pt.add_row(row)
        return pt, missing_hosts

    def report_failures(self):
        failures = {}
        for test in self._test_results:
            failures[test] = []
            for key, result in self._test_results[test].items():
                if not issubclass(result.__class__, Failure):
                    continue
                host, server = key
                failures[test].append((host, server, result))
        return failures

    def report_errors(self):
        errors = {}
        for test in self._test_results:
            errors[test] = []
            for key, result in self._test_results[test].items():
                if not issubclass(result.__class__, Error):
                    continue
                host, server = key
                errors[test].append((host, server, result))
        return errors

    def report_aggregates(self, all_hosts=False):
        if all_hosts:
            hosts = [host.host for host in self.list_hosts()]
        else:
            hosts = set()
            for results in self._test_results.values():
                hosts = hosts.union(set(results.keys()))
            hosts = sorted(list(hosts))
            hosts = set(host for host, server in hosts)
        pt = PrettyTable(['Host ID', 'Aggregates'])
        pt.align = 'l'
        aggregates = defaultdict(list)
        for agg in self.state.nova.aggregates.list():
            for host in agg.hosts:
                aggregates[host].append(agg.name)

        for host in sorted(hosts):
            pt.add_row([host, ','.join(aggregates.get(host, []))])
        return pt
