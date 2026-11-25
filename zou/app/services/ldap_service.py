"""
Access to the LDAP directory: connection, user search and the conversion of
directory entries into the dicts the person sync understands.
"""

import ldap3
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import to_dn

from zou.app import app
from zou.app.exceptions import LdapGroupNotFoundException

# Patched to ldap3.MOCK_SYNC in tests.
CLIENT_STRATEGY = ldap3.SYNC


def get_settings():
    """
    The directory connection settings, from the configuration.
    """
    keys = [
        "LDAP_HOST",
        "LDAP_PORT",
        "LDAP_PASSWORD",
        "LDAP_BASE_DN",
        "LDAP_DOMAIN",
        "LDAP_USER",
        "LDAP_GROUP",
        "LDAP_SSL",
        "EMAIL_DOMAIN",
        "LDAP_EXCLUDED_ACCOUNTS",
        "LDAP_IS_AD",
        "LDAP_IS_AD_SIMPLE",
        "LDAP_SEARCH_BIND",
    ]
    return {key: app.config[key] for key in keys}


def is_ad(settings):
    """
    Whether the directory is an Active Directory.
    """
    return bool(settings["LDAP_IS_AD"] or settings["LDAP_IS_AD_SIMPLE"])


def get_login_attribute(settings):
    """
    Name of the entry attribute holding the desktop login.
    """
    if settings["LDAP_IS_AD_SIMPLE"]:
        return "cn"
    elif settings["LDAP_IS_AD"]:
        return "sAMAccountName"
    return "uid"


def get_server(settings):
    """
    The directory server described by the settings.
    """
    return ldap3.Server(
        f"{settings['LDAP_HOST']}:{settings['LDAP_PORT']}",
        get_info=ldap3.ALL,
        use_ssl=settings["LDAP_SSL"],
    )


def connect(settings, user, password, authentication):
    """
    Open a connection to the directory and bind it with the given identity.
    """
    conn = ldap3.Connection(
        get_server(settings),
        user=user,
        password=password,
        authentication=authentication,
        raise_exceptions=True,
        auto_bind=True,
        client_strategy=CLIENT_STRATEGY,
    )
    if not conn.bound:
        # The mock strategies skip auto_bind.
        conn.bind()
    return conn


def open_service_connection(settings):
    """
    Bind to the directory with the configured service account.
    """
    if settings["LDAP_IS_AD_SIMPLE"]:
        user = settings["LDAP_USER"]
        authentication = ldap3.SIMPLE
    elif settings["LDAP_IS_AD"]:
        user = f"{settings['LDAP_DOMAIN']}\\{settings['LDAP_USER']}"
        authentication = ldap3.NTLM
    elif "=" in settings["LDAP_USER"]:
        # LDAP_USER is already a full bind DN, use it as is. OpenLDAP
        # admin accounts often live outside the users base DN
        # (e.g. cn=admin,dc=studio,dc=local).
        user = settings["LDAP_USER"]
        authentication = ldap3.SIMPLE
    else:
        user = f"uid={settings['LDAP_USER']},{settings['LDAP_BASE_DN']}"
        authentication = ldap3.SIMPLE
    return connect(settings, user, settings["LDAP_PASSWORD"], authentication)


def build_person_filter(settings, identity_filter=""):
    """
    Filter matching the person entries (restricted to the configured group on
    Active Directory), optionally narrowed by an identity filter.
    """
    parts = ["(objectClass=person)"]
    if is_ad(settings):
        parts.append("(!(objectClass=computer))")
        if len(settings["LDAP_GROUP"]) > 0:
            group = escape_filter_chars(settings["LDAP_GROUP"])
            parts.append(f"(memberOf={group})")
    if identity_filter:
        parts.append(identity_filter)
    return f"(&{''.join(parts)})"


