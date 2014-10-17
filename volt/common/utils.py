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
import binascii

from webob import exc
from OpenSSL import crypto

from volt.common import exception
from volt.openstack.common import strutils
from volt.openstack.common.gettextutils import _


volume_META_HEADERS = [
    'x-volume-meta-host', 'x-volume-meta-port',
    'x-volume-meta-iqn', 'x-volume-meta-lun',
]

VOLT_TEST_SOCKET_FD_STR = 'VOLT_TEST_SOCKET_FD'


def get_volume_meta_from_headers(response):
    """
    Processes HTTP headers from a supplied response that
    match the x-volume-meta and x-volume-meta-property and
    returns a mapping of volume metadata and properties

    :param response: Response to process
    """
    result = {}
    properties = {}

    if hasattr(response, 'getheaders'):  # httplib.HTTPResponse
        headers = response.getheaders()
    else:  # webob.Response
        headers = response.headers.items()

    for key, value in headers:
        key = str(key.lower())
        if key.startswith('x-volume-meta-property-'):
            field_name = key[len('x-volume-meta-property-'):].replace('-', '_')
            properties[field_name] = value or None
        elif key.startswith('x-volume-meta-'):
            field_name = key[len('x-volume-meta-'):].replace('-', '_')
            if 'x-volume-meta-' + field_name not in volume_META_HEADERS:
                msg = _("Bad header: %(header_name)s") % {'header_name': key}
                raise exc.HTTPBadRequest(msg, content_type="text/plain")
            result[field_name] = value or None
    result['properties'] = properties

    for key in ('size', 'min_disk', 'min_ram'):
        if key in result:
            try:
                result[key] = int(result[key])
            except ValueError:
                extra = (_("Cannot convert volume %(key)s '%(value)s' "
                           "to an integer.")
                         % {'key': key, 'value': result[key]})
                raise exception.InvalidParameterValue(value=result[key],
                                                      param=key,
                                                      extra_msg=extra)
            if result[key] < 0:
                extra = (_("volume %(key)s must be >= 0 "
                           "('%(value)s' specified).")
                         % {'key': key, 'value': result[key]})
                raise exception.InvalidParameterValue(value=result[key],
                                                      param=key,
                                                      extra_msg=extra)

    for key in ('is_public', 'deleted', 'protected'):
        if key in result:
            result[key] = strutils.bool_from_string(result[key])
    return result


def volume_meta_to_http_headers(volume_meta):
    """
    Returns a set of volume metadata into a dict
    of HTTP headers that can be fed to either a Webob
    Request object or an httplib.HTTP(S)Connection object

    :param volume_meta: Mapping of volume metadata
    """
    headers = {}
    for k, v in volume_meta.items():
        if v is not None:
            if k == 'properties':
                for pk, pv in v.items():
                    if pv is not None:
                        headers["x-volume-meta-property-%s"
                                % pk.lower()] = unicode(pv)
            else:
                headers["x-volume-meta-%s" % k.lower()] = unicode(v)
    return headers

def validate_key_cert(key_file, cert_file):
    try:
        error_key_name = "private key"
        error_filename = key_file
        key_str = open(key_file, "r").read()
        key = crypto.load_privatekey(crypto.FILETYPE_PEM, key_str)

        error_key_name = "certficate"
        error_filename = cert_file
        cert_str = open(cert_file, "r").read()
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_str)
    except IOError as ioe:
        raise RuntimeError(_("There is a problem with your %(error_key_name)s "
                             "%(error_filename)s.  Please verify it."
                             "  Error: %(ioe)s") %
                           {'error_key_name': error_key_name,
                            'error_filename': error_filename,
                            'ioe': ioe})
    except crypto.Error as ce:
        raise RuntimeError(_("There is a problem with your %(error_key_name)s "
                             "%(error_filename)s.  Please verify it. OpenSSL"
                             " error: %(ce)s") %
                           {'error_key_name': error_key_name,
                            'error_filename': error_filename,
                            'ce': ce})

    try:
        data = str(uuid.uuid4())
        digest = "sha1"

        out = crypto.sign(key, data, digest)
        crypto.verify(cert, out, data, digest)
    except crypto.Error as ce:
        raise RuntimeError(_("There is a problem with your key pair.  "
                             "Please verify that cert %(cert_file)s and "
                             "key %(key_file)s belong together.  OpenSSL "
                             "error %(ce)s") % {'cert_file': cert_file,
                                                'key_file': key_file,
                                                'ce': ce})


def get_test_suite_socket():
    global VOLT_TEST_SOCKET_FD_STR
    if VOLT_TEST_SOCKET_FD_STR in os.environ:
        fd = int(os.environ[VOLT_TEST_SOCKET_FD_STR])
        sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        sock = socket.SocketType(_sock=sock)
        sock.listen(CONF.backlog)
        del os.environ[VOLT_TEST_SOCKET_FD_STR]
        os.close(fd)
        return sock
    return None


def is_uuid_like(val):
    """Returns validation of a value as a UUID.

    For our purposes, a UUID is a canonical form string:
    aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
    """
    try:
        return str(uuid.UUID(val)) == val
    except (TypeError, ValueError, AttributeError):
        return False


def generate_uuid(by_time=True, host=None, image_id=None):
    '''
    Returns uuid
    
    if by_time is True, return the uuid generated by time 
    else return host_port_iqn_lun
    '''
    if by_time:
        return binascii.hexlify(os.urandom(16))
    else:
        return str("%s:%s" % (host, image_id))
    
def get_image_id_from_peerid(peer_id):
    '''
    get image_id from peerid
    '''
    if peer_id is None:
        return None
    else:
        (host,image_id)= peer_id.split(':')
        return image_id
