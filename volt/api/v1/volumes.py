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

from volt.common import policy
from volt.common import exception
from volt import executor
from volt.common import wsgi
from volt.openstack.common import log as logging
from volt.openstack.common.gettextutils import _
from volt.openstack.common import jsonutils

SUPPORTED_PARAMS = ('host', 'port', 'iqn', 'lun', 'peer_id')

LOG = logging.getLogger(__name__)



class Controller(object):
    """
    WSGI controller for tracked volumes information in Volt v1 API

    The tracked volumes API is a RESTful web service for volume
    metadata. The API is as follows::

        GET /volumes -- Returns a set of brief metadata about volumes
        HEAD /volumes/<ID> -- Returns detailed metadata about volumes
                            with id <ID>
        GET /volumes/<ID> -- Search volumes metadata about volumes
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
#         self.pool.spawn_n(self.executor.kickoff_dead_node())
        self.scanning_thread = executor.ScanningThread(self.executor)
        
        
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
            if req and PARAM in req:
                params[PARAM] = req.get(PARAM)

        return params

    def index(self, req, volume_id=None):
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
        #self._enforce(req, 'get_volumes')

        try:
            if volume_id is None:
                volumes = self.executor.get_volumes_list()
            else:
                volumes = self.executor.get_volumes_detail(volume_id)
        except exception.Invalid as e:
            raise HTTPBadRequest(explanation="%s" % e)

        return volumes

    def remove(self, req, volume_id, peer_id=None, body=None):
        """
        Remove the volume metadata from Volt

        :param req: The WSGI/Webob Request object
        :param volume_id: The volume identifier of the volume.
        :param peer_id: The opaque volume identifier allocated by
                        volt

        :raises HttpNotFound if volume is not available
        """
        #self._enforce(req, 'remove_volume')
        params = self._get_query_params(body)
        assert(peer_id is not None)
        try:
            self.executor.delete_volume_metadata(volume_id, peer_id, **params)
        except exception.NotFound as e:
            msg = _("Failed to find volume to delete: %(e)s") % {'e': e}
            for line in msg.split('\n'):
                LOG.info(line)
            raise HTTPNotFound(explanation=msg,
                               request=req,
                               content_type="text/plain")
        else:
            return Response(body='', status=200)

    def register(self, req, volume_id, peer_id, body=None):
        """
        Adds the volume metadata to the registry and assigns
        an volume identifier if one is not supplied in the request
        headers.

        :param req: The WSGI/Webob Request object
        :param volume_meta: The volume metadata

        :raises HTTPConflict if volume already exists
        :raises HTTPBadRequest if volume metadata is not valid
        """
        #self._enforce(req, 'register_volume')
        params = self._get_query_params(body)
        #if self.scanning_thread.status == 'init':
        #    self.scanning_thread.start()
        #    self.scanning_thread.status = 'running'
        try:
            volume_meta = self.executor.add_volume_metadata(volume_id,
                                                            peer_id, **params)
        except exception.DuplicateItem:
            msg = (_("An volume with identifier %s already exists") %
                   volume_id)
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
        except exception.NotFound as e:
            msg = _("Failed to register volume. Got error: %(e)s") % {'e': e}
            for line in msg.split('\n'):
                LOG.debug(line)
            raise HTTPNotFound(explanation=msg,
                               request=req,
                               content_type="text/plain")

        return volume_meta

    def query(self, req, volume_id, body=None):
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
        #self._enforce(req, 'get_volumes')
        params = self._get_query_params(body)
        #host = params.get('host', None)
        host = req.environ['REMOTE_ADDR']
        peer_id = params.get('peer_id', None)
        if self.scanning_thread.status == 'init':
            self.scanning_thread.start()
            self.scanning_thread.status = 'running'
        try:
            target = self.executor.get_volume_parents(volume_id=volume_id,
                                                      peer_id=peer_id,
                                                      host=host)
        except exception.NotFound as e:
            msg = _("this volume is not found in tracker.")
            raise HTTPNotFound(explanation=msg,
                               request=req,
                               content_type="text/plain")
        except exception.InvalidParameterValue:
            raise HTTPBadRequest()
        except exception.Duplicate:
            raise HTTPConflict()

        return target


def create_resource():
    """Volumes resource factory method"""
    return wsgi.Resource(Controller())
