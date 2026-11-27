import uuid
from unittest import mock

import ldap3

from zou.app.services import ldap_service

BASE_DN = "dc=studio,dc=local"
SERVICE_DN = f"cn=svc,{BASE_DN}"


class LdapDirectoryMixin:
    """
    Builds an in-memory LDAP directory and points ldap_service at it.
    """

    def directory(self, entries, **settings_overrides):
        """
        Seed a mock directory with (dn, attributes) entries, patch
        ldap_service to use it and return the matching settings.
        """
        server = ldap3.Server("mock", get_info=ldap3.OFFLINE_AD_2012_R2)
        seed = ldap3.Connection(
            server,
            user=SERVICE_DN,
            password="p",
            client_strategy=ldap3.MOCK_SYNC,
        )
        seed.strategy.add_entry(
            SERVICE_DN,
            {"userPassword": "p", "objectClass": "applicationProcess"},
        )
        for dn, attributes in entries:
            seed.strategy.add_entry(dn, attributes)
        patchers = [
            mock.patch.object(ldap_service, "get_server", return_value=server),
            mock.patch.object(
                ldap_service, "CLIENT_STRATEGY", ldap3.MOCK_SYNC
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        settings = {
            "LDAP_HOST": "mock",
            "LDAP_PORT": "389",
            "LDAP_BASE_DN": BASE_DN,
            "LDAP_USER": SERVICE_DN,
            "LDAP_PASSWORD": "p",
            "LDAP_DOMAIN": "studio.local",
            "LDAP_GROUP": "",
            "LDAP_SSL": False,
            "EMAIL_DOMAIN": "studio.local",
            "LDAP_EXCLUDED_ACCOUNTS": "",
            "LDAP_IS_AD": False,
            "LDAP_IS_AD_SIMPLE": True,
            "LDAP_SEARCH_BIND": False,
            "LDAP_USER_FILTER": "",
            "LDAP_VERIFY_CERTIFICATES": False,
            "LDAP_CA_FILE": "",
            "LDAP_NESTED_GROUPS": False,
            "LDAP_START_TLS": False,
            "LDAP_LOGIN_ATTRIBUTE": "",
        }
        settings.update(settings_overrides)
        return settings


def ad_user(login, **attributes):
    """
    Attributes of an active Active Directory user entry.
    """
    entry = {
        "objectClass": ["person", "user"],
        "cn": login,
        "sn": login.title(),
        "givenName": "Given",
        "mail": f"{login}@studio.local",
        "objectGUID": uuid.uuid4().bytes_le,
        "userAccountControl": 512,
    }
    entry.update(attributes)
    return entry


def openldap_person(login):
    """
    Attributes of an active OpenLDAP person entry.
    """
    return {
        "objectClass": ["person", "inetOrgPerson"],
        "uid": login,
        "cn": login,
        "sn": login.title(),
        "givenName": "Given",
        "mail": f"{login}@studio.local",
        "organizationalStatus": "active",
    }


def openldap_group(name, members):
    """
    Attributes of an OpenLDAP group with the given member DNs.
    """
    return {
        "objectClass": "groupOfUniqueNames",
        "cn": name,
        "uniqueMember": members,
    }
