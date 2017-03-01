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

import os
import time
import logging
import subprocess

from sanity.fixtures import Fixture, Error, Skipped, Failure

LOG = logging.getLogger(__name__)


def ping(host):
    with open(os.devnull, 'w') as DEVNULL:
        try:
            subprocess.check_call(
                ['ping', '-c', '1', str(host)],
                stdout=DEVNULL,
                stderr=DEVNULL
            )
            return True
        except subprocess.CalledProcessError:
            return False


class FloatingIPFixture(Fixture):
    """Add a floating IP to a server

    1. Associate a floating IP to a server
    2. Ping the server until it responds
    """
    log = LOG
    name = 'FloatingIP Fixture'
    shortname = 'floatingip'
    _floatingip = None
    ip_address = None

    def _setUp(self):
        if self._floatingip or self.result.is_failure():
            return self.result
        floating_network = self.state['external_net']
        try:
            self._floatingip = self.neutron.create_ip(
                **{'floating_network_id': floating_network['id']})
        except:
            self.result = Error()
            self.log.warning('Failed to create floating IP')
        else:
            self.ip_address = self._floatingip['floating_ip_address']
            self.log.info('Created floating ip: %s',
                          self._floatingip['floating_ip_address'])
        return self.result

    def _tearDown(self):
        # Handle the case where setup fails
        if not self._floatingip:
            return self.result

        self.log.info('Deleting floating ip: %s',
                      self._floatingip['floating_ip_address'])
        self.neutron.delete_ip(self._floatingip['id'])
        self._floatingip = None
        return self.result

    def get_floatingip(self, uuid=None):
        if not uuid:
            uuid = self._floatingip['id']
        return self.neutron.get_ip(uuid)

    def _enableFixture(self, server):
        if server.status != 'ACTIVE':
            return Skipped()
        result = self.result

        # Assign floatingip
        server.add_floating_ip(self.ip_address)

        # Wait for floating IP to come UP, only works in Icehouse or newer
        count = 0
        if 'status' in self.get_floatingip():
            while self.get_floatingip()['status'] == 'DOWN':
                count += 1
                sleep_for = count * 2
                self.log.debug("Server %s floating IP %s is DOWN, sleeping %s",
                               server.id, self.ip_address, sleep_for)
                time.sleep(sleep_for)
                if count > 8:
                    result = Failure(
                        'Failed waiting for Floating IP %s to associate.'
                        % self.ip_address)
                    break
        else:
            time.sleep(5)

        count = 0
        while not ping(self.ip_address):
            count += 1
            sleep_for = count * 2
            self.log.debug("Can't ping server %s on ip %s sleeping %s",
                           server.id, self.ip_address, sleep_for)
            time.sleep(sleep_for)
            if count > 8:
                result = Failure(
                    "Floating IP %s not replying to ping."
                    % self.ip_address)
                break
        return result

    def _disableFixture(self, server):
        if server.status != 'ACTIVE':
            return Skipped()
        result = self.result
        server.remove_floating_ip(self.ip_address)

        # Wait for floating IP to go down, only works in Icehouse or newer
        count = 0
        if 'status' in self.get_floatingip():
            while self.get_floatingip()['status'] != 'DOWN':
                count += 1
                sleep_for = count * 2
                self.log.debug("Disassociating floating IP, waiting for "
                               "state change from UP, sleeping %s", sleep_for)
                time.sleep(sleep_for)
                if count > 8:
                    result = Failure(
                        'Failed disassociate Floating IP %s.'
                        % self.ip_address)
                    break
        else:
            time.sleep(5)

        return result
