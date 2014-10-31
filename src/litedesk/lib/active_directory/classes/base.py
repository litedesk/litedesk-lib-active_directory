#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2014, Deutsche Telekom AG - Laboratories (T-Labs)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import weakref

import ldap


class _AttributeFactory(object):

    def __init__(self, cls, *args, **kwargs):
        self.__cls = cls
        self.__args = args
        self.__kwargs = kwargs

    def new(self, attr_name):
        self.__kwargs['attr_name'] = attr_name
        attribute = property.__new__(self.__cls)
        attribute.__init__(*self.__args, **self.__kwargs)
        return attribute


class BaseAttribute(property):

    def __new__(cls, *args, **kwargs):
        return _AttributeFactory(cls, *args, **kwargs)

    def __init__(self, ad_key, **kwargs):
        self.__ad_key = ad_key
        self.__name = kwargs['attr_name']
        self.__values = weakref.WeakKeyDictionary()
        super(BaseAttribute, self).__init__(
            self.getter, self.setter, self.deleter
        )

    @property
    def ad_key(self):
        return self.__ad_key

    @property
    def name(self):
        return self.__name

    def modified(self, instance):
        return (
            self.__values.has_key(instance) and
            self.__values[instance]['modified']
        )

    def getter(self, instance):
        try:
            return self.__values[instance]['value']
        except KeyError:
            return None

    def setter(self, instance, value):
        self.raw_set(
            instance, value, True if self.__values.has_key(instance) else False
        )

    def deleter(self, instance):
        try:
            self.__values.pop(instance)
        except KeyError:
            pass

    def raw_set(self, instance, value, modified):
        self.__values[instance] = {
            'value': value,
            'modified': modified
        }

class ReadOnlyAttribute(BaseAttribute):

    def setter(self, instance, value):
        raise ldap.UNWILLING_TO_PERFORM(
            "{0} attribute is Read-Only".format(self.ad_key)
        )


class WriteOnceAttribute(BaseAttribute):

    def setter(self, instance, value):
        if self.modified(instance):
            raise ldap.UNWILLING_TO_PERFORM(
            "{0} attribute is Write-Once and it"
            " already has a value".format(self.ad_key)
        )
        else:
            super(WriteOnceAttribute, self).setter(instance, value)


class _BaseObjectMetaclass(type):

    def __new__(mcs, name, bases, __dict__):
        attrs = {
            attr_name: attr_fact.new(attr_name)
            for attr_name, attr_fact in __dict__.viewitems()
            if isinstance(attr_fact, _AttributeFactory)
        }
        attrs.update({
            attr_name: attr
            for base in bases
            for attr_name, attr in dict(base.__dict__).viewitems()
            if isinstance(attr, BaseAttribute)
        })
        __dict__.update(attrs)
        __dict__.update(mcs.__make_methods(attrs))
        return type.__new__(mcs, name, bases, __dict__)

    @staticmethod
    def __make_methods(attrs):
        def _raw_set(self, name, value, modified):
            for attr in attrs.viewvalues():
                if name in (attr.name, attr.ad_key):
                    attr.raw_set(self, value, modified)
                    break
            else:
                raise KeyError(
                    '{0} has no attribute {1}'.format(self, name)
                )
        def _moddict(self):
            return {
                attr.ad_key: attr.getter(self)
                for attr in self._raw_attrs
                if attr.modified(self)
            }
        def _raw_attrs(self):
            return attrs.viewvalues()

        return {
            '_raw_set': _raw_set,
            '_moddict': property(_moddict),
            '_raw_attrs': property(_raw_attrs)
        }


