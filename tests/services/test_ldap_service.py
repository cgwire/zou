import uuid
from unittest import mock

import ldap3

from tests.base import ApiDBTestCase
from tests.services.ldap_fixtures import BASE_DN, LdapDirectoryMixin, ad_user
from zou.app.commands import commands_service
from zou.app.exceptions import (
    LdapAmbiguousUserException,
    LdapGroupNotFoundException,
    WrongPasswordException,
)
from zou.app.models.person import Person
from zou.app.services import ldap_service


class LdapServiceTestCase(LdapDirectoryMixin, ApiDBTestCase):
    def test_search_users_anywhere_under_base(self):
        settings = self.directory(
            [
                (f"cn=alice,cn=Users,{BASE_DN}", ad_user("alice")),
                (
                    f"cn=bob,ou=Paris,ou=Staff,{BASE_DN}",
                    ad_user("bob"),
                ),
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual(
            sorted(user["desktop_login"] for user in users),
            ["alice", "bob"],
        )

    def test_search_users_group_filter(self):
        group = f"cn=Kitsu,ou=Groups,{BASE_DN}"
        settings = self.directory(
            [
                (
                    f"cn=alice,cn=Users,{BASE_DN}",
                    ad_user("alice", memberOf=group),
                ),
                (f"cn=bob,cn=Users,{BASE_DN}", ad_user("bob")),
            ],
            LDAP_GROUP=group,
        )
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual([user["desktop_login"] for user in users], ["alice"])

    def test_build_person_filter_escapes_group(self):
        settings = self.directory([], LDAP_GROUP="cn=Kitsu (prod),dc=x")
        person_filter = ldap_service.build_person_filter(settings)
        self.assertIn("cn=Kitsu \\28prod\\29,dc=x", person_filter)

    def test_search_users_excluded_account(self):
        settings = self.directory(
            [
                (f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe")),
                (f"cn=bob,cn=Users,{BASE_DN}", ad_user("bob")),
            ],
            LDAP_EXCLUDED_ACCOUNTS="jdoe",
        )
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual([user["desktop_login"] for user in users], ["bob"])

    def test_entry_to_user_disabled_account(self):
        settings = self.directory(
            [
                (
                    f"cn=jdoe,cn=Users,{BASE_DN}",
                    ad_user("jdoe", userAccountControl=514),
                ),
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertIs(users[0]["active"], False)

    def test_search_users_excluded_entry_without_account_control(self):
        attributes = ad_user("svc2")
        del attributes["userAccountControl"]
        settings = self.directory(
            [
                (f"cn=svc2,cn=Users,{BASE_DN}", attributes),
                (f"cn=bob,cn=Users,{BASE_DN}", ad_user("bob")),
            ],
            LDAP_EXCLUDED_ACCOUNTS="svc2",
        )
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual([user["desktop_login"] for user in users], ["bob"])

    def test_search_users_openldap_group(self):
        def person(login, **extra):
            return {
                "objectClass": ["person", "inetOrgPerson"],
                "uid": login,
                "cn": login,
                "sn": login.title(),
                "givenName": "Given",
                "mail": f"{login}@studio.local",
                "organizationalStatus": "active",
                **extra,
            }

        settings = self.directory(
            [
                (f"uid=alice,ou=People,{BASE_DN}", person("alice")),
                (f"uid=bob,ou=People,{BASE_DN}", person("bob")),
                (
                    f"cn=Kitsu,ou=Groups,{BASE_DN}",
                    {
                        "objectClass": "groupOfUniqueNames",
                        "cn": "Kitsu",
                        "uniqueMember": [
                            f"UID=Alice, OU=people,{BASE_DN.upper()}"
                        ],
                    },
                ),
            ],
            LDAP_IS_AD_SIMPLE=False,
            LDAP_GROUP="Kitsu",
        )
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual([user["desktop_login"] for user in users], ["alice"])

    def test_get_group_member_dns_missing_group(self):
        settings = self.directory(
            [], LDAP_IS_AD_SIMPLE=False, LDAP_GROUP="missing"
        )
        conn = ldap_service.open_service_connection(settings)
        with self.assertRaises(LdapGroupNotFoundException):
            ldap_service.get_group_member_dns(conn, settings)

    def test_sync_with_ldap_server_creates_person(self):
        settings = self.directory(
            [(f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe"))]
        )
        with mock.patch.object(
            ldap_service, "get_settings", return_value=settings
        ):
            commands_service.sync_with_ldap_server()
        person = Person.get_by(desktop_login="jdoe")
        self.assertIsNotNone(person)
        self.assertTrue(person.is_generated_from_ldap)

    def test_find_user_entry_by_login_in_sub_ou(self):
        dn = f"cn=jdoe,ou=Paris,ou=Staff,{BASE_DN}"
        settings = self.directory(
            [
                (dn, ad_user("jdoe")),
                (f"cn=bob,cn=Users,{BASE_DN}", ad_user("bob")),
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        entry = ldap_service.find_user_entry(conn, settings, "jdoe")
        self.assertEqual(entry.entry_dn, dn)

    def test_find_user_entry_by_email(self):
        settings = self.directory(
            [
                (
                    f"cn=jdoe,cn=Users,{BASE_DN}",
                    ad_user(
                        "jdoe",
                        mail="john.doe@studio.com",
                        userPrincipalName="jdoe@corp.studio.com",
                    ),
                )
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        for identifier in ["john.doe@studio.com", "jdoe@corp.studio.com"]:
            entry = ldap_service.find_user_entry(conn, settings, identifier)
            self.assertEqual(
                ldap_service.get_desktop_login(entry, settings), "jdoe"
            )

    def test_find_user_entry_escapes_identifier(self):
        settings = self.directory(
            [(f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe"))]
        )
        conn = ldap_service.open_service_connection(settings)
        self.assertIsNone(ldap_service.find_user_entry(conn, settings, "*"))

    def test_find_user_entry_not_in_group(self):
        group = f"cn=Kitsu,ou=Groups,{BASE_DN}"
        settings = self.directory(
            [
                (group, {"objectClass": "group"}),
                (f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe")),
            ],
            LDAP_GROUP=group,
        )
        conn = ldap_service.open_service_connection(settings)
        self.assertIsNone(ldap_service.find_user_entry(conn, settings, "jdoe"))

    def test_find_user_entry_group_missing(self):
        settings = self.directory(
            [(f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe"))],
            LDAP_GROUP=f"cn=Missing,ou=Groups,{BASE_DN}",
        )
        conn = ldap_service.open_service_connection(settings)
        with self.assertRaises(LdapGroupNotFoundException):
            ldap_service.find_user_entry(conn, settings, "jdoe")

    def test_find_user_entry_stale_ldap_uid(self):
        settings = self.directory(
            [(f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe"))]
        )
        conn = ldap_service.open_service_connection(settings)
        entry = ldap_service.find_user_entry(
            conn, settings, "jdoe", ldap_uid=f"{{{uuid.uuid4()}}}"
        )
        self.assertEqual(entry.entry_dn, f"cn=jdoe,cn=Users,{BASE_DN}")

    def test_find_user_entry_by_ldap_uid(self):
        guid = uuid.uuid4()
        settings = self.directory(
            [
                (
                    f"cn=jdoe,cn=Users,{BASE_DN}",
                    ad_user("jdoe", objectGUID=guid.bytes_le),
                ),
                (f"cn=bob,cn=Users,{BASE_DN}", ad_user("bob")),
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        entry = ldap_service.find_user_entry(
            conn, settings, "bob", ldap_uid=f"{{{guid}}}"
        )
        self.assertEqual(entry.entry_dn, f"cn=jdoe,cn=Users,{BASE_DN}")

    def test_find_user_entry_ambiguous(self):
        settings = self.directory(
            [
                (
                    f"cn=jdoe,cn=Users,{BASE_DN}",
                    ad_user("jdoe", mail="shared@studio.com"),
                ),
                (
                    f"cn=jdoe2,ou=Paris,{BASE_DN}",
                    ad_user("jdoe2", mail="shared@studio.com"),
                ),
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        with self.assertRaises(LdapAmbiguousUserException):
            ldap_service.find_user_entry(conn, settings, "shared@studio.com")

    def test_check_user_password_simple(self):
        settings = self.directory(
            [
                (
                    f"cn=jdoe,cn=Users,{BASE_DN}",
                    ad_user("jdoe", userPassword="secret"),
                )
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        entry = ldap_service.find_user_entry(conn, settings, "jdoe")
        ldap_service.check_user_password(settings, entry, "secret")
        with self.assertRaises(WrongPasswordException):
            ldap_service.check_user_password(settings, entry, "wrong")
        with mock.patch.object(ldap_service, "connect") as connect:
            with self.assertRaises(WrongPasswordException):
                ldap_service.check_user_password(settings, entry, "")
            connect.assert_not_called()

    def test_check_user_password_ntlm(self):
        settings = self.directory(
            [(f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe"))],
            LDAP_IS_AD=True,
            LDAP_IS_AD_SIMPLE=False,
            LDAP_DOMAIN="STUDIO",
        )
        entry = mock.Mock()
        entry.sAMAccountName = "jdoe"
        with mock.patch.object(ldap_service, "connect") as connect:
            ldap_service.check_user_password(settings, entry, "pw")
        connect.assert_called_once_with(
            settings, "STUDIO\\jdoe", "pw", ldap3.NTLM
        )
