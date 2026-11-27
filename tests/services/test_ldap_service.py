import ssl
import tempfile
import uuid
from unittest import mock

import ldap3

from tests.base import ApiDBTestCase
from tests.services.ldap_fixtures import (
    BASE_DN,
    LdapDirectoryMixin,
    ad_user,
    openldap_group,
    openldap_person,
)
from zou.app import app, config
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

    def test_build_person_filter_default(self):
        settings = self.directory([])
        self.assertEqual(
            ldap_service.build_person_filter(settings),
            "(&(objectClass=person)(!(objectClass=computer)))",
        )
        settings = self.directory([], LDAP_IS_AD_SIMPLE=False)
        self.assertEqual(
            ldap_service.build_person_filter(settings),
            "(&(objectClass=person))",
        )

    def test_build_person_filter_custom_user_filter(self):
        group = f"cn=Kitsu,ou=Groups,{BASE_DN}"
        settings = self.directory(
            [],
            LDAP_GROUP=group,
            LDAP_USER_FILTER="(&(objectClass=user)(department=Anim))",
        )
        self.assertEqual(
            ldap_service.build_person_filter(settings, "(cn=jdoe)"),
            "(&(&(objectClass=user)(department=Anim))"
            f"(memberOf={group})(cn=jdoe))",
        )

    def test_build_person_filter_wraps_bare_user_filter(self):
        settings = self.directory([], LDAP_USER_FILTER="department=Anim")
        self.assertEqual(
            ldap_service.build_person_filter(settings),
            "(&(department=Anim))",
        )

    def test_search_users_custom_user_filter(self):
        settings = self.directory(
            [
                (
                    f"cn=alice,cn=Users,{BASE_DN}",
                    ad_user("alice", department="Anim"),
                ),
                (
                    f"cn=bob,cn=Users,{BASE_DN}",
                    ad_user("bob", department="Compta"),
                ),
            ],
            LDAP_USER_FILTER="(&(objectClass=person)(department=Anim))",
        )
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual([user["desktop_login"] for user in users], ["alice"])

    def test_find_user_entry_custom_user_filter(self):
        settings = self.directory(
            [
                (
                    f"cn=bob,cn=Users,{BASE_DN}",
                    ad_user("bob", department="Compta"),
                ),
            ],
            LDAP_USER_FILTER="(&(objectClass=person)(department=Anim))",
        )
        conn = ldap_service.open_service_connection(settings)
        self.assertIsNone(ldap_service.find_user_entry(conn, settings, "bob"))

    def test_search_users_reads_every_page(self):
        logins = ["alice", "bob", "carol", "dave", "eve"]
        settings = self.directory(
            [
                (f"cn={login},cn=Users,{BASE_DN}", ad_user(login))
                for login in logins
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        with mock.patch.object(ldap_service, "SEARCH_PAGE_SIZE", 2):
            with mock.patch.object(
                conn, "search", wraps=conn.search
            ) as search:
                users = ldap_service.search_users(conn, settings)
        self.assertEqual(
            sorted(user["desktop_login"] for user in users), logins
        )
        self.assertEqual(search.call_count, 3)
        for call in search.call_args_list:
            self.assertEqual(call.kwargs["paged_size"], 2)

    def tls_settings(self, **overrides):
        settings = {
            "LDAP_HOST": "dc.studio.local",
            "LDAP_PORT": "636",
            "LDAP_SSL": True,
            "LDAP_START_TLS": False,
            "LDAP_VERIFY_CERTIFICATES": False,
            "LDAP_CA_FILE": "",
        }
        settings.update(overrides)
        return settings

    def test_get_server_does_not_verify_by_default(self):
        server = ldap_service.get_server(self.tls_settings())
        self.assertTrue(server.ssl)
        self.assertEqual(server.tls.validate, ssl.CERT_NONE)

    def test_get_server_verifies_certificates(self):
        server = ldap_service.get_server(
            self.tls_settings(LDAP_VERIFY_CERTIFICATES=True)
        )
        self.assertEqual(server.tls.validate, ssl.CERT_REQUIRED)
        self.assertIsNone(server.tls.ca_certs_file)
        self.assertEqual(server.tls.sni, "dc.studio.local")

    def test_get_server_verifies_with_ca_file(self):
        with tempfile.NamedTemporaryFile(suffix=".pem") as ca_file:
            server = ldap_service.get_server(
                self.tls_settings(
                    LDAP_VERIFY_CERTIFICATES=True, LDAP_CA_FILE=ca_file.name
                )
            )
        self.assertEqual(server.tls.validate, ssl.CERT_REQUIRED)
        self.assertEqual(server.tls.ca_certs_file, ca_file.name)

    def test_get_server_missing_ca_file(self):
        with self.assertRaises(
            ldap3.core.exceptions.LDAPSSLConfigurationError
        ):
            ldap_service.get_server(
                self.tls_settings(
                    LDAP_VERIFY_CERTIFICATES=True,
                    LDAP_CA_FILE="/nonexistent/ca.pem",
                )
            )

    def test_build_person_filter_nested_groups(self):
        group = f"cn=Kitsu,ou=Groups,{BASE_DN}"
        settings = self.directory(
            [], LDAP_GROUP=group, LDAP_NESTED_GROUPS=True
        )
        self.assertIn(
            f"(memberOf:1.2.840.113556.1.4.1941:={group})",
            ldap_service.build_person_filter(settings),
        )
        settings["LDAP_NESTED_GROUPS"] = False
        self.assertIn(
            f"(memberOf={group})", ldap_service.build_person_filter(settings)
        )

    def nested_openldap_directory(self, **overrides):
        people = f"ou=People,{BASE_DN}"
        groups = f"ou=Groups,{BASE_DN}"
        return self.directory(
            [
                (f"uid={login},{people}", openldap_person(login))
                for login in ["alice", "bob", "carol", "dave"]
            ]
            + [
                (
                    f"cn=Kitsu,{groups}",
                    openldap_group(
                        "Kitsu",
                        [f"uid=alice,{people}", f"cn=Anim,{groups}"],
                    ),
                ),
                (
                    f"cn=Anim,{groups}",
                    openldap_group(
                        "Anim", [f"uid=bob,{people}", f"cn=Layout,{groups}"]
                    ),
                ),
                (
                    f"cn=Layout,{groups}",
                    openldap_group(
                        "Layout",
                        [f"uid=carol,{people}", f"cn=Kitsu,{groups}"],
                    ),
                ),
                (
                    f"cn=Compta,{groups}",
                    openldap_group("Compta", [f"uid=dave,{people}"]),
                ),
            ],
            **{
                "LDAP_IS_AD_SIMPLE": False,
                "LDAP_GROUP": "Kitsu",
                **overrides,
            },
        )

    def test_search_users_openldap_direct_members_only(self):
        settings = self.nested_openldap_directory()
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual([user["desktop_login"] for user in users], ["alice"])

    def test_search_users_openldap_nested_groups(self):
        settings = self.nested_openldap_directory(LDAP_NESTED_GROUPS=True)
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual(
            sorted(user["desktop_login"] for user in users),
            ["alice", "bob", "carol"],
        )

    def test_get_group_member_dns_nested_missing_group(self):
        settings = self.nested_openldap_directory(
            LDAP_NESTED_GROUPS=True, LDAP_GROUP="Missing"
        )
        conn = ldap_service.open_service_connection(settings)
        with self.assertRaises(LdapGroupNotFoundException):
            ldap_service.get_group_member_dns(conn, settings)

    def test_open_service_connection_without_password(self):
        for mode in [
            {"LDAP_IS_AD_SIMPLE": True},
            {"LDAP_IS_AD_SIMPLE": False, "LDAP_IS_AD": True},
            {"LDAP_IS_AD_SIMPLE": False},
        ]:
            settings = self.directory([], LDAP_PASSWORD="", **mode)
            with self.assertRaises(
                ldap3.core.exceptions.LDAPPasswordIsMandatoryError
            ):
                ldap_service.open_service_connection(settings)

    def connection_kwargs(self, settings):
        with mock.patch.object(ldap3, "Connection") as connection:
            ldap_service.connect(settings, "user", "secret", ldap3.SIMPLE)
        (server,) = connection.call_args.args
        return {"server": server, **connection.call_args.kwargs}

    def test_connect_without_start_tls(self):
        settings = self.tls_settings(LDAP_SSL=False)
        self.assertIs(self.connection_kwargs(settings)["auto_bind"], True)

    def test_connect_with_start_tls(self):
        settings = self.tls_settings(
            LDAP_SSL=False, LDAP_PORT="389", LDAP_START_TLS=True
        )
        self.assertEqual(
            self.connection_kwargs(settings)["auto_bind"],
            ldap3.AUTO_BIND_TLS_BEFORE_BIND,
        )

    def test_connect_start_tls_verifies_certificates(self):
        settings = self.tls_settings(
            LDAP_SSL=False,
            LDAP_START_TLS=True,
            LDAP_VERIFY_CERTIFICATES=True,
        )
        server = self.connection_kwargs(settings)["server"]
        self.assertFalse(server.ssl)
        self.assertEqual(server.tls.validate, ssl.CERT_REQUIRED)

    def test_connect_ssl_and_start_tls(self):
        settings = self.tls_settings(LDAP_START_TLS=True)
        with self.assertRaises(
            ldap3.core.exceptions.LDAPSSLConfigurationError
        ):
            ldap_service.connect(settings, "user", "secret", ldap3.SIMPLE)

    def test_get_login_attribute_default(self):
        settings = self.directory([])
        self.assertEqual(ldap_service.get_login_attribute(settings), "cn")
        settings.update(LDAP_IS_AD_SIMPLE=False, LDAP_IS_AD=True)
        self.assertEqual(
            ldap_service.get_login_attribute(settings), "sAMAccountName"
        )
        settings.update(LDAP_IS_AD=False)
        self.assertEqual(ldap_service.get_login_attribute(settings), "uid")

    def test_get_login_attribute_custom(self):
        settings = self.directory([], LDAP_LOGIN_ATTRIBUTE=" sAMAccountName ")
        self.assertEqual(
            ldap_service.get_login_attribute(settings), "sAMAccountName"
        )
        self.assertIn(
            "sAMAccountName", ldap_service.get_user_attributes(settings)
        )

    def test_get_login_attribute_invalid(self):
        for attribute in ["uid)(objectClass=*", "a b", "-uid"]:
            settings = self.directory([], LDAP_LOGIN_ATTRIBUTE=attribute)
            with self.assertRaises(
                ldap3.core.exceptions.LDAPInvalidFilterError
            ):
                ldap_service.get_login_attribute(settings)

    def test_search_users_custom_login_attribute(self):
        settings = self.directory(
            [
                (
                    f"cn=John Doe,cn=Users,{BASE_DN}",
                    ad_user("John Doe", sAMAccountName="jdoe"),
                )
            ],
            LDAP_LOGIN_ATTRIBUTE="sAMAccountName",
        )
        conn = ldap_service.open_service_connection(settings)
        users = ldap_service.search_users(conn, settings)
        self.assertEqual([user["desktop_login"] for user in users], ["jdoe"])
        entry = ldap_service.find_user_entry(conn, settings, "jdoe")
        self.assertEqual(entry.entry_dn, f"cn=John Doe,cn=Users,{BASE_DN}")
        self.assertIsNone(
            ldap_service.find_user_entry(conn, settings, "John Doe")
        )

    def mapped_directory(self):
        return self.directory(
            [
                (
                    f"cn=jdoe,cn=Users,{BASE_DN}",
                    ad_user(
                        "jdoe",
                        displayName="Johnny",
                        department="Doe",
                        otherMailbox="john.doe@studio.com",
                        jpegPhoto=b"photo",
                    ),
                )
            ],
            LDAP_FIRST_NAME_ATTRIBUTE="displayName",
            LDAP_LAST_NAME_ATTRIBUTE="department",
            LDAP_EMAIL_ATTRIBUTE="otherMailbox",
            LDAP_THUMBNAIL_ATTRIBUTE="jpegPhoto",
        )

    def test_search_users_attribute_mapping(self):
        settings = self.mapped_directory()
        self.assertTrue(
            {"displayName", "department", "otherMailbox", "jpegPhoto"}
            <= set(ldap_service.get_user_attributes(settings))
        )
        conn = ldap_service.open_service_connection(settings)
        (user,) = ldap_service.search_users(conn, settings)
        self.assertEqual(user["first_name"], "Johnny")
        self.assertEqual(user["last_name"], "Doe")
        self.assertEqual(user["email"], "john.doe@studio.com")
        self.assertEqual(user["thumbnail"], b"photo")

    def test_search_users_default_attribute_mapping(self):
        settings = self.directory(
            [
                (
                    f"cn=jdoe,cn=Users,{BASE_DN}",
                    ad_user("jdoe", thumbnailPhoto=b"photo"),
                )
            ]
        )
        conn = ldap_service.open_service_connection(settings)
        (user,) = ldap_service.search_users(conn, settings)
        self.assertEqual(user["first_name"], "Given")
        self.assertEqual(user["last_name"], "Jdoe")
        self.assertEqual(user["email"], "jdoe@studio.local")
        self.assertEqual(user["thumbnail"], b"photo")

    def test_find_user_entry_by_mapped_email(self):
        settings = self.mapped_directory()
        conn = ldap_service.open_service_connection(settings)
        entry = ldap_service.find_user_entry(
            conn, settings, "john.doe@studio.com"
        )
        self.assertEqual(entry.entry_dn, f"cn=jdoe,cn=Users,{BASE_DN}")
        self.assertIsNone(
            ldap_service.find_user_entry(conn, settings, "jdoe@studio.local")
        )

    def test_invalid_mapped_attribute(self):
        for key in [
            "LDAP_FIRST_NAME_ATTRIBUTE",
            "LDAP_LAST_NAME_ATTRIBUTE",
            "LDAP_EMAIL_ATTRIBUTE",
            "LDAP_THUMBNAIL_ATTRIBUTE",
        ]:
            settings = self.directory([], **{key: "mail)(cn=*"})
            with self.assertRaises(
                ldap3.core.exceptions.LDAPInvalidFilterError
            ):
                ldap_service.get_user_attributes(settings)

    def role_directory(self, **overrides):
        groups = f"ou=Groups,{BASE_DN}"
        admins = f"cn=Admins,{groups}"
        managers = f"cn=Managers,{groups}"
        clients = f"cn=Clients,{groups}"
        return self.directory(
            [
                (admins, {"objectClass": "group"}),
                (managers, {"objectClass": "group"}),
                (clients, {"objectClass": "group"}),
                (
                    f"cn=alice,cn=Users,{BASE_DN}",
                    ad_user("alice", memberOf=[managers, admins]),
                ),
                (
                    f"cn=bob,cn=Users,{BASE_DN}",
                    ad_user("bob", memberOf=[managers]),
                ),
                (
                    f"cn=carol,cn=Users,{BASE_DN}",
                    ad_user("carol", memberOf=[clients]),
                ),
                (f"cn=dave,cn=Users,{BASE_DN}", ad_user("dave")),
            ],
            **{
                "LDAP_ADMIN_GROUP": admins,
                "LDAP_MANAGER_GROUP": managers,
                "LDAP_CLIENT_GROUP": clients,
                **overrides,
            },
        )

    def test_search_users_role_groups(self):
        settings = self.role_directory()
        conn = ldap_service.open_service_connection(settings)
        roles = {
            user["desktop_login"]: user["role"]
            for user in ldap_service.search_users(conn, settings)
        }
        self.assertEqual(
            roles,
            {
                "alice": "admin",
                "bob": "manager",
                "carol": "client",
                "dave": "user",
            },
        )

    def test_search_users_without_role_group(self):
        settings = self.role_directory(
            LDAP_ADMIN_GROUP="", LDAP_MANAGER_GROUP="", LDAP_CLIENT_GROUP=""
        )
        conn = ldap_service.open_service_connection(settings)
        for user in ldap_service.search_users(conn, settings):
            self.assertNotIn("role", user)

    def test_search_users_role_group_missing(self):
        settings = self.role_directory(
            LDAP_ADMIN_GROUP=f"cn=Missing,ou=Groups,{BASE_DN}"
        )
        conn = ldap_service.open_service_connection(settings)
        with self.assertRaises(LdapGroupNotFoundException):
            ldap_service.search_users(conn, settings)

    def test_get_entry_role(self):
        settings = self.role_directory()
        conn = ldap_service.open_service_connection(settings)
        for login, role in [
            ("alice", "admin"),
            ("bob", "manager"),
            ("carol", "client"),
            ("dave", "user"),
        ]:
            entry = ldap_service.find_user_entry(conn, settings, login)
            self.assertEqual(
                ldap_service.get_entry_role(conn, settings, entry), role
            )
        settings["LDAP_ADMIN_GROUP"] = ""
        settings["LDAP_MANAGER_GROUP"] = ""
        settings["LDAP_CLIENT_GROUP"] = ""
        self.assertIsNone(ldap_service.get_entry_role(conn, settings, entry))

    def test_openldap_role_groups(self):
        people = f"ou=People,{BASE_DN}"
        settings = self.directory(
            [
                (f"uid={login},{people}", openldap_person(login))
                for login in ["alice", "bob"]
            ]
            + [
                (
                    f"cn=Supervisors,ou=Groups,{BASE_DN}",
                    openldap_group("Supervisors", [f"uid=alice,{people}"]),
                )
            ],
            LDAP_IS_AD_SIMPLE=False,
            LDAP_SUPERVISOR_GROUP="Supervisors",
        )
        conn = ldap_service.open_service_connection(settings)
        roles = {
            user["desktop_login"]: user["role"]
            for user in ldap_service.search_users(conn, settings)
        }
        self.assertEqual(roles, {"alice": "supervisor", "bob": "user"})
        entry = ldap_service.find_user_entry(conn, settings, "alice")
        self.assertEqual(
            ldap_service.get_entry_role(conn, settings, entry), "supervisor"
        )

    def ldap_person_with_role(self, login, role, email=None):
        return persons_service.create_person(
            email or f"{login}@studio.local",
            b"",
            login.title(),
            "Doe",
            role=role,
            desktop_login=login,
            is_generated_from_ldap=True,
        )

    def test_sync_applies_role_groups(self):
        settings = self.role_directory()
        alice = self.ldap_person_with_role("alice", "user")
        bob = self.ldap_person_with_role("bob", "admin")
        with mock.patch.object(
            ldap_service, "get_settings", return_value=settings
        ):
            commands_service.sync_with_ldap_server()
        self.assertEqual(Person.get(alice["id"]).role.code, "admin")
        self.assertEqual(Person.get(bob["id"]).role.code, "manager")
        self.assertEqual(
            Person.get_by(desktop_login="carol").role.code, "client"
        )

    def test_sync_keeps_role_without_role_group(self):
        settings = self.role_directory(
            LDAP_ADMIN_GROUP="", LDAP_MANAGER_GROUP="", LDAP_CLIENT_GROUP=""
        )
        bob = self.ldap_person_with_role("bob", "supervisor")
        with mock.patch.object(
            ldap_service, "get_settings", return_value=settings
        ):
            commands_service.sync_with_ldap_server()
        self.assertEqual(Person.get(bob["id"]).role.code, "supervisor")

    def test_sync_keeps_role_of_protected_account(self):
        settings = self.role_directory()
        dave = self.ldap_person_with_role("dave", "admin")
        with mock.patch.object(
            config, "PROTECTED_ACCOUNTS", ["dave@studio.local"]
        ):
            with mock.patch.object(
                ldap_service, "get_settings", return_value=settings
            ):
                commands_service.sync_with_ldap_server()
        self.assertEqual(Person.get(dave["id"]).role.code, "admin")

    def test_provision_person_role(self):
        person = self.ldap_person_with_role("dave", "admin")
        user = {
            "email": "dave@studio.local",
            "first_name": "Dave",
            "last_name": "Doe",
            "active": True,
            "desktop_login": "dave",
            "ldap_uid": None,
            "role": "user",
        }
        with mock.patch.object(
            config, "PROTECTED_ACCOUNTS", ["dave@studio.local"]
        ):
            ldap_service.provision_person(
                user, persons_service.get_person(person["id"])
            )
        self.assertEqual(Person.get(person["id"]).role.code, "admin")
        ldap_service.provision_person(
            user, persons_service.get_person(person["id"])
        )
        self.assertEqual(Person.get(person["id"]).role.code, "user")
        del user["role"]
        persons_service.update_person(person["id"], {"role": "manager"})
        ldap_service.provision_person(
            user, persons_service.get_person(person["id"])
        )
        self.assertEqual(Person.get(person["id"]).role.code, "manager")

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

    def test_sync_with_ldap_server_no_user_keeps_persons(self):
        settings = self.directory([])
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
            with self.assertRaises(SystemExit):
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
        settings = self.tls_settings(LDAP_SSL=False)
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