class BaseObject(object):

    __metaclass__ = _BaseObjectMetaclass

    object_class = WriteOnceAttribute('objectClass')
    object_guid = ReadOnlyAttribute('objectGUID')
    distinguished_name = WriteOnceAttribute('distinguishedName')
    instance_type = WriteOnceAttribute('instanceType')
    object_category = WriteOnceAttribute('objectCategory')
    ds_core_propagation_data = ReadOnlyAttribute('dSCorePropagationData')
    name = BaseAttribute('name')
    usn_created = ReadOnlyAttribute('uSNCreated')
    usn_changed = ReadOnlyAttribute('uSNChanged')
    when_created = ReadOnlyAttribute('whenCreated')
    when_changed = ReadOnlyAttribute('whenChanged')

    _base_search_query = '(objectClass=*)'
    _preset = {}

    def __init__(self, session, **kwargs):
        self._session = session
        self._raw_update(**kwargs)
        self._raw_update(**self._preset)

    def _raw_update(self, **kwargs):
        try:
            self.parent = kwargs.pop('parent')
        except KeyError:
            pass
        for key, value in kwargs.iteritems():
            if key == 'parent':
                continue
            self._raw_set(key, value, False)

    def _distinguished_name(self):
        raise NotImplementedError()

    def diff(self, other):
        return {
            attr.ad_key:{
                self:{
                    'value': attr.getter(self),
                    'modified': attr.modified(self)
                },
                other:{
                    'value': attr.getter(other),
                    'modified': attr.modified(other)
                }
            }
            for attr in self._raw_attrs
            if attr.getter(self) != attr.getter(other)
        }

    def update(self, **kwargs):
        try:
            self.parent = kwargs.get('parent', self.parent)
        except AttributeError:
            self.parent = None
        for key, value in kwargs.iteritems():
            if key == 'parent':
                continue
            if key in dir(self):
                setattr(self, key, value)
            else:
                raise AttributeError(
                    "{0} has no attribute {1}".format(self, key)
                )

    @classmethod
    def base_search_query(cls):
        try:
            return cls.concat_search_query(
                super(BaseObject).base_search_query(),
                cls._base_search_query
            )
        except AttributeError:
            return cls._base_search_query

    @staticmethod
    def concat_search_query(a, b):
        return '(&{0}{1})'.format(a, b)

    @classmethod
    def search(cls, conn, base=None, query=None):
        if base is None:
            base = conn.root_dn
        if query is None:
            query = cls.base_search_query()
        else:
            query = cls.concat_search_query(cls.base_search_query(), query)
        return [
            cls(
                conn,
                **{
                    key: value[0]
                    if len(value) == 1 and isinstance(value, list) else value
                    for key, value in entry[1].viewitems()
                }
            )
            for entry in conn.search_st(base, ldap.SCOPE_SUBTREE, query)
            if entry[0] is not None
        ]

    def update_from_ad(self):
        query = '(distinguishedName={0})'.format(self.distinguished_name)
        try:
            other = self.__class__.search(self._session, query=query)[0]
            diff = self.diff(other)
            for attr in self._raw_attrs:
                self._raw_set(attr.name, attr.getter(self), False)
            for name, attr in diff.viewitems():
                if (
                    not attr[self]['modified'] and
                    attr[other]['value'] is not None
                ):
                    self._raw_set(name, attr[other]['value'], False)
                elif attr[self]['value'] is not None:
                    self._raw_set(name, attr[self]['value'], True)
            return True
        except IndexError:
            return False


    def save(self):
        if not self.update_from_ad():
            for attr in self._raw_attrs:
                if (
                    attr.name != 'distinguished_name' and
                    attr.getter(self) is not None
                ):
                    self._raw_set(attr.name, attr.getter(self), True)
        modlist = [
            (ad_key, value)
            for ad_key, value in self._moddict.viewitems()
        ]
        if self.object_guid is None:
            self._session.add_s(self.distinguished_name, modlist)
        else:
            modlist = [
                (ldap.MOD_REPLACE, ad_key, value)
                for ad_key, value in modlist
            ]
            self._session.modify_s(self.distinguished_name, modlist)
        for attr in self._raw_attrs:
            self._raw_set(attr.name, attr.getter(self), False)
        self.update_from_ad()

    def delete(self):
        self._session.delete_s(self.distinguished_name)


class Company(BaseObject):

    ou = BaseAttribute('ou')

    _base_search_query = '''(&
        (objectClass=organizationalUnit)
        (instanceType=4)
        (!(isCriticalSystemObject=TRUE))
    )'''

    _preset = {
        'object_class': 'organizationalUnit'
    }

    @property
    def users(self):
        try:
            return User.search(self._session, base=self.distinguished_name)
        except ldap.NO_SUCH_OBJECT:
            return []

    def _distinguished_name(self):
        return 'OU={0},{1}'.format(
            self.ou,
            self._session.root_dn
        )

    def save(self):
        if not self.distinguished_name:
            self.distinguished_name = self._distinguished_name()
        super(Company, self).save()


class User(BaseObject):
    USER_ACCOUNT_CONTROL_ACTIVE = '544'

    cn = ReadOnlyAttribute('cn')
    account_expires = BaseAttribute('accountExpires')
    bad_password_time = BaseAttribute('badPasswordTime')
    bad_pwd_count = ReadOnlyAttribute('badPwdCount')
    code_page = BaseAttribute('codePage')
    country_code = BaseAttribute('countryCode')
    department = BaseAttribute('department')
    display_name = BaseAttribute('displayName')
    given_name = BaseAttribute('givenName')
    last_logoff = ReadOnlyAttribute('lastLogoff')
    last_logon = ReadOnlyAttribute('lastLogon')
    last_logon_timestamp = ReadOnlyAttribute('lastLogonTimestamp')
    logon_count = ReadOnlyAttribute('logonCount')
    mail = BaseAttribute('mail')
    object_sid = ReadOnlyAttribute('objectSid')
    primary_group_id = ReadOnlyAttribute('primaryGroupID')
    pwd_last_set = ReadOnlyAttribute('pwdLastSet')
    s_am_account_name = BaseAttribute('sAMAccountName')
    s_am_account_type = ReadOnlyAttribute('sAMAccountType')
    description = BaseAttribute('description')
    telephone_number = BaseAttribute('telephoneNumber')
    physical_delivery_office_name = BaseAttribute('physicalDeliveryOfficeName')
    ms_ds_supported_encryption_types = BaseAttribute('msDS-SupportedEncryptionTypes')
    sn = BaseAttribute('sn')
    user_account_control = BaseAttribute('userAccountControl')
    user_principal_name = BaseAttribute('userPrincipalName')

    _base_search_query = '''(&
        (objectClass=organizationalPerson)
        (instanceType=4)
    )'''

    _preset = {
        'object_class': ['organizationalPerson', 'top', 'person', 'user'],
    }

    def _distinguished_name(self):
        return 'CN={0},{1}'.format(
            self.s_am_account_name,
            self.parent.distinguished_name
        )

    def parent_distinguished_name(self):
        return self.distinguished_name.replace(
            'CN={0},'.format(self.s_am_account_name),
            ''
        )

    @property
    def is_activated(self):
        return self.user_account_control == self.USER_ACCOUNT_CONTROL_ACTIVE

    def activate(self):
        self.user_account_control = self.USER_ACCOUNT_CONTROL_ACTIVE

    def save(self):
        if not self.distinguished_name:
            self.distinguished_name = self._distinguished_name()
        if not self.is_activated: self.activate()
        super(User, self).save()
