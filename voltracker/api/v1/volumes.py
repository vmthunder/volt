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

from webob.exc import HTTPBadRequest
from webob.exc import HTTPForbidden
from webob.exc import HTTPConflict
from webob.exc import HTTPNotFound
from webob import Response
import eventlet

from voltracker.common import policy
from voltracker.common import exception
from voltracker import executor
from voltracker.common import wsgi
from voltracker.openstack.common import log as logging

SUPPORTED_PARAMS = ('host', 'port', 'iqn', 'lun')

LOG = logging.getLogger(__name__)


class Controller(object):
    """
    WSGI controller for tracked volumes information in Voltracker v1 API

    The tracked volumes API is a RESTful web service for volume
    metadata. The API is as follows::

        GET /volumes -- Returns a set of brief metadata about volumes
        HEAD /volumes/<ID> -- Returns detailed metadata about volumes
                            with id <ID>
        GET /volumes/qurey/<ID> -- Search volumes metadata about volumes
                             matching the id <ID>. Because the client
                             uses this result to build the iscsi
                             connections, in order to promote overall
                             r/w performance and limit the number of
                             connections, executor always returns
                             partial matching list.
        POST /volumes/<ID> -- Register a new volume and store metadata
                             with id <ID>
        DELETE /volumes/<ID> -- Delete all tracked volume with id <ID>
        DELETE /volumes -- Delete all tracked volumes
    """

    def __init__(self):
        self.policy = policy.Enforcer()
        self.pool = eventlet.GreenPool(size=1024)
        self.executor = executor.get_default_executor()

    def _enforce(self, req, action):
        """Authorize an action against our policies"""
        try:
            self.policy.enforce(req.context, action, {})
        except exception.Forbidden:
            raise HTTPForbidden()

    def _get_query_params(self, req):
        """
        Extracts necessary query params from request.

        :param req: the WSGI Request object
        :retval dict of parameters that can be used by registry client
        """
        params = {}
        for PARAM in SUPPORTED_PARAMS:
            if PARAM in req.params:
                params[PARAM] = req.params.get(PARAM)

        return params

    def index(self, req):
        """
        Returns the following information for all tracked volumes:

            * id -- The opaque volume identifier
            * count -- The number of registered volumes with this id

        :param req: The WSGI/Webob Request object
        :retval The response body is a mapping of the following form::

            {'volumes': [
                {'id': <ID>,
                 'count': <COUNT>}, ...
            ]}
        """
        self._enforce(req, 'get_volumes')

        try:
            volumes = self.executor.get_volumes_list()
        except exception.Invalid as e:
            raise HTTPBadRequest(explanation="%s" % e)

        return dict(volumes=volumes)

    def remove(self, req, peer_id):
        """
        Remove the volume metadata from Voltracker

        :param req: The WSGI/Webob Request object
        :param peer_id: The opaque volume identifier allocated by
                        voltracker.

        :raises HttpNotFound if volume is not available
        """
        self._enforce(req, 'remove_volume')

        params = self._get_query_params(req)
        try:
            self.executor.delete_volume_metadata(peer_id, params)
        except exception.NotFound as e:
            msg = _("Failed to find volume to delete: %(e)s") % {'e': e}
            for line in msg.split('\n'):
                LOG.info(line)
            raise HTTPNotFound(explanation=msg,
                               request=req,
                               content_type="text/plain")
        else:
            return Response(body='', status=200)

    def register(self, req, volume_id):
        """
        Adds the volume metadata to the registry and assigns
        an volume identifier if one is not supplied in the request
        headers.

        :param req: The WSGI/Webob Request object
        :param volume_meta: The volume metadata

        :raises HTTPConflict if volume already exists
        :raises HTTPBadRequest if volume metadata is not valid
        """
        self._enforce(req, 'register_volume')

        params = self._get_query_params(req)
        try:
            volume_meta = self.executor.add_volume_metadata(volume_id,
                                                            params)
        except exception.Duplicate:
            msg = (_("An volume with identifier %s already exists") %
                   volume_meta['id'])
            LOG.debug(msg)
            raise HTTPConflict(explanation=msg,
                               request=req,
                               content_type="text/plain")
        except exception.Invalid as e:
            msg = _("Failed to register volume. Got error: %(e)s") % {'e': e}
            for line in msg.split('\n'):
                LOG.debug(line)
            raise HTTPBadRequest(explanation=msg,
                                 request=req,
                                 content_type="text/plain")

        return {'volume_meta': volume_meta}

    def query(self, req, volume_id):
        """
        Returns detailed information for all available volumes with id
        <volume_id>

        :param req: The WSGI/Webob Request object
        :param id: The volume id of the query
        :retval The response body is a mapping of the following form::

            {'volumes': [
                {'host': <HOST>,
                 'ip': <IP>,
                 'iqn': <IQN>,
                 'lun': <LUN>}, ...
            ]}

        """
        self._enforce(req, 'get_volumes')

        volumes = self.executor.get_volumes_detail(volume_id)
        return dict(volumes=volumes)


def create_resource():
    """Volumes resource factory method"""
    return wsgi.Resource(Controller())
