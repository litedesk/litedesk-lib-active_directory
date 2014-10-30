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


import ldap


class _AttributeFactory(object):

    def __init__(self, cls, *args, **kwargs):
        self.__cls = cls
        self.__args =  args
        self.__kwargs = kwargs

    def __call__(self):
        attr = object.__new__(self.__cls, *self.__args, **self.__kwargs)
        attr.__init__(*self.__args, **self.__kwargs)
        return attr

    @property
    def ad_key(self):
        try:
            return self.__args[0]
        except IndexError:
            return self.__kwargs['ad_key']


class BaseAttribute(object):

    def __new__(cls, *args, **kwargs):
        return _AttributeFactory(cls, *args, **kwargs)

    def __init__(self, ad_key):
        self.__ad_key = ad_key
        self.__value = None

    @property
    def ad_key(self):
        return self.__ad_key

    def set(self, value):
        if isinstance(value, unicode):
            value = value.encode()
        elif isinstance(value, (list, tuple)):
            value = [
                item.encode() if isinstance(item, unicode) else item
                for item in value
            ]
        self.__value = value

    def get(self):
        return self.__value


class _BaseObjectMetaclass(type):

    ATTR_TEMPLATE = '_{0}__{1}'
    AD_KEY_PROP_TEMPLATE = '_{0}__ad_key_{1}'

    def __new__(mcs, name, bases, __dict__):
        props = [
            (
                prop_name,
                mcs.AD_KEY_PROP_TEMPLATE.format(name, attr_fact.ad_key),
                mcs.__make_property(
                    mcs.ATTR_TEMPLATE.format(name, prop_name),
                    prop_name,
                    attr_fact
                )
            )
            for prop_name, attr_fact in __dict__.viewitems()
            if isinstance(attr_fact, _AttributeFactory)
        ]
        __dict__.update({prop[0]: prop[2] for prop in props})
        __dict__.update({prop[1]: prop[2] for prop in props})
        __dict__['ad_key'] = mcs.__resolve_ad_key
        for base in bases:
            if hasattr(base, '_preset'):
                __dict__['_preset'].update(base._preset)
        """for prop_name, ad_key, prop in props:
            __dict__[prop_name] = prop
            __dict__['__ad_keys'][ad_key] = prop"""
        """__dict__.update({
            prop_name: property(*mcs.__make_attr_property(prop_name, attr_fact))
            for prop_name, attr_fact in __dict__.viewitems()
            if isinstance(attr_fact, _AttributeFactory)
        })"""
        return type.__new__(mcs, name, bases, __dict__)

    @classmethod
    def __make_property(mcs, attr_name, prop_name, attr_fact):
        def getter(self):
            return mcs.__get_or_create_attr(self, attr_fact, attr_name).get()
        def setter(self, value):
            mcs.__get_or_create_attr(self, attr_fact, attr_name).set(value)
        return property(getter, setter)

    @staticmethod
    def __get_or_create_attr(instance, attr_fact, attr_name):
        try:
            return instance.__dict__[attr_name]
        except KeyError:
            instance.__dict__[attr_name] = attr_fact()
            return instance.__dict__[attr_name]

    @staticmethod
    def __resolve_ad_key(instance, ad_key):
        needle = 'ad_key_{0}'.format(ad_key)
        for name in dir(instance):
            index = len(name) - len(needle)
            if name[index:] == needle:
                return name
        else:
            raise ldap.NO_SUCH_ATTRIBUTE(ad_key)


class BaseObject(object):

    __metaclass__ = _BaseObjectMetaclass

    object_class = BaseAttribute('objectClass')
    object_guid = BaseAttribute('objectGUID')
    distinguished_name = BaseAttribute('distinguishedName')
    instance_type = BaseAttribute('instanceType')
    object_category = BaseAttribute('objectCategory')
    ds_core_propagation_data = BaseAttribute('dSCorePropagationData')
    name = BaseAttribute('name')
    usn_created = BaseAttribute('uSNCreated')
    usn_changed = BaseAttribute('uSNChanged')
    when_created = BaseAttribute('whenCreated')
    when_changed = BaseAttribute('whenChanged')

    _base_search_query = '(objectClass=*)'
    _preset = {}

    def __init__(self, session, **kwargs):
        self._session = session
        self.update(**kwargs)

    def update(self, **kwargs):
        parent = kwargs.get('parent', None)
        try:
            self.parent = parent or self.parent
        except AttributeError:
            self.parent = None
        for key, value in kwargs.iteritems():
            if key in dir(self):
                setattr(self, key, value)
            else:
                raise AttributeError(
                    "{0} doesn't have {1} attribute".format(self, key)
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
        instances = [
            (cls(conn), entry)
            for entry in conn.search_st(base, ldap.SCOPE_SUBTREE, query)
            if entry[0] is not None
        ]
        for instance, entry in instances:
            instance.update(**{
                instance.ad_key(key): value[0]
                if len(value) == 1 and isinstance(value, list) else value
                for key, value in entry[1].viewitems()
            })
        return [instance for instance, entry in instances]

    def save(self):
        self.update(**self._preset)
        modlist = [
            (attr.ad_key, attr.get())
            for attr in (
                getattr(self, key)
                for key in dir(self)
            )
            if isinstance(attr, BaseAttribute) and not attr.ad_key == 'distinguishedName'
        ]
        if self.object_guid is None:
            self._session.add_s(self.distinguished_name, modlist)
        else:
            modlist = [
                (ldap.MOD_REPLACE, ad_key, value)
                for ad_key, value in modlist
            ]
            self._session.modify_s(self.distinguished_name, modlist)

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

    def save(self):
        if not self.distinguished_name:
            self.distinguished_name = 'OU={0},{1}'.format(
                self.ou,
                self._session.root_dn
            )
        super(Company, self).save()


class User(BaseObject):
    USER_ACCOUNT_CONTROL_ACTIVE = '544'

    cn = BaseAttribute('cn')
    account_expires = BaseAttribute('accountExpires')
    bad_password_time = BaseAttribute('badPasswordTime')
    bad_pwd_count = BaseAttribute('badPwdCount')
    code_page = BaseAttribute('codePage')
    country_code = BaseAttribute('countryCode')
    department = BaseAttribute('department')
    display_name = BaseAttribute('displayName')
    given_name = BaseAttribute('givenName')
    last_logoff = BaseAttribute('lastLogoff')
    last_logon = BaseAttribute('lastLogon')
    last_logon_timestamp = BaseAttribute('lastLogonTimestamp')
    logon_count = BaseAttribute('logonCount')
    mail = BaseAttribute('mail')
    object_sid = BaseAttribute('objectSid')
    primary_group_id = BaseAttribute('primaryGroupID')
    pwd_last_set = BaseAttribute('pwdLastSet')
    s_am_account_name = BaseAttribute('sAMAccountName')
    s_am_account_type = BaseAttribute('sAMAccountType')
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

    @property
    def is_activated(self):
        return self.user_account_control == self.USER_ACCOUNT_CONTROL_ACTIVE

    def activate(self):
        self.user_account_control = self.USER_ACCOUNT_CONTROL_ACTIVE

    def save(self):
        if not self.distinguished_name:
            self.distinguished_name = 'CN={0},{1}'.format(
                self.s_am_account_name,
                self.parent.distinguished_name
            )
        if not self.is_activated: self.activate()
        super(User, self).save()
