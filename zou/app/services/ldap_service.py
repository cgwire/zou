"""
Access to the LDAP directory: connection, user search and the conversion of
directory entries into the dicts the person sync understands.
"""

import ldap3
from flask import current_app
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import to_dn

from zou.app import config
from zou.app.exceptions import (
    InactiveUserException,
    IsUserLimitReachedException,
    LdapAccountConflictException,
    LdapAmbiguousUserException,
    LdapGroupNotFoundException,
    PersonNotFoundException,
    WrongPasswordException,
)
from zou.app.services import persons_service

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
    return {key: current_app.config[key] for key in keys}


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


def check_group_exists(conn, settings):
    """
    Raise when the configured group is not in the directory. Nothing to check
    when no group is configured.
    """
    if len(settings["LDAP_GROUP"]) == 0:
        return
    if is_ad(settings):
        try:
            conn.search(
                settings["LDAP_GROUP"],
                "(objectClass=group)",
                search_scope=ldap3.BASE,
            )
        except ldap3.core.exceptions.LDAPNoSuchObjectResult:
            raise LdapGroupNotFoundException(
                f"LDAP group not found: {settings['LDAP_GROUP']}"
            )
        if len(conn.entries) == 0:
            raise LdapGroupNotFoundException(
                f"LDAP group not found: {settings['LDAP_GROUP']}"
            )
    else:
        get_group_member_dns(conn, settings)


def build_identity_filter(settings, identifier, ldap_uid=None):
    """
    Filter matching the entry of the given identifier (login or email), or of
    the given directory unique id.
    """
    escaped = escape_filter_chars(identifier)
    if ldap_uid is not None:
        escaped_uid = escape_filter_chars(ldap_uid)
        if is_ad(settings):
            return f"(objectGUID={escaped_uid})"
        return f"(uniqueIdentifier={escaped_uid})"
    if "@" in identifier:
        if is_ad(settings):
            return f"(|(mail={escaped})(userPrincipalName={escaped}))"
        return f"(mail={escaped})"
    return f"({get_login_attribute(settings)}={escaped})"


def search_entries(conn, settings, identity_filter):
    """
    Entries matching the identity filter anywhere under the base DN (and in
    the configured group on OpenLDAP).
    """
    conn.search(
        settings["LDAP_BASE_DN"],
        build_person_filter(settings, identity_filter),
        attributes=get_user_attributes(settings),
    )
    entries = list(conn.entries)
    if not is_ad(settings):
        group_members = get_group_member_dns(conn, settings)
        if group_members is not None:
            entries = [
                entry
                for entry in entries
                if normalize_dn(entry.entry_dn) in group_members
            ]
    return entries


def find_user_entry(
    conn, settings, identifier, ldap_uid=None, desktop_login=None
):
    """
    Find the directory entry of a user anywhere under the base DN, by its
    directory unique id first, then by the desktop login of the known
    person, then by the typed login or email. Return None when none of
    them matches.
    """
    check_group_exists(conn, settings)
    identity_filters = []
    if ldap_uid:
        identity_filters.append(
            build_identity_filter(settings, identifier, ldap_uid)
        )
    if desktop_login:
        login = escape_filter_chars(desktop_login)
        identity_filters.append(f"({get_login_attribute(settings)}={login})")
    identity_filters.append(build_identity_filter(settings, identifier))
    entries = []
    for identity_filter in identity_filters:
        entries = search_entries(conn, settings, identity_filter)
        if len(entries) > 0:
            break
    if len(entries) == 0:
        return None
    if len(entries) > 1:
        raise LdapAmbiguousUserException(
            f"Several LDAP entries match: {identifier}"
        )
    return entries[0]


def check_user_password(settings, entry, password):
    """
    Check the password of a directory entry by binding with it.
    """
    if not password:
        raise WrongPasswordException()
    if is_ad(settings) and not settings["LDAP_IS_AD_SIMPLE"]:
        user = f"{settings['LDAP_DOMAIN']}\\{entry.sAMAccountName}"
        authentication = ldap3.NTLM
    else:
        user = entry.entry_dn
        authentication = ldap3.SIMPLE
    try:
        conn = connect(settings, user, password, authentication)
    except ldap3.core.exceptions.LDAPInvalidCredentialsResult:
        raise WrongPasswordException()
    conn.unbind()


def find_ldap_person(user):
    """
    Return the person matching a directory user (by LDAP uid, then desktop
    login, then each email) or None. Refuse local accounts and protected
    accounts.
    """
    person = None
    try:
        person = persons_service.get_person_by_ldap_uid(user["ldap_uid"])
    except PersonNotFoundException:
        try:
            person = persons_service.get_person_by_desktop_login(
                user["desktop_login"]
            )
        except PersonNotFoundException:
            for mail in user["emails"]:
                try:
                    person = persons_service.get_person_by_email(mail)
                    break
                except PersonNotFoundException:
                    pass
    if person is not None and (
        not person["is_generated_from_ldap"]
        or person["email"] in config.PROTECTED_ACCOUNTS
    ):
        current_app.logger.error(
            f"LDAP login refused for {user['desktop_login']}: "
            f"person {person['id']} is not managed by LDAP."
        )
        raise LdapAccountConflictException()
    return person


def provision_person(user, person=None):
    """
    Create the person of a directory user, or update the existing one.
    Return the person id.
    """
    if person is None:
        if not user["active"]:
            raise InactiveUserException()
        if persons_service.is_user_limit_reached():
            raise IsUserLimitReachedException()
        created = persons_service.create_person(
            user["email"],
            "default".encode("utf-8"),
            user["first_name"],
            user["last_name"],
            desktop_login=user["desktop_login"],
            is_generated_from_ldap=True,
            ldap_uid=user["ldap_uid"],
            active=True,
        )
        return created["id"]

    if (
        not person["active"]
        and user["active"]
        and persons_service.is_user_limit_reached()
    ):
        raise IsUserLimitReachedException()
    fields = {
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "active": user["active"],
        "is_generated_from_ldap": True,
        "desktop_login": user["desktop_login"],
        "ldap_uid": user["ldap_uid"],
    }
    if any(person[key] != value for key, value in fields.items()):
        persons_service.update_person(
            person["id"], fields, bypass_protected_accounts=False
        )
    return person["id"]


def deactivate_person(person):
    """
    Disable a person that is no longer active in the directory.
    """
    if person["active"]:
        persons_service.update_person(person["id"], {"active": False})
        current_app.logger.info(
            f"User {person['desktop_login']} disabled (inactive in LDAP)."
        )
