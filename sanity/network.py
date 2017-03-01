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


class Network(object):
    def __init__(self, client, sanity):
        self._client = client
        self._sanity = sanity

    def assign_server_floating_ip(self, server):
        assert self._sanity._external_net, \
            "Sanity not initialised. Please run start()"
        floatingip = self._client.create_ip(
            {'floating_network_id': self._sanity._external_net['id']})
        port = list(self._client.ports(
            device_id=server.id,
            network_id=self._sanity._network['id']))[0]
        self._client.update_ip(floatingip['id'], port_id=port['id'])
        return server

    def remove_server_floating_ip(self, server):
        assert self._sanity._external_net, \
            "Sanity not initialised. Please run start()"
        port = list(self._client.find_ports(
            device_id=server.id,
            network_id=self._sanity._network['id']))[0]
        floatingip = list(self._client.ips(
            port_id=port['id']))[0]
        self._client.delete_ip(floatingip['id'])
        return server
