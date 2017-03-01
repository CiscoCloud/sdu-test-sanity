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

from openstack.image.v1 import image
from openstack.network.v2 import security_group
from openstack.network.v2 import security_group_rule

from sanity import controller


class TestSanityState(TestCase):

    def setUp(self):

        self.keystone = mock.Mock()
        self.nova = mock.Mock()
        self.glance = mock.Mock()
        self.neutron = mock.Mock()
        self.controller = controller.SanityState(
            self.keystone, self.nova, self.glance, self.neutron)

    @mock.patch('sanity.controller.time')
    def test_create_security_group(self, time):

        time.time.return_value = '1234'
        existing_security_groups = []
        self.neutron.security_groups.return_value = \
            existing_security_groups

        sg = {'description': '',
              'id': '79c3952c-3d27-425b-bc9e-cde7892f9c42',
              'name': 'qaspansecg-1234',
              'security_group_rules': [],
              'tenant_id': 'fc394f2ab2df4114bde39905f800dc57'}

        self.neutron.create_security_group.return_value = \
            security_group.SecurityGroup(sg)
        self.neutron.get_security_group.return_value = \
            security_group.SecurityGroup(sg)
        secgroup = self.controller.security_group
        self.neutron.create_security_group.assert_called_with(
            name='qaspansecg-1234')
        self.assertEqual(secgroup['id'],
                         '79c3952c-3d27-425b-bc9e-cde7892f9c42')
        self.assertEqual(secgroup['name'],
                         'qaspansecg-1234')

    @mock.patch('sanity.controller.time')
    def test_reuse_security_group(self, time):

        time.time.return_value = '1234'
        existing_sgr = [
            {'description': '',
             'id': '79p3952p',
             'name': 'unused-group',
             'security_group_rules': [],
             'tenant_id': 'fc394f2ab2df4114bde39905f800dc57'},
            {'description': '',
             'id': '79c3952c-3d27-425b-bc9e-cde7892f9c42',
             'name': 'qaspansecg-1234',
             'security_group_rules': [],
             'tenant_id': 'fc394f2ab2df4114bde39905f800dc57'}]

        self.neutron.security_groups.return_value = \
            (security_group_rule.SecurityGroupRule(e_sgr)
             for e_sgr in existing_sgr)

        secgroup = self.controller.security_group
        self.assertEqual(self.neutron.create_security_group.call_count, 0)
        self.assertEqual(secgroup['id'],
                         '79c3952c-3d27-425b-bc9e-cde7892f9c42')
        self.assertEqual(secgroup['name'],
                         'qaspansecg-1234')


class UnitTestSanityState(TestCase):

    def setUp(self):
        self.keystone = mock.Mock()
        self.nova = mock.Mock()
        self.glance = mock.Mock()
        self.neutron = mock.Mock()

        self.controller = controller.SanityState(
            self.keystone, self.nova, self.glance, self.neutron)

    def test_get_glance_image(self):

        image_list = [{'name': 'RHEL-7-DE5253'},
                      {'name': 'RHEL-6'},
                      {'name': 'Fedora-20'},
                      {'name': 'RHEL-7'}]

        self.glance.images.return_value = \
            (image.Image(i) for i in image_list)

        self.assertEqual(self.controller.image,
                         {'name': 'RHEL-7'})

    def test_get_glance_centos_image(self):

        image_list = [{'name': 'RHEL-7-DE5253'},
                      {'name': 'CentOS-3'},
                      {'name': 'Fedora-20'},
                      {'name': 'CentOS-7'}]

        self.glance.images.return_value = \
            (image.Image(i) for i in image_list)

        self.assertEqual(self.controller.image,
                         {'name': 'CentOS-7'})

    def test_get_glance_no_image(self):

        image_list = [{'name': 'RHEL-7-DE5253'},
                      {'name': 'RHEL-6-my_image'},
                      {'name': 'Fedora-20'},
                      {'name': 'Centos-7-old'}]

        self.glance.images.return_value = \
            (image.Image(i) for i in image_list)

        with self.assertRaises(self.controller.ImageNotFound):
            self.controller.image
