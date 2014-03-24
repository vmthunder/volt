# -*- coding: utf-8 -*-

# Copyright 2010-2011 OpenStack Foundation
# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


from oslo.config import cfg
from stevedore import driver

from volt.openstack.common.gettextutils import _

EXECUTOR_NAMESPACE = 'volt.executor'

executor_opts = [
    cfg.StrOpt('default_executor', default='btree',
               help=_('The default volume tracker algorithm executor.')
    ),
]

CONF = cfg.CONF
CONF.register_opts(executor_opts)


def get_default_executor():
    executor = driver.DriverManager(
        EXECUTOR_NAMESPACE, CONF.default_executor,
        invoke_on_load=True
    )
    return executor.driver


class Executor(object):
    """ The Base class of Executor
    """
    def __init__(self):
        pass

    def get_volumes_list(self):
        raise NotImplementedError()

    def get_volumes_detail(self, volume_id):
        raise NotImplementedError()

    def add_volume_metadata(self, volume_id, **kwargs):
        raise NotImplementedError()

    def delete_volume_metadata(self, peer_id, **kwargs):
        raise NotImplementedError()

    def get_volume_parents(self, volume_id, peer_id):
        raise NotImplementedError()
