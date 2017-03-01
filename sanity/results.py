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


from datetime import timedelta
import traceback

import six


class Result(object):
    duration = timedelta(seconds=0)
    _is_failure = False

    def is_failure(self):
        return self._is_failure

    def to_dict(self):
        return {
            'result': self.__class__.__name__,
            'duration': self.duration.seconds,
        }


class Success(Result):
    pass


class Failure(Result):
    _is_failure = True
    exception = None
    traceback = None

    def __init__(self, reason="", exception=None, *args, **kwargs):
        self.reason = reason
        for k, v in kwargs.items():
            setattr(self, k, v)
        if isinstance(exception, six.string_types):
            self.exception = exception
        elif exception:
            self.exception = '%s: %s' % (type(exception), exception)
            self.traceback = traceback.format_exc()

    def __str__(self):
        if self.duration:
            seconds = self.duration.seconds
            return 'FAILURE {:02}:{:02}'.format(
                seconds % 3600 // 60, seconds % 60)
        else:
            return 'FAILURE'

    def to_dict(self):
        return {
            'result': self.__class__.__name__,
            'duration': self.duration.seconds,
            'reason': self.reason,
            'exception': self.exception,
            'traceback': self.traceback
        }


class Error(Failure):

    def __init__(self, *args, **kwargs):
        super(Error, self).__init__(*args, **kwargs)
        self.traceback = traceback.format_exc()

    def __str__(self):
        if self.duration:
            seconds = self.duration.seconds
            return 'ERROR {:02}:{:02}'.format(
                seconds % 3600 // 60, seconds % 60)
        else:
            return 'ERROR'

    def to_dict(self):
        return {
            'result': self.__class__.__name__,
            'duration': self.duration.seconds,
            'reason': self.reason,
            'traceback': self.traceback
        }


class Skipped(Result):
    def __str__(self):
        return "SKIPPED"
