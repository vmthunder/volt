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

import testtools

from voltracker.executor import btree
from voltracker.common import exception


class BtreeTest(testtools.TestCase):

    def setUp(self):
        super(BtreeTest, self).setUp()
        self._build_btree()

    def _build_btree(self):
        self.volume_id = '5cc4bebc-db27-11e1-a1eb-080027cbe205'

        self.btree_root = btree.BTreeNode(host='www.example.com', port='7447',
                               iqn='iqn.2014-3-16.com:pdl', lun='1')

        self.node1 = btree.BTreeNode(host='localhost', port='9527',
                                iqn='iqn.2014-3-20.com:pdl', lun='2')

        self.node2 = btree.BTreeNode(host='foo', port='3721',
                                iqn='iqn.2014-3-19.com:pdl', lun='3')

        self.node3 = btree.BTreeNode(host='bar', port='15625',
                                iqn='iqn.2014-3-18.com:pdl', lun='4')

        self.binary_tree = btree.BTree(self.btree_root, self.volume_id)
        self.binary_tree.insert_by_node(self.node1)
        self.binary_tree.insert_by_node(self.node2)
        self.binary_tree.insert_by_node(self.node3)

    def test_parse_to_peer_id(self):
        test_input = {
            "host": "www.example.com",
            "port": "7447",
            "iqn": "iqn.2014-3-16.com:pdl",
            "lun": "1"
        }
        result = btree.parse_to_peer_id(host=test_input['host'],
                                        port=test_input['port'],
                                        iqn=test_input['iqn'],
                                        lun=test_input['lun'])
        expect = "www.example.com,7447,iqn.2014-3-16.com:pdl,1"
        self.assertEqual(result, expect)

    def test_parse_to_peer_id_with_error(self):
        test_input = {
            "host": "www.example.com",
            "port": "7447",
            "iqn": None,
            "lun": "1"
        }

        self.assertRaises(exception.InvalidParameterValue,
                          btree.parse_to_peer_id,
                          host=test_input['host'],
                          port=test_input['port'],
                          iqn=test_input['iqn'],
                          lun=test_input['lun'])

    def test_parse_from_peer_id(self):
        test_input = "www.example.com,7447,iqn.2014-3-16.com:pdl,1"
        result = btree.parse_from_peer_id(test_input)
        expect = {
            "host": "www.example.com",
            "port": "7447",
            "iqn": "iqn.2014-3-16.com:pdl",
            "lun": "1"
        }
        self.assertEqual(result, expect)

    def test_parse_from_peer_id_with_error(self):
        test_input = "www.example.com,7447,iqn.2014-3-16.com:pdl"
        self.assertRaises(exception.InvalidParameterValue,
                          btree.parse_from_peer_id, test_input)

    def test_tree_find_available_slot(self):
        result = btree.tree_find_available_slot(self.btree_root)
        self.assertEqual(result, self.node1)

    def test_insert_by_node(self):
        test_input = btree.BTreeNode(host="www.wtf.org",
                                     port="7447",
                                     iqn="iqn.2014-3-16.com:pdl",
                                     lun="1")
        result = self.binary_tree.insert_by_node(test_input)
        self.assertEqual(result, self.node1)
        self.assertEqual(self.binary_tree.count(), 5)
        self.assertEqual(len(self.binary_tree.nodes), 5)
        self.assertEqual(self.node1.right, test_input)
        self.assertEqual(test_input.parent, self.node1)

    def test_insert_by_peer_id(self):
        test_input = "www.example.com,7447,iqn.2014-3-16.com:pdl,23"
        result = self.binary_tree.insert_by_peer_id(test_input)

        self.assertEqual(result, self.node1)
        self.assertEqual(self.binary_tree.count(), 5)
        self.assertEqual(len(self.binary_tree.nodes), 5)

    def test_tree_remove_by_peer_id(self):
        result1 = self.binary_tree.remove_by_peer_id(
            "localhost,9527,iqn.2014-3-20.com:pdl,2")

        self.assertEqual(self.node1.peer_id, result1.peer_id)
        self.assertEqual(self.binary_tree.count(), 3)
        self.assertEqual(self.btree_root.left, self.node3)
        self.assertEqual(self.node3.parent, self.btree_root)

        result2 = self.binary_tree.remove_by_peer_id(self.node2.peer_id)

        self.assertEqual(self.btree_root.right, None)

    def test_tree_remove_root(self):
        result1 = self.binary_tree.remove_by_peer_id(
            self.btree_root.peer_id)

        self.assertEqual(self.btree_root, result1)
        self.assertEqual(self.binary_tree.count(), 3)
        self.assertEqual(self.binary_tree.root, self.node1)
        self.assertEqual(self.node2.parent, self.node1)
        self.assertEqual(self.node1.right, self.node2)

    def test_get_node_parent(self):
        result1 = self.binary_tree.get_node_parent(self.node1.peer_id)
        self.assertEqual(result1, self.btree_root)

        result2 = self.binary_tree.get_node_parent(self.btree_root.peer_id)
        self.assertEqual(result2, None)

        result3 = self.binary_tree.get_node_parent(self.node2.peer_id)
        self.assertEqual(result3, self.btree_root)

        result4 = self.binary_tree.get_node_parent(self.node3.peer_id)
        self.assertEqual(result4, self.node1)
