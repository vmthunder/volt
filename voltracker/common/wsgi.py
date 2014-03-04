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

import os

import eventlet
from paste import deploy
from oslo.config import cfg

from voltracker.common import exception
from voltracker.openstack.common import log as logging


# Raise the default from 8192 to accommodate large tokens
eventlet.wsgi.MAX_HEADER_LINE = 16384

wsgi_opts = [
    cfg.StrOpt('api_paste_config',
               default="api-paste.ini",
               help='File name for the paste.deploy config for nova-api'),
    cfg.StrOpt('wsgi_log_format',
            default='%(client_ip)s "%(request_line)s" status: %(status_code)s'
                    ' len: %(body_length)s time: %(wall_seconds).7f',
            help='A python format string that is used as the template to '
                 'generate log lines. The following values can be formatted '
                 'into it: client_ip, date_time, request_line, status_code, '
                 'body_length, wall_seconds.'),
    cfg.StrOpt('ssl_ca_file',
               help="CA certificate file to use to verify "
                    "connecting clients"),
    cfg.StrOpt('ssl_cert_file',
                    help="SSL certificate of API server"),
    cfg.StrOpt('ssl_key_file',
                    help="SSL private key of API server"),
    cfg.IntOpt('tcp_keepidle',
               default=600,
               help="Sets the value of TCP_KEEPIDLE in seconds for each "
                    "server socket. Not supported on OS X."),
]

CONF = cfg.CONF
CONF.register_opts(wsgi_opts)

LOG = logging.getLogger(__name__)


class Loader(object):
    """Used to load WSGI applications from paste configurations."""

    def __init__(self, config_path=None):
        """Initialize the loader, and attempt to find the config.

        :param config_path: Full or relative path to the paste config.
        :returns: None

        """
        config_path = config_path or CONF.api_paste_config
        if os.path.exists(config_path):
            self.config_path = config_path
        else:
            self.config_path = CONF.find_file(config_path)
        if not self.config_path:
            raise exception.ConfigNotFound(path=config_path)

    def load_app(self, name):
        """Return the paste URLMap wrapped WSGI application.

        :param name: Name of the application to load.
        :returns: Paste URLMap object wrapping the requested application.
        :raises: `nova.exception.PasteAppNotFound`

        """
        try:
            LOG.debug(_("Loading app %(name)s from %(path)s") %
                      {'name': name, 'path': self.config_path})
            return deploy.loadapp("config:%s" % self.config_path, name=name)
        except LookupError as err:
            LOG.error(err)
            raise exception.PasteAppNotFound(name=name, path=self.config_path)
