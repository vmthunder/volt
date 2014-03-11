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

""" A native implements of binary tree to track the topology of peers
    (nova-compute nodes)
"""


from collections import deque

from voltracker.common import exception
from voltracker import executor


def parse_to_peer_id(host, port, iqn, lun):

    try:
        peer_id = host + ':' + port + ':' + iqn + ':' + lun
    except TypeError:
        param = ''
        if host is None:
            param += 'host'
        if port is None:
            param += 'port'
        if iqn is None:
            param += 'iqn'
        if lun is None:
            param += 'lun'
        extra_msg = _('The param can\'t be None.')
        raise exception.InvalidParameterValue(param=param,
                                              value=None,)

    return peer_id


def parse_from_peer_id(peer_id):
    items = peer_id.split(':')

    if len(items) is not 4:
        extra_msg = _("The peer_id seems invalid, "
                      "please check if there are exactly 3 colons in peer_id")
        raise exception.InvalidParameterValue(param='peer_id',
                                              value=peer_id,
                                              extra_msg=extra_msg)
    else:
        host, port, iqn, lun = items

    return {
        'host': host, 'port': port,
        'iqn': iqn, 'lun': lun
    }


def tree_find_available_slot(tree_root):
    """
    Use the breadth first search algorithm to find the first node
    which left child or right child is empty.
    """
    node_queue = deque()
    node_queue.append(tree_root)

    slot = None
    while len(node_queue):
        node = node_queue.pop()
        if node.available():
            slot = node
            break
        else:
            node_queue.append(node.left)
            node_queue.append(node.right)

    return slot

def tree_remove_by_node(self, target):
    """Delete a tree node with the specific node instance

    :param target: the target instance of the node to be removed
    """

    if not target:
        extra_msg = _('The node to be removed is not in the tree')
        raise exception.InvalidParameterValue(value=None,
                                              param='node',
                                              extra_msg=extra_msg)

    up = None
    # TODO(zpfalpc23@gmail.com): After the node removal, the tree
    # need to be more balanced.
    if target.left and target.right:
        up = target.left
        current = target
        # Always terminated in finite loop
        while not current.available():
            if current.right:
                current = current.right

        target.right.parent = current
        if not current.left:
            current.left = target.right
        else:
            current.right = target.left
    elif target.left:
        up = target.left
    elif target.right:
        up = target.right

    if up:
        up.parent = target.parent
    if target.parent:
        if target.left is target:
            target.left = up
        else:
            target.right = up

    return True


class BTreeNode(object):

    def __init__(self, peer_id=None, host=None,
                 port=None, iqn=None, lun=None,
                 left=None, right=None, parent=None):

        if not peer_id:
            peer_id = parse_to_peer_id(host, port, iqn, lun)
        else:
            info = parse_from_peer_id(peer_id)
            if info['host'] != host or \
               info['port'] != port or \
               info['iqn'] != iqn or \
               info['lun'] != lun:
                extra_msg = 'The peer_id is inconsistent with other' \
                            'volume information.'
                raise exception.InvalidParameterValue(extra_msg=extra_msg)

        self.peer = peer_id
        self.host = host
        self.left = left
        self.right = right
        self.parent = parent

    def available(self):
        """ Return true if the node can append a child
        """
        return not self.left or not self.right


class BTree(object):

    def __init__(self, root, volume_id=None):

        root.left = None
        root.right = None
        root.parent = None
        self.root = root
        self.volume_id = volume_id
        self.nodes = {root.peer_id: root}

    def insert_by_node(self, new_node):
        """ Insert a new node to the binary tree by node instance.

        :param new_node: new node instance to be added
        """
        if new_node is None:
            extra_msg = _('The new adding node cannot be None')
            raise exception.InvalidParameterValue(value=None,
                                                  param='new_node',
                                                  extra_msg=extra_msg)
        elif new_node.parent:
            extra_msg = _('the new adding node already has a parent')
            raise exception.InvalidParameterValue(value=new_node.peer_id,
                                                  param='new_node',
                                                  extra_msg=extra_msg)


        slot = tree_find_available_slot(self.root)
        self.nodes.update[new_node.peer_id] = new_node
        new_node.left = None
        new_node.right = None
        new_node.parent = slot
        if not slot.left:
            slot.left = new_node
        else:
            slot.right = new_node

        return slot

    def insert_by_peer_id(self, peer_id):
        """ Insert a new node to the binary tree by peer id.

        :param peer_id: the peer id of the node to be added
        """
        if peer_id in self.nodes:
            raise exception.DuplicateItem(params=peer_id)

        node = BTreeNode(peer_id=peer_id)

        return self.insert_by_node(node)

    def remove_by_peer_id(self, peer_id):
        """ Delete a tree node with the specific peer_id

        :param peer_id: the peed id of the node to be removed
        """
        if peer_id not in self.nodes:
            extra_msg = _('The node to be removed is not in the tree')
            raise exception.InvalidParameterValue(value=peer_id,
                                                  param='peer_id',
                                                  extra_msg=extra_msg)

        target = self.nodes[peer_id]
        tree_remove_by_node(target)
        del self.nodes[peer_id]

        return target

    def count(self):
        return len(self.nodes)

    def get_node_parent(self, peer_id):
        """ Get the parent of a node

        :param peer_id: the peer_id of the node
        """
        if peer_id not in self.nodes:
            extra_msg = _('This node is not in the tree')
            raise exception.InvalidParameterValue(value=peer_id,
                                                  param='node',
                                                  extra_msg=extra_msg)

        node = self.nodes[peer_id]
        return node.parent


class BtreeExecutor(executor.Executor):
    """
    """
    def __init__(self):
        self.volumes = {}


    def get_volumes_list(self):
        volumes_list = []
        for volume_id in self.volumes:
            volumes_list.append({
                'id': volume_id,
                'count': self.volumes[volume_id].count(),
            })

        return {'volumes': volumes_list}

    def get_volumes_detail(self, volume_id):
        volumes_list = []
        volumes_tree = self.volumes.get(volume_id, None)
        for peer_id in volumes_tree.nodes:
            tree_node = self.nodes[peer_id]
            volumes_list.append({
                'host': tree_node.host,
                'port': tree_node.port,
                'iqn': tree_node.iqn,
                'lun': tree_node.lun
            })

        return {'volumes': volumes_list}

    def add_volume_metadata(self, volume_id, **kwargs):
        """
        """
        host = kwargs.get('host', None)
        port = kwargs.get('port', None)
        iqn = kwargs.get('iqn', None)
        lun = kwargs.get('lun', None)
        peer_id = parse_to_peer_id(host, port, iqn, lun)

        if volume_id not in self.volumes:
            self.volumes[volume_id] = BTree(BTreeNode(peer_id))
        else:
            self.volumes[volume_id].insert_by_peer_id(peer_id)

    def delete_volume_metadata(self, volume_id, peer_id=None, **kwargs):
        """
        """
        if peer_id is None:
            host = kwargs.get('host', None)
            port = kwargs.get('port', None)
            iqn = kwargs.get('iqn', None)
            lun = kwargs.get('lun', None)
            peer_id = parse_to_peer_id(host, port, iqn, lun)

        if volume_id not in self.volumes:
            raise exception.NotFound
        else:
            try:
                vol_tree = self.volumes[volume_id]
                vol_tree.remove_by_peer_id(peer_id)
            except exception.InvalidParameterValue, e:
                raise exception.NotFound

            


