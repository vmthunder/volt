# Copyright 2014 OpenStack Foundation
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


from volt.api.v1 import volumes
from volt.api.v1 import members
from volt.common import wsgi


class API(wsgi.Router):

    """WSGI router for Voltracker v1 API requests."""

    def __init__(self, mapper):
        volumes_resource = volumes.create_resource()

        mapper.connect("/volumes",
                       controller=volumes_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect("/volumes/{volume_id}",
                       controller=volumes_resource,
                       action='index',
                       conditions={'method': ['HEAD']})
        mapper.connect("/volumes/query/{volume_id}",
                       controller=volumes_resource,
                       action='query',
                       conditions={'method': ['GET']})
        mapper.connect("/volumes/{volume_id}/{peer_id}",
                       controller=volumes_resource,
                       action='register',
                       conditions={'method': ['POST']})
        mapper.connect("/volumes/{volume_id}/{peer_id}",
                       controller=volumes_resource,
                       action='remove',
                       conditions={'method': ['DELETE']})
        mapper.connect("/volumes/{volume_id}",
                       controller=volumes_resource,
                       action="remove",
                       conditions={'method': ['DELETE']})

        members_resource = members.create_resource()

        mapper.connect("/members/heartbeat",
                       controller=members_resource,
                       action="heartbeat",
                       conditions={'method': ['PUT']})

        super(API, self).__init__(mapper)
