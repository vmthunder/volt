# Copyright (c) 2011 OpenStack Foundation
# Copyright 2013 IBM Corp.
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

"""Policy Engine For Glance"""

import copy
import os.path

from oslo.config import cfg

from volt.common import exception
from volt.openstack.common import jsonutils
from volt.openstack.common import log as logging
from volt.openstack.common import policy
from volt.openstack.common.gettextutils import _


LOG = logging.getLogger(__name__)

DEFAULT_RULES = {
    'context_is_admin': policy.RoleCheck('role', 'admin'),
    'default': policy.TrueCheck(),
}

CONF = cfg.CONF

_rules = None
_checks = {}


def check(rule, target, creds, exc=None, *args, **kwargs):
    """
    Checks authorization of a rule against the target and credentials.

    :param rule: The rule to evaluate.
    :param target: As much information about the object being operated
                   on as possible, as a dictionary.
    :param creds: As much information about the user performing the
                  action as possible, as a dictionary.
    :param exc: Class of the exception to raise if the check fails.
                Any remaining arguments passed to check() (both
                positional and keyword arguments) will be passed to
                the exception class.  If exc is not provided, returns
                False.

    :return: Returns False if the policy does not allow the action and
             exc is not provided; otherwise, returns a value that
             evaluates to True.  Note: for rules using the "case"
             expression, this True value will be the specified string
             from the expression.
    """

    # Allow the rule to be a Check tree
    if isinstance(rule, policy.BaseCheck):
        result = rule(target, creds)
    elif not _rules:
        # No rules to reference means we're going to fail closed
        result = False
    else:
        try:
            # Evaluate the rule
            result = _rules[rule](target, creds)
        except KeyError:
            # If the rule doesn't exist, fail closed
            result = False

    # If it is False, raise the exception if requested
    if exc and result is False:
        raise exc(*args, **kwargs)

    return result

# Really have to figure out a way to deprecate this
def set_rules(rules):
    """Set the rules in use for policy checks."""

    global _rules

    _rules = rules


# Ditto
def reset():
    """Clear the rules used for policy checks."""

    global _rules

    _rules = None


class Enforcer(object):
    """Responsible for loading and enforcing rules"""

    def __init__(self, policy_file=None, rules=None,
                 default_rule=None, use_conf=True):
        self.default_rule = CONF.policy_default_rule
        self.policy_path = self._find_policy_file()
        self.policy_file_mtime = None
        self.policy_file_contents = None
        self.load_rules()

    def set_rules(self, rules):
        """Create a new Rules object based on the provided dict of rules"""
        rules_obj = policy.Rules(rules, self.default_rule)
        set_rules(rules_obj)

    def add_rules(self, rules):
        """Add new rules to the Rules object"""
        if _rules:
            rules_obj = policy.Rules(rules)
            _rules.update(rules_obj)
        else:
            set_rules(rules)

    def load_rules(self):
        """Set the rules found in the json file on disk"""
        if self.policy_path:
            rules = self._read_policy_file()
            rule_type = ""
        else:
            rules = DEFAULT_RULES
            rule_type = "default "

        text_rules = dict((k, str(v)) for k, v in rules.items())
        msg = (_('Loaded %(rule_type)spolicy rules: %(text_rules)s') %
               {'rule_type': rule_type, 'text_rules': text_rules})
        LOG.debug(msg)

        self.set_rules(rules)

    @staticmethod
    def _find_policy_file():
        """Locate the policy json data file"""
        policy_file = CONF.find_file(CONF.policy_file)
        if policy_file:
            return policy_file
        else:
            LOG.warn(_('Unable to find policy file'))
            return None

    def _read_policy_file(self):
        """Read contents of the policy file

        This re-caches policy data if the file has been changed.
        """
        mtime = os.path.getmtime(self.policy_path)
        if not self.policy_file_contents or mtime != self.policy_file_mtime:
            LOG.debug(_("Loading policy from %s") % self.policy_path)
            with open(self.policy_path) as fap:
                raw_contents = fap.read()
                rules_dict = jsonutils.loads(raw_contents)
                self.policy_file_contents = dict(
                    (k, policy.parse_rule(v))
                    for k, v in rules_dict.items())
            self.policy_file_mtime = mtime
        return self.policy_file_contents

    def _check(self, context, rule, target, *args, **kwargs):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param rule: String representing the action to be checked
           :param object: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        credentials = {
            'roles': context.roles,
            'user': context.user,
            'tenant': context.tenant,
        }

        return check(rule, target, credentials, *args, **kwargs)

    def enforce(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Volt request context
           :param action: String representing the action to be checked
           :param object: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        return self._check(context, action, target,
                           exception.Forbidden, action=action)

    def check(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param object: Dictionary representing the object of the action.
           :returns: A non-False value if access is allowed.
        """
        return self._check(context, action, target)

    def check_is_admin(self, context):
        """Check if the given context is associated with an admin role,
           as defined via the 'context_is_admin' RBAC rule.

           :param context: Glance request context
           :returns: A non-False value if context role is admin.
        """
        target = context.to_dict()
        return self.check(context, 'context_is_admin', target)
