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

import os
import random
import unittest
from codecs import utf_16_le_encode

import ldap

from session import Session
from classes.base import Company, User


class CommonTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.url = os.environ['LITEDESK_LIB_ACTIVE_DIRECTORY_URL']
            cls.dn = os.environ['LITEDESK_LIB_ACTIVE_DIRECTORY_DN']
            cls.password = os.environ['LITEDESK_LIB_ACTIVE_DIRECTORY_PASSWORD']
        except KeyError:
            raise Exception(
                'This tests require environment variables (LITEDESK_LIB_ACTIVE_DIRECTORY_URL, '
                'LITEDESK_LIB_ACTIVE_DIRECTORY_DN, LITEDESK_LIB_ACTIVE_DIRECTORY_PASSWORD) to be set.'
            )


class SessionTestCase(CommonTest):

    def test_session(self):
        session = Session(self.url, self.dn, self.password, insecure=True)
        self.assertIsInstance(session.whoami_s(), str)


class CompanyTestCase(CommonTest):

    def setUp(self):
        super(CompanyTestCase, self).setUp()
        self.session = Session(self.url, self.dn, self.password, insecure=True)
        self.test_ou = 'test_company'

    def test_create_company(self):
        company = Company(self.session, ou=self.test_ou)
        company.save()
        self.assertIsInstance(company, Company)
        self.assertEqual(company.ou, self.test_ou)
        company.delete()

    def test_company_search(self):
        company = Company(self.session, ou=self.test_ou)
        company.save()
        companies = Company.search(self.session, self.session.root_dn, '(OU={0})'.format(self.test_ou))
        self.assertEqual(len(companies), 1)
        company.delete()

    def test_company_delete(self):
        company = Company(self.session, ou=self.test_ou)
        company.save()
        company.delete()
        companies = Company.search(self.session, self.session.root_dn, '(OU={0})'.format(self.test_ou))
        self.assertEqual(len(companies), 0)


class UserTestCase(CommonTest):

    def setUp(self):
        super(UserTestCase, self).setUp()
        self.session = Session(self.url, self.dn, self.password, insecure=True)
        self.test_ou = 'test_company'
        self.test_company = Company(self.session, ou=self.test_ou)
        self.test_company.save()
        self.test_s_am_account_name = 'test.user'
        self.test_given_name = 'Test'
        self.test_sn = 'User'
        self.test_mail = 'test.user@example.com'
        self.test_display_name = 'Test User'
        self.test_password = 'VeryStrongPassword1'

    def tearDown(self):
        for user in self.test_company.users:
            user.delete()
        self.test_company.delete()

    def user_create(self):
        return User(
            self.session,
            parent=self.test_company,
            s_am_account_name=self.test_s_am_account_name,
            given_name=self.test_given_name,
            sn=self.test_sn,
            mail=self.test_mail,
            display_name=self.test_display_name
        )

    def test_user_create(self):
        user = self.user_create()
        user.save()
        self.assertIsInstance(user, User)
        self.assertEqual(user.s_am_account_name, self.test_s_am_account_name)
        self.assertEqual(user.parent, self.test_company)
        self.assertEqual(user.s_am_account_name, self.test_company.users[0].s_am_account_name)
        user.delete()

    def test_user_is_activated_on_creation(self):
        user = self.user_create()
        user.save()
        self.assertIsInstance(user, User)
        self.assertTrue(user.is_activated, 'User is not activated')
        user.delete()

    def test_user_search(self):
        user = self.user_create()
        user.save()
        users = User.search(
            self.session,
            query='(&(sAMAccountName={0})(mail={1}))'.format(self.test_s_am_account_name, self.test_mail)
        )
        self.assertEqual(len(users), 1)
        user.delete()

    def test_user_edit(self):
        NEW_USER_NAME = 'User %08d' % random.randint(0, 100000000)
        user = self.user_create()
        user.save()
        user.given_name = NEW_USER_NAME
        user.save()
        users = User.search(
            self.session,
            query='(&(sAMAccountName={0})(givenName={1}))'.format(self.test_s_am_account_name, user.given_name)
            )

        self.assertEqual(len(users), 1)
        updated_user = users[0]
        self.assertEqual(updated_user.given_name, user.given_name)
        user.delete()

    def test_user_delete(self):
        user = self.user_create()
        user.save()
        user.delete()
        users = User.search(
            self.session,
            query='(&(sAMAccountName={0})(mail={1}))'.format(self.test_s_am_account_name, self.test_mail)
        )
        self.assertEqual(len(users), 0)

    def test_user_modify(self):
        user = self.user_create()
        user.save()
        user = User.search(
            self.session,
            query='(&(sAMAccountName={0})(mail={1}))'.format(self.test_s_am_account_name, self.test_mail)
        )[0]
        user.mail = 'test2.user@example.com'
        user.save()
        self.assertEqual(user.mail, 'test2.user@example.com')
        user.delete()

    def test_user_set_password(self):
        user = self.user_create()
        user.save()
        user.set_password(self.test_password)
        encoded_password = utf_16_le_encode('"{0}"'.format(self.test_password))[0]
        encoded_password_2 = utf_16_le_encode('"{0}_2"'.format(self.test_password))[0]
        self._session.modify_s(self.distinguished_name, [
            (ldap.MOD_DELETE, 'unicodePwd', encoded_password),
            (ldap.MOD_ADD, 'unicodePwd', encoded_password_2)
        ])
        user.delete()


if __name__ == '__main__':
    unittest.main()
