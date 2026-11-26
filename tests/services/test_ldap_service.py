import uuid
from unittest import mock

import ldap3

from tests.base import ApiDBTestCase
from tests.services.ldap_fixtures import BASE_DN, LdapDirectoryMixin, ad_user
from zou.app import app
from zou.app.commands import commands_service
from zou.app.exceptions import (
    InactiveUserException,
    IsUserLimitReachedException,
    LdapAccountConflictException,
    LdapAmbiguousUserException,
    LdapGroupNotFoundException,
    WrongPasswordException,
)
from zou.app.models.person import Person
from zou.app.services import ldap_service, persons_service


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
                (group, {"objectClass": "group"}),
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

    def test_search_users_ad_group_missing(self):
        settings = self.directory(
            [(f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe"))],
            LDAP_GROUP=f"cn=Missing,ou=Groups,{BASE_DN}",
        )
        conn = ldap_service.open_service_connection(settings)
        with self.assertRaises(LdapGroupNotFoundException):
            ldap_service.search_users(conn, settings)

    def test_sync_with_ldap_server_group_missing_keeps_persons(self):
        settings = self.directory(
            [(f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe"))],
            LDAP_GROUP=f"cn=Missing,ou=Groups,{BASE_DN}",
        )
        person = persons_service.create_person(
            "jdoe@studio.local",
            b"",
            "John",
            "Doe",
            desktop_login="jdoe",
            is_generated_from_ldap=True,
        )
        with mock.patch.object(
            ldap_service, "get_settings", return_value=settings
        ):
            with self.assertRaises(LdapGroupNotFoundException):
                commands_service.sync_with_ldap_server()
        self.assertTrue(Person.get(person["id"]).active)

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

    def test_check_group_exists_group_is_not_a_dn(self):
        settings = self.directory(
            [(f"cn=jdoe,cn=Users,{BASE_DN}", ad_user("jdoe"))],
            LDAP_GROUP="Kitsu",
        )
        conn = ldap_service.open_service_connection(settings)
        for error in (
            ldap3.core.exceptions.LDAPInvalidDNSyntaxResult,
            ldap3.core.exceptions.LDAPInvalidDnError,
        ):
            with mock.patch.object(conn, "search", side_effect=error("bad")):
                with self.assertRaises(LdapGroupNotFoundException):
                    ldap_service.check_group_exists(conn, settings)

    def test_find_user_entry_openldap_group(self):
        def person(login):
            return {
                "objectClass": ["person", "inetOrgPerson"],
                "uid": login,
                "cn": login,
                "sn": login.title(),
                "givenName": "Given",
                "mail": f"{login}@studio.local",
                "organizationalStatus": "active",
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
        entry = ldap_service.find_user_entry(conn, settings, "alice")
        self.assertEqual(entry.entry_dn, f"uid=alice,ou=People,{BASE_DN}")
        self.assertIsNone(ldap_service.find_user_entry(conn, settings, "bob"))
        with mock.patch.object(
            ldap_service,
            "get_group_member_dns",
            wraps=ldap_service.get_group_member_dns,
        ) as get_group_member_dns:
            ldap_service.find_user_entry(
                conn, settings, "nobody", ldap_uid="x", desktop_login="y"
            )
        get_group_member_dns.assert_called_once()

    def test_is_excluded(self):
        settings = {"LDAP_EXCLUDED_ACCOUNTS": ""}
        self.assertFalse(ldap_service.is_excluded(settings, ""))
        self.assertFalse(ldap_service.is_excluded(settings, "svc1"))
        settings = {"LDAP_EXCLUDED_ACCOUNTS": "svc1, svc2,"}
        self.assertTrue(ldap_service.is_excluded(settings, "svc1"))
        self.assertTrue(ldap_service.is_excluded(settings, "svc2"))
        self.assertFalse(ldap_service.is_excluded(settings, ""))
        self.assertFalse(ldap_service.is_excluded(settings, "svc3"))

    def test_get_server_short_timeout(self):
        settings = {"LDAP_HOST": "h", "LDAP_PORT": "389", "LDAP_SSL": False}
        with mock.patch.object(ldap3, "Server") as server:
            ldap_service.get_server(settings)
            ldap_service.get_server(settings, get_info=ldap3.NONE)
        first, second = server.call_args_list
        self.assertEqual(first.kwargs["get_info"], ldap3.ALL)
        self.assertEqual(second.kwargs["get_info"], ldap3.NONE)
        self.assertEqual(first.kwargs["connect_timeout"], 5)

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
            settings, "STUDIO\\jdoe", "pw", ldap3.NTLM, get_info=ldap3.NONE
        )


def build_user(**overrides):
    user = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "jdoe@studio.local",
        "emails": ["jdoe@studio.local"],
        "desktop_login": "jdoe",
        "thumbnail": None,
        "active": True,
        "ldap_uid": "uid-jdoe",
    }
    user.update(overrides)
    return user


class LdapPersonTestCase(ApiDBTestCase):
    def create_person(self, email, **kwargs):
        return persons_service.create_person(
            email, b"x", "First", "Last", **kwargs
        )

    def test_find_ldap_person_by_ldap_uid_then_login_then_email(self):
        by_uid = self.create_person(
            "a@x.org", is_generated_from_ldap=True, ldap_uid="uid-jdoe"
        )
        found = ldap_service.find_ldap_person(build_user())
        self.assertEqual(found["id"], by_uid["id"])

        Person.get(by_uid["id"]).update({"ldap_uid": "other"})
        by_login = self.create_person(
            "b@x.org", is_generated_from_ldap=True, desktop_login="jdoe"
        )
        found = ldap_service.find_ldap_person(build_user())
        self.assertEqual(found["id"], by_login["id"])

        Person.get(by_login["id"]).update({"desktop_login": "other"})
        by_email = self.create_person(
            "jdoe@studio.local", is_generated_from_ldap=True
        )
        found = ldap_service.find_ldap_person(build_user())
        self.assertEqual(found["id"], by_email["id"])

    def test_find_ldap_person_not_found(self):
        self.assertIsNone(ldap_service.find_ldap_person(build_user()))

    def test_find_ldap_person_local_conflict(self):
        local = self.create_person("jdoe@studio.local")
        with self.assertRaises(LdapAccountConflictException):
            ldap_service.find_ldap_person(build_user())
        person = Person.get(local["id"])
        self.assertFalse(person.is_generated_from_ldap)
        self.assertIsNone(person.ldap_uid)

    def test_provision_person_creates(self):
        person_id = ldap_service.provision_person(build_user())
        person = Person.get(person_id)
        self.assertTrue(person.is_generated_from_ldap)
        self.assertEqual(person.ldap_uid, "uid-jdoe")
        self.assertEqual(person.desktop_login, "jdoe")
        self.assertEqual(person.email, "jdoe@studio.local")
        self.assertTrue(person.active)

    def test_provision_person_user_limit(self):
        count = Person.query.count()
        with mock.patch.object(
            persons_service, "is_user_limit_reached", return_value=True
        ):
            with self.assertRaises(IsUserLimitReachedException):
                ldap_service.provision_person(build_user())
        self.assertEqual(Person.query.count(), count)

    def test_provision_person_inactive_new_user_not_created(self):
        count = Person.query.count()
        with self.assertRaises(InactiveUserException):
            ldap_service.provision_person(build_user(active=False))
        self.assertEqual(Person.query.count(), count)

    def test_provision_person_updates_stale_ldap_uid(self):
        created = self.create_person(
            "jdoe@studio.local",
            desktop_login="jdoe",
            is_generated_from_ldap=True,
            ldap_uid="old-uid",
        )
        person = ldap_service.find_ldap_person(build_user())
        person_id = ldap_service.provision_person(build_user(), person)
        self.assertEqual(person_id, created["id"])
        self.assertEqual(Person.get(person_id).ldap_uid, "uid-jdoe")

    def test_provision_person_logs_a_rewritten_ldap_uid(self):
        self.create_person(
            "jdoe@studio.local",
            desktop_login="jdoe",
            is_generated_from_ldap=True,
            ldap_uid="old-uid",
        )
        person = ldap_service.find_ldap_person(build_user())
        with self.assertLogs(app.logger, "WARNING") as logs:
            ldap_service.provision_person(build_user(), person)
        output = "".join(logs.output)
        self.assertIn(person["id"], output)
        self.assertIn("old-uid", output)
        self.assertIn("uid-jdoe", output)

    def test_provision_person_email_collision(self):
        created = self.create_person(
            "old@studio.local",
            desktop_login="jdoe",
            is_generated_from_ldap=True,
            ldap_uid="uid-jdoe",
        )
        other = self.create_person("jdoe@studio.local")
        person = ldap_service.find_ldap_person(build_user())
        with self.assertLogs(app.logger, "ERROR") as logs:
            with self.assertRaises(LdapAccountConflictException):
                ldap_service.provision_person(build_user(), person)
        output = "".join(logs.output)
        self.assertIn(created["id"], output)
        self.assertIn(other["id"], output)
        self.assertEqual(Person.get(created["id"]).email, "old@studio.local")

    def test_provision_person_reactivation_user_limit(self):
        created = self.create_person(
            "jdoe@studio.local",
            desktop_login="jdoe",
            is_generated_from_ldap=True,
            ldap_uid="uid-jdoe",
            active=False,
        )
        person = ldap_service.find_ldap_person(build_user())
        with mock.patch.object(
            persons_service, "is_user_limit_reached", return_value=True
        ):
            with self.assertRaises(IsUserLimitReachedException):
                ldap_service.provision_person(build_user(), person)
        self.assertFalse(Person.get(created["id"]).active)

    def test_deactivate_person(self):
        created = self.create_person(
            "jdoe@studio.local", is_generated_from_ldap=True
        )
        ldap_service.deactivate_person(created)
        self.assertFalse(Person.get(created["id"]).active)
