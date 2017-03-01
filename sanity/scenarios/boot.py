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

from oslo_config import cfg

from sanity.scenarios import (Success, Failure,
                              SanityScenario, has_booted)

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class BootScenario(SanityScenario):
    name = 'Boot Check'
    shortname = 'boot'
    log = LOG

    def setUp(self):
        result = super(BootScenario, self).setUp()
        return result

    def _test_server(self, server):
        if not has_booted(server):
            return Failure(
                "Server didn't boot, %s" % server.status)

        if server.status == 'ACTIVE':
            return Success()
        if not getattr(server, 'OS-EXT-SRV-ATTR:host'):
            return Failure(
                "Stuck in %s state, never scheduled to host correctly."
                % server.status,
                exception=getattr(server, 'fault', {}).get('message', ''))
        return Failure(
            "Stuck in %s state." % server.status,
            exception=getattr(server, 'fault', {}).get('message', ''))
