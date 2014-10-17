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

from volt.common import utils
from volt.common import exception
from volt import executor
from volt.openstack.common.gettextutils import _
from volt.openstack.common import log as logging

import time, datetime, threading

LOG = logging.getLogger(__name__)


def tree_find_available_slot(tree_root):
    """
    Use the breadth first search algorithm to find the first node
    which left child or right child is empty.
    """
    node_queue = deque()
    node_queue.append(tree_root)

    slot = None
    LOG.debug(_("len(node_queue)"),{'length': len(node_queue)})
    
    while len(node_queue):        
        node = node_queue.popleft()
        LOG.debug(_("node is None %(node)s, length %(length)s"),
                      {'node': node is None, 'length': len(node_queue)})
        if node is None:
            continue
        else:
            LOG.debug(_("node's peer_id %(peer_id)s, status: %(status)s, host: %(host)s, tgt:%(iqn)s"),
                      {'peer_id':node.peer_id, 'status':node.status, 'host':node.host, 'iqn':node.iqn})
        if node_available(node):
            slot = node
            break
        else:
            node_queue.append(node.left)
            node_queue.append(node.right)
    
    return slot

def update_tree_status(tree_root):
    """update the level of each tree node
    """
    node_queue = deque()
    node_queue.append(tree_root)

    LOG.debug(_("len(node_queue)"),{'length': len(node_queue)})
    
    while len(node_queue) :
        node = node_queue.popleft()
        LOG.debug(_("node is None %(node)s, length %(length)s"),
                      {'node': node is None, 'length': len(node_queue)})
        if node is None:
            continue
        else:
            if node.parent :
                node.level = node.parent.level + 1
            else:
                node.level = 0
                
            LOG.debug(_("node's peer_id %(peer_id)s, status: %(status)s, host: %(host)s, level:%(level)s"),
                      {'peer_id':node.peer_id, 'status':node.status, 'host':node.host, 'level':node.level})
        
            node_queue.append(node.left)
            node_queue.append(node.right)


def node_available(node):
    """ Return true if the node can append a child
    """
    if node is None:
        return False

    return node.status == 'OK' and \
           (not node.left or not node.right)


class BTreeNode(object):

    def __init__(self, peer_id=None, host=None,
                 port=None, iqn=None, lun=None,
                 left=None, right=None, parent=None,
                 status=None, image_id=None, fake_root=False):
        
        self.host = host
        self.port = port
        self.iqn = iqn
        self.lun = lun
        self.left = left
        self.right = right
        self.parent = parent
        self.status = status
        self.fake_root = fake_root
        self.level = -1
        if not peer_id:
            peer_id = utils.generate_uuid(by_time=False, host=host, image_id=image_id)
            self.level = 0
        self.peer_id = peer_id

    def identity(self):
        """ Make BTreeNode callable to return to client.
        """
        return {
            "host" : self.host,
            "port" : self.port,
            "iqn": self.iqn,
            "lun": self.lun,
            'status': self.status,
            "peer_id": self.peer_id
        }

    def get_sibling(self):
        if self.parent is None:
            return None

        if self.parent.left == self:
            return self.parent.right

        return self.parent.left


class BTree(object):

    def __init__(self, volume_id, root=None):

        if root is None:
            root = BTreeNode(peer_id=utils.generate_uuid(), host=utils.generate_uuid(),
                             port=utils.generate_uuid(),
                             iqn=utils.generate_uuid(),
                             lun=utils.generate_uuid(),
                             image_id=volume_id,
                             status='OK', fake_root=True)
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
        elif self.nodes.get(new_node.peer_id, None):
            extra_msg = _('The new adding node has existed in tree')
            raise exception.InvalidParameterValue(value=None,
                                                  param='new_node',
                                                  extra_msg=extra_msg)
        elif new_node.parent:
            extra_msg = _('the new adding node already has a parent')
            raise exception.InvalidParameterValue(value=new_node.peer_id,
                                                  param='new_node',
                                                  extra_msg=extra_msg)

        slot = tree_find_available_slot(self.root)
        if slot is None:
            extra_msg = _('no available slot for newly volume.')
            raise exception.InvalidParameterValue(value=new_node.peer_id,
                                                  param='new_node',
                                                  extra_msg=extra_msg)

        self.nodes[new_node.peer_id] = new_node
        new_node.left = None
        new_node.right = None
        new_node.parent = slot
        new_node.level = slot.level + 1
        if not slot.left:
            slot.left = new_node
        else:
            slot.right = new_node

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

        if target.status == 'pending':
            if target.left:
                self.tree_remove_by_node(target.left)
            if target.right:
                self.tree_remove_by_node(target.right)

        up = None
        # TODO(zpfalpc23@gmail.com): After the node removal, the tree
        # need to be more balanced.
        if target.left and target.right:
            up = target.left
            current = target
            # Always terminated in finite loop
            while not node_available(current):
                if current.left:
                    current = current.left

            target.right.parent = current
            if not current.left:
                current.left = target.right
            else:
                current.right = target.right
        elif target.left:
            up = target.left
        elif target.right:
            up = target.right

        if up:
            up.parent = target.parent
        if target.parent:
            if target.parent.left is target:
                target.parent.left = up
            else:
                target.parent.right = up
        if target == self.root:
            self.root = up
        
        # update the level info
        update_tree_status(self.root)
        return target

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
        self.tree_remove_by_node(target)
        del self.nodes[peer_id]

        return target

    def count(self):
        return len(self.nodes)

    def get_node_parents(self, node):
        """ Get the parents of a node

        :param node: BTreeNode 
        """
        if node.peer_id not in self.nodes:
            extra_msg = _('This node is not in the tree')
            raise exception.InvalidParameterValue(value=node.peer_id,
                                                  param='node',
                                                  extra_msg=extra_msg)

        parent_level = node.level - 1 
        parents_list = []
        parents_list.append(node.parent.identity())
        
        for parent_node in self.nodes.values():
            if parent_node.level == parent_level and node is not node.parent:
                parents_list.append(parent_node.identity())
                
        return parents_list

    def update_nodes(self, peer_id=None, host=None,
                     port=None, iqn=None, lun=None,
                     status=None):
        if peer_id is None:  
