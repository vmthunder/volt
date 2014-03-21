#!/usr/bin/env python

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 OpenStack Foundation
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

"""
Volt API Server
"""

import sys

import eventlet
from oslo.config import cfg

# Monkey patch socket, time, select, threads
eventlet.patcher.monkey_patch(all=False, socket=True, time=True,
                              select=True, thread=True)

from volt.common import wsgi
from volt.common import version
from volt.openstack.common import log as logging

CONF = cfg.CONF

def main():
    CONF(sys.argv[1:], project='volt',
         version=version.version_string())
    logging.setup('volt')

    # Use the wsgi service to serve the request from client
    server = wsgi.Server('volt-api')
    server.start(CONF.bind_port)
    server.wait()
