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

import pytest

from sanity import results


@pytest.mark.parametrize(
    'class_name',
    ['Result', 'Success', 'Failure', 'Error', 'Skipped']
)
def test_result_type_has_duration(class_name):
    result = getattr(results, class_name)()
    assert 'duration' in result.to_dict()
