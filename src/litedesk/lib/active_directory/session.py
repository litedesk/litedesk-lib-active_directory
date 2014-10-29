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


from __future__ import unicode_literals
import warnings
import weakref

import ldap


class Session(object):
    """Session object maintains the LDAP connection.
    To avoid problems we finalize LDAP connection even if exception occurs."""

    __instances = weakref.WeakValueDictionary()

    def __new__(cls, url, dn, password, insecure=False):
        session_desc = (url, dn, password, insecure)
        try:
            return cls.__instances[session_desc]
        except KeyError:
            instance = object.__new__(cls, url, dn, password, insecure)
            cls.__instances[session_desc] = instance
            return instance

    def __init__(self, url, dn, password, insecure=False):
        """Initialize the session.
        This doesn't open the connection yet."""
        self.__url = url
        self.__dn = dn
        self.__password = password
        self.__insecure = insecure
        self.__ldap = None

    def __enter__(self):
        """Initialize LDAP connection to the endpoint"""
        self.__ldap = ldap.initialize(self.__url)
        self.__ldap.protocol_version = 3
        self.__ldap.set_option(ldap.OPT_REFERRALS, 0)
        self.__ldap.set_option(ldap.OPT_X_TLS_DEMAND, True)
        self.__ldap.set_option(ldap.OPT_DEBUG_LEVEL, 255)
        if self.__insecure:
            warnings.warn(
                'Allowing LDAP over TLS without certificate verification'
            )
            self.__ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, 0)
        self.__ldap.simple_bind_s(self.__dn, self.__password)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finalize the connection"""
        if self.__ldap is not None:
            self.__ldap.unbind()

    @property
    def root_dn(self):
        return self.__dn[self.__dn.find('DC='):]

    @property
    def active(self):
        return self.__ldap is not None

    def __get_connection(self):
        with self:
            while True:
                yield getattr(self.__ldap, self.__ldap_attr)

    def __getattr__(self, item):
        if not self.active:
            self.__ldap_iter = self.__get_connection()
        self.__ldap_attr = item
        return self.__ldap_iter.next()