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

import openstack.profile
import openstack.connection
import openstack.session
from positional import positional
from keystoneauth1 import exceptions
from keystoneauth1.identity.generic.password import Password as BasePassword
from oslo_config import cfg


CONF = cfg.CONF


class Password(BasePassword):
    @positional()
    def get_discovery(self, session, url, authenticated=None):
        raise exceptions.DiscoveryFailure()


class Session(openstack.session.Session):
    def request(self, *args, **kwargs):
        kwargs.setdefault('connect_retries', 5)
        return super(Session, self).request(*args, **kwargs)


def create_connection(auth_url, project_name, username, password,
                      endpoint_type='publicURL',
                      user_domain_id='default',
                      project_domain_id='default',
                      verify=True,
                      cert=None,
                      identity_version=None):
    profile = openstack.profile.Profile()
    profile.set_interface(profile.ALL, endpoint_type)

    # This compute service override exists to support the new behaviour of the
    # endpoint discovery where it uses the discovery endpoint instead of the
    # service catalogue.
    profile._services['compute']['requires_project_id'] = True

    if not identity_version:
        identity_version = CONF.keystone.version
    if identity_version in '3' or 'v3' in auth_url:
        identity_version = 'v3'
    profile.set_version('identity', identity_version)

    if identity_version == 'v3':
        authenticator = Password(
            auth_url=auth_url,
            user_domain_id=user_domain_id,
            project_name=project_name,
            project_domain_id=project_domain_id,
            username=username,
            password=password)
    else:
        authenticator = Password(
            auth_url=auth_url,
            project_name=project_name,
            username=username,
            password=password)

    session = Session(
        profile,
        user_agent='Sanity',
        auth=authenticator,
        verify=verify,
        cert=cert)

    return openstack.connection.Connection(
        session=session,
        authenticator=authenticator,
        profile=profile)