def get_user_attributes(settings):
    """
    Attributes to read on the user entries.
    """
    attributes = ["givenName", "sn", "mail", "cn"]
    if is_ad(settings):
        if settings["LDAP_IS_AD_SIMPLE"]:
            attributes += ["cn"]
        else:
            attributes += ["sAMAccountName"]
        attributes += [
            "thumbnailPhoto",
            "userAccountControl",
            "objectGUID",
        ]
    else:
        attributes += [
            "uid",
            "jpegPhoto",
            "uniqueIdentifier",
            "organizationalStatus",
        ]
    return attributes


def clean_value(value):
    """
    String form of an attribute value, empty for an empty attribute.
    """
    cleaned_value = str(value)
    if cleaned_value == "[]":
        cleaned_value = ""
    return cleaned_value


def normalize_dn(dn):
    """
    Canonical form of a DN, to compare DNs regardless of case and spacing.
    """
    return ",".join(part.strip().lower() for part in to_dn(dn))


def is_excluded(settings, desktop_login):
    """
    Whether the login is in the list of accounts to leave out.
    """
    return desktop_login in settings["LDAP_EXCLUDED_ACCOUNTS"].split(",")


def get_desktop_login(entry, settings):
    """
    Desktop login of a directory entry.
    """
    return clean_value(getattr(entry, get_login_attribute(settings)))


def entry_to_user(entry, settings):
    """
    Convert a directory entry into a dict the person sync understands.
    """
    ad = is_ad(settings)
    desktop_login = get_desktop_login(entry, settings)
    if ad:
        ldap_uid = clean_value(entry.objectGUID)
    elif entry.uniqueIdentifier:
        ldap_uid = clean_value(entry.uniqueIdentifier)
    else:
        ldap_uid = None
    thumbnails = (entry.thumbnailPhoto if ad else entry.jpegPhoto).raw_values
    if len(thumbnails) > 0 and len(thumbnails[0]) > 0:
        thumbnail = thumbnails[0]
    else:
        thumbnail = None

    emails = entry.mail.values
    if len(emails) == 0:
        emails = [f"{desktop_login}@{settings['EMAIL_DOMAIN']}"]
    else:

        def sort_mails(email):
            if email == desktop_login:
                return -2
            elif settings["EMAIL_DOMAIN"] in email:
                return -1
            else:
                return 0

        emails = sorted(emails, key=sort_mails)

    if ad:
        active = bool(entry.userAccountControl.value & 2) is False
    elif entry.organizationalStatus:
        active = entry.organizationalStatus.value.lower() == "active"
    else:
        active = False

    return {
        "first_name": clean_value(entry.givenName or entry.cn),
        "last_name": clean_value(entry.sn),
        "email": emails[0].lower(),
        "emails": emails,
        "desktop_login": desktop_login,
        "thumbnail": thumbnail,
        "active": active,
        "ldap_uid": ldap_uid,
    }


def get_group_member_dns(conn, settings):
    """
    Normalized DNs of the members of the configured group (OpenLDAP only).
    None when no group is configured.
    """
    if len(settings["LDAP_GROUP"]) == 0:
        return None
    group = escape_filter_chars(settings["LDAP_GROUP"])
    conn.search(
        settings["LDAP_BASE_DN"],
        f"(&(objectClass=groupOfUniqueNames)(cn={group}))",
        attributes=["uniqueMember"],
    )
    if len(conn.entries) == 0:
        raise LdapGroupNotFoundException(
            f"LDAP group not found: {settings['LDAP_GROUP']}"
        )
    return {normalize_dn(dn) for dn in conn.entries[0].uniqueMember.values}


def search_users(conn, settings):
    """
    Read the user entries of the directory (or of the configured group) and
    return them as dicts the person sync understands.
    """
    group_members = None
    if not is_ad(settings):
        group_members = get_group_member_dns(conn, settings)
    conn.search(
        settings["LDAP_BASE_DN"],
        build_person_filter(settings),
        attributes=get_user_attributes(settings),
    )
    users = []
    for entry in conn.entries:
        if is_excluded(settings, get_desktop_login(entry, settings)):
            continue
        if (
            group_members is not None
            and normalize_dn(entry.entry_dn) not in group_members
        ):
            continue
        users.append(entry_to_user(entry, settings))
    return users
