# Copyright 2012 OpenStack Foundation.
# Copyright 2013 NTT corp.
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

from webob.exc import HTTPNotFound
from webob.exc import HTTPForbidden

from volt.common import policy
from volt.common import exception
from volt.common import wsgi
from volt.openstack.common import log as logging
from volt.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)


class Controller(object):

    def __init__(self):
        self.policy = policy.Enforcer()

    def _enforce(self, req, action):
        """Authorize an action against our policies"""
        try:
            self.policy.enforce(req.context, action, {})
        except exception.Forbidden:
            raise HTTPForbidden()

    def heartbeat(self, req):
        """
        Client send periodical heartbeat to Volt server.

        :param req: the Request object coming from the wsgi layer

        """
        self._enforce(req, 'heartbeat')

        try:
            result = self.executor.update_status(req.context)
        except exception.NotFound:
            msg = _("Image with identifier %s not found") % image_id
            LOG.debug(msg)
            raise HTTPNotFound(msg)
        return status


def create_resource():
    """volt members resource factory method"""
    return wsgi.Resource(Controller())