#             if peer_id is None, cann't be updated                        
#             peer_id = utils.generate_uuid(host, port, iqn, lun, False)
            return None

        if peer_id not in self.nodes:
            LOG.debug(_("cant found is %(peer_id)s, %(type)s"),
                      {'peer_id': peer_id, 'type': type(peer_id)})
            target = BTreeNode(peer_id=peer_id, host=host,
                                 port=port, iqn=iqn, lun=lun,
                                 status=status)
            self.insert_by_node(target)
        else:
            target = self.nodes[peer_id]
            target.peer_id = peer_id
            target.host = host
            target.port = port
            target.iqn = iqn
            target.lun = lun
            target.status = status

        if target.status == 'pending':
            if target.left:
                self.tree_remove_by_node(target.left)
            if target.right:
                self.tree_remove_by_node(target.right)

        return target


class BtreeExecutor(executor.Executor):
    """
    """
    def __init__(self):
        self.volumes = {}
        self.host_to_volumes = {}

    def get_volumes_list(self):
        volumes_list = []
        for volume_id in self.volumes:
            volumes_list.append({
                'id': volume_id,
                'count': self.volumes[volume_id].count(),
            })

        return volumes_list

    def get_volumes_detail(self, volume_id):
        volumes_list = []
        volumes_tree = self.volumes.get(volume_id, None)
        if volumes_tree is None:
            volumes_nodes = []
        else:
            volumes_nodes = volumes_tree.nodes
        for peer_id in volumes_nodes:
            tree_node = self.nodes[peer_id]
            volumes_list.append({
                'host': tree_node.host,
                'port': tree_node.port,
                'iqn': tree_node.iqn,
                'lun': tree_node.lun,
                'status': tree_node.status
            })

        return volumes_list

    def add_volume_metadata(self, volume_id, peer_id, **kwargs):
        """
        """
        host = kwargs.get('host', None)
        port = kwargs.get('port', None)
        iqn = kwargs.get('iqn', None)
        lun = kwargs.get('lun', None)
        LOG.debug(_("host = %(host)s, port = %(port)s, iqn = %(iqn)s,"
                    " lun = %(lun)s"),
                  {'host': host, 'port': port, 'iqn': iqn, 'lun': lun})

        if volume_id not in self.volumes:
            raise exception.NotFound
        
        if peer_id is None:
            peer_id = utils.generate_uuid(False, host, volume_id)
            
        target = self.volumes[volume_id].update_nodes(peer_id=peer_id,
                                                      host=host,
                                                      port=port,
                                                      iqn=iqn,
                                                      lun=lun,
                                                      status='OK')
        return target.identity()

    def delete_volume_metadata(self, volume_id, peer_id):
        """
        """
        if peer_id is None:
            extra_msg = _('peer_id should not be None.')
            raise exception.InvalidParameterValue(value=peer_id,
                                                  param='peer_id',
                                                  extra_msg=extra_msg)

        if volume_id not in self.volumes:
            raise exception.NotFound
        else:
            try:
                vol_tree = self.volumes[volume_id]
                node = vol_tree.nodes.get(peer_id, None)

                if node is None:
                    raise exception.InvalidParameterValue

                self.remove_host_bookkeeping(host=node.host, peer_id=peer_id)
                vol_tree.remove_by_peer_id(peer_id)
            except exception.InvalidParameterValue, e:
                raise exception.NotFound

    def insert_node_slot(self, volume_id, peer_id=None, host=None):
        if peer_id is None and host is None:
            extra_msg = _('peer_id or host should not be None.')
            raise exception.InvalidParameterValue(value=peer_id,
                                                  param='peer_id',
                                                  extra_msg=extra_msg)

        if volume_id is None:
            extra_msg = _('volume_id should not be None.')
            raise exception.InvalidParameterValue(value=peer_id,
                                                  param='peer_id',
                                                  extra_msg=extra_msg)

        if volume_id not in self.volumes:
            self.volumes[volume_id] = BTree(volume_id)
        
        peer_id = utils.generate_uuid(False, host, volume_id)
        
        if peer_id in self.volumes[volume_id].nodes:
            target = self.volumes[volume_id].nodes[peer_id]

        else:            
            LOG.debug(_("new peer_id is %(peer_id)s, %(type)s"),
                      {'peer_id': peer_id, 'type': type(peer_id)})
            new_node = BTreeNode(peer_id=peer_id,
                                 host=host,
                                 image_id=volume_id,
                                 status='pending')
            
            try:
                self.volumes[volume_id].insert_by_node(new_node)
    
                self.add_host_bookkeeping(host=host,
                                         peer_id=peer_id,
                                         node=new_node)
    
                target = self.volumes[volume_id].nodes[peer_id]
            except Exception as exc:
                LOG.debug(_(" fatal error occured insert_node_slot: %s" % exc))

        return target

    def get_volume_parents(self, volume_id, peer_id=None, host=None):
        """
        """
        target = self.insert_node_slot(volume_id,
                                       peer_id=peer_id,
                                       host=host)

        parents_list = self.get_parents_info(target)

        return \
            {
                'peer_id': target.peer_id,
                'parents': parents_list
            }

    def get_parents_info(self, target):
        if target.parent.fake_root:
            return []
        else:                       
            image_id = utils.get_image_id_from_peerid(target.peer_id)
            btree = self.volumes[image_id]
            parents_list = btree.get_node_parents(target)
            LOG.debug('get_parents_info: %s' % parents_list)
            return parents_list

    def update_status(self, host=None):
        if host not in self.host_to_volumes.keys():
            return []

        volume_list = self.host_to_volumes[host]['volume_list']
        self.host_to_volumes[host]['timestamp'] = datetime.datetime.now()
        volume_info = []
        
        for (peer_id, volume) in volume_list.iteritems():

            parents_list = self.get_parents_info(volume)

            volume_info.append({
                'peer_id': peer_id,
                'parents': parents_list
            })

        return volume_info


    def add_host_bookkeeping(self, host=None, peer_id=None, node=None):

        host_info = self.host_to_volumes.get(host, None)
        if host_info is None:
            host_info = {}
            volumes_list = {}
            timestamp = datetime.datetime.now()
            host_info['volume_list'] = volumes_list
            host_info['timestamp'] = timestamp
            self.host_to_volumes[host] = host_info
        else:
            volumes_list = host_info['volume_list']
            
        if peer_id in volumes_list:
            raise exception.Duplicate

        volumes_list[peer_id] = node

    def remove_host_bookkeeping(self, host=None, peer_id=None):

        host_info = self.host_to_volumes.get(host, None)

        if host_info is None or peer_id not in host_info['volume_list']:
            raise exception.NotFound

        del host_info['volume_list'][peer_id]

    #kickoff node that lost connction
    def kickoff_dead_node(self):
        
        while True:
            now_time = datetime.datetime.now()
            LOG.debug('scanning host_to_volumes list: %s host lists: %s' % 
                      (now_time, self.host_to_volumes.keys()))
            for host in self.host_to_volumes.keys():            
                host_info = self.host_to_volumes[host]
                last_save_time = host_info['timestamp']            
                if (now_time - last_save_time).seconds > executor.MAX_POLLING_TIME:
                    #if time exceed MAX_POLLING_TIME, then kick out of the tree               
                    volume_list = host_info['volume_list']   
                    
                    for peer_id in volume_list.keys():
                        LOG.debug('volume_list.keys(): %s',volume_list.keys())
                        self.remove_host_bookkeeping(host, peer_id)
                        vol_tree = self.volumes[utils.get_image_id_from_peerid(peer_id)]
                        vol_tree.remove_by_peer_id(peer_id)
                        LOG.debug(_('kick out host %(host)s, peer_id: %(peer_id)s elapse time: %(time)s'),{
                                    'host':host, 'peer_id':peer_id, 'time':now_time - last_save_time})
                    del self.host_to_volumes[host]
                
            LOG.debug('scanning host_to_volumes list: %s host lists: %s' % 
                      (now_time, self.host_to_volumes.keys()))
            timeout = threading.Event()
            timeout.wait(executor.MAX_POLLING_TIME)
        

class BtreeWithUncleExecutor(BtreeExecutor):
    """
    """

    def get_parents_info(self, target):
        if target.parent.fake_root:
            return []
        else:
            parent = target.parent
            parents_list = [parent.identity()]
            sibling = parent.get_sibling()
            if sibling is not None:
                parents_list.append(sibling.identity())

            return parents_list
