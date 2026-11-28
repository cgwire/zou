"""
Access to the LDAP directory: connection, user search and the conversion of
directory entries into the dicts the person sync understands.
"""

import re
import ssl

import ldap3
from flask import current_app
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import to_dn

from zou.app import config
from zou.app.exceptions import (
    InactiveUserException,
    IsUserLimitReachedException,
    LdapAccountConflictException,
    LdapAmbiguousGroupException,
    LdapAmbiguousUserException,
    LdapGroupNotFoundException,
    PersonNotFoundException,
    WrongPasswordException,
)
from zou.app.services import persons_service

# Patched to ldap3.MOCK_SYNC in tests.
CLIENT_STRATEGY = ldap3.SYNC

# Seconds to wait for the directory to accept the connection.
# Active Directory returns at most 1000 entries for each search: read the
# entries page by page, below that limit.
SEARCH_PAGE_SIZE = 500
PAGED_RESULTS_CONTROL = "1.2.840.113556.1.4.319"
IN_CHAIN_RULE = "1.2.840.113556.1.4.1941"
# Role given by each role group setting, the highest role first: a user in
# several role groups gets the first one. A user in none gets "user".
ROLE_GROUPS = [
    ("admin", "LDAP_ADMIN_GROUP"),
    ("manager", "LDAP_MANAGER_GROUP"),
    ("supervisor", "LDAP_SUPERVISOR_GROUP"),
    ("client", "LDAP_CLIENT_GROUP"),
    ("vendor", "LDAP_VENDOR_GROUP"),
]
# An attribute name (letters, digits, hyphens) or an OID.
ATTRIBUTE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]*|[0-9]+(\.[0-9]+)+")


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
        "LDAP_USER_FILTER",
        "LDAP_VERIFY_CERTIFICATES",
        "LDAP_CA_FILE",
        "LDAP_NESTED_GROUPS",
        "LDAP_START_TLS",
        "LDAP_LOGIN_ATTRIBUTE",
        "LDAP_FIRST_NAME_ATTRIBUTE",
        "LDAP_LAST_NAME_ATTRIBUTE",
        "LDAP_EMAIL_ATTRIBUTE",
        "LDAP_THUMBNAIL_ATTRIBUTE",
        "LDAP_ADMIN_GROUP",
        "LDAP_MANAGER_GROUP",
        "LDAP_SUPERVISOR_GROUP",
        "LDAP_CLIENT_GROUP",
        "LDAP_VENDOR_GROUP",
        "LDAP_CONNECT_TIMEOUT",
        "LDAP_TIMEOUT",
        "LDAP_FOLLOW_REFERRALS",
        "LDAP_ALLOWED_REFERRAL_HOSTS",
    ]
    return {key: current_app.config[key] for key in keys}


def is_ad(settings):
    """
    Whether the directory is an Active Directory.
    """
    return bool(settings["LDAP_IS_AD"] or settings["LDAP_IS_AD_SIMPLE"])


def get_attribute_name(settings, key, default):
    """
    Name of the entry attribute set by the given setting, else the default.
    The names go into the search filters, so anything but an attribute name
    or an OID is refused.
    """
    attribute = settings[key].strip()
    if not attribute:
        return default
    if not ATTRIBUTE_NAME.fullmatch(attribute):
        raise ldap3.core.exceptions.LDAPInvalidFilterError(
            f"Invalid {key}: {attribute}"
        )
    return attribute


def get_login_attribute(settings):
    """
    Name of the entry attribute holding the desktop login: the configured
    one, else the usual one of the directory type.
    """
    if settings["LDAP_IS_AD_SIMPLE"]:
        default = "cn"
    elif settings["LDAP_IS_AD"]:
        default = "sAMAccountName"
    else:
        default = "uid"
    return get_attribute_name(settings, "LDAP_LOGIN_ATTRIBUTE", default)


def get_mapped_attributes(settings):
    """
    Names of the entry attributes holding the first name, the last name, the
    emails and the photo of a user.
    """
    return {
        "first_name": get_attribute_name(
            settings, "LDAP_FIRST_NAME_ATTRIBUTE", "givenName"
        ),
        "last_name": get_attribute_name(
            settings, "LDAP_LAST_NAME_ATTRIBUTE", "sn"
        ),
        "email": get_attribute_name(settings, "LDAP_EMAIL_ATTRIBUTE", "mail"),
        "thumbnail": get_attribute_name(
            settings,
            "LDAP_THUMBNAIL_ATTRIBUTE",
            "thumbnailPhoto" if is_ad(settings) else "jpegPhoto",
        ),
    }


def get_tls(settings):
    """
    TLS settings of the directory connection. Without certificate
    verification, ldap3 accepts any server certificate. The host name is
    sent (SNI) for the servers that pick their certificate from it.
    """
    if not settings["LDAP_VERIFY_CERTIFICATES"]:
        return None
    return ldap3.Tls(
        validate=ssl.CERT_REQUIRED,
        ca_certs_file=settings["LDAP_CA_FILE"] or None,
        sni=settings["LDAP_HOST"],
    )


def get_allowed_referral_hosts(settings):
    """
    Hosts a referral may send the connection to, with the same credentials:
    the directory host and the ones of LDAP_ALLOWED_REFERRAL_HOSTS. ldap3
    compares the host names as they are written, without any resolution.
    """
    hosts = [settings["LDAP_HOST"]]
    for host in settings["LDAP_ALLOWED_REFERRAL_HOSTS"].split(","):
        host = host.strip()
        if host and host not in hosts:
            hosts.append(host)
    return [(host, True) for host in hosts]


def get_server(settings, get_info=ldap3.ALL):
    """
    The directory server described by the settings. Reading its info (schema
    included) costs requests: ask for it only when it is needed.
    """
    return ldap3.Server(
        f"{settings['LDAP_HOST']}:{settings['LDAP_PORT']}",
        get_info=get_info,
        use_ssl=settings["LDAP_SSL"],
        tls=get_tls(settings),
        connect_timeout=settings["LDAP_CONNECT_TIMEOUT"],
        allowed_referral_hosts=get_allowed_referral_hosts(settings),
    )


def connect(settings, user, password, authentication, get_info=ldap3.ALL):
    """
    Open a connection to the directory and bind it with the given identity.
    With StartTLS, the connection is encrypted before the bind, and a
    failed StartTLS raises before any password is sent.
    """
    auto_bind = True
    if settings["LDAP_START_TLS"]:
        if settings["LDAP_SSL"]:
            raise ldap3.core.exceptions.LDAPSSLConfigurationError(
                "LDAP_SSL and LDAP_START_TLS cannot be both set"
            )
        auto_bind = ldap3.AUTO_BIND_TLS_BEFORE_BIND
    conn = ldap3.Connection(
        get_server(settings, get_info=get_info),
        user=user,
        password=password,
        authentication=authentication,
        raise_exceptions=True,
        auto_bind=auto_bind,
        receive_timeout=settings["LDAP_TIMEOUT"],
        auto_referrals=settings["LDAP_FOLLOW_REFERRALS"],
        client_strategy=CLIENT_STRATEGY,
    )
    if not conn.bound:
        # The mock strategies skip auto_bind.
        conn.bind()
    return conn


def open_service_connection(settings):
    """
    Bind to the directory with the configured service account. Refuse an
    empty password: some directories take it as an anonymous bind.
    """
    if not settings["LDAP_PASSWORD"]:
        raise ldap3.core.exceptions.LDAPPasswordIsMandatoryError(
            "LDAP_PASSWORD is not set"
        )
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


def build_member_of_filter(settings, group):
    """
    Active Directory filter matching the members of the given group DN, and
    of its subgroups with LDAP_NESTED_GROUPS.
    """
    group = escape_filter_chars(group)
    if settings["LDAP_NESTED_GROUPS"]:
        # LDAP_MATCHING_RULE_IN_CHAIN: members of the subgroups too.
        return f"(memberOf:{IN_CHAIN_RULE}:={group})"
    return f"(memberOf={group})"


def build_person_filter(settings, identity_filter=""):
    """
    Filter matching the person entries (restricted to the configured group on
    Active Directory), optionally narrowed by an identity filter. A
    configured user filter replaces the default object class filter.
    """
    user_filter = settings["LDAP_USER_FILTER"].strip()
    if user_filter:
        if not user_filter.startswith("("):
            user_filter = f"({user_filter})"
        parts = [user_filter]
    elif is_ad(settings):
        parts = ["(objectClass=person)", "(!(objectClass=computer))"]
    else:
        parts = ["(objectClass=person)"]
    if is_ad(settings):
        if len(settings["LDAP_GROUP"]) > 0:
            parts.append(
                build_member_of_filter(settings, settings["LDAP_GROUP"])
            )
    if identity_filter:
        parts.append(identity_filter)
    return f"(&{''.join(parts)})"


def get_user_attributes(settings):
    """
    Attributes to read on the user entries.
    """
    attributes = ["cn"]
    if is_ad(settings):
        if not settings["LDAP_IS_AD_SIMPLE"]:
            attributes += ["sAMAccountName"]
        attributes += ["userAccountControl", "objectGUID"]
    else:
        attributes += ["uid", "uniqueIdentifier", "organizationalStatus"]
    for attribute in [
        get_login_attribute(settings),
        *get_mapped_attributes(settings).values(),
    ]:
        if attribute not in attributes:
            attributes.append(attribute)
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
    excluded = [
        account.strip()
        for account in settings["LDAP_EXCLUDED_ACCOUNTS"].split(",")
        if account.strip()
    ]
    return desktop_login in excluded


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
    mapped = get_mapped_attributes(settings)
    desktop_login = get_desktop_login(entry, settings)
    if ad:
        ldap_uid = clean_value(entry.objectGUID)
    elif entry.uniqueIdentifier:
        ldap_uid = clean_value(entry.uniqueIdentifier)
    else:
        ldap_uid = None
    thumbnails = getattr(entry, mapped["thumbnail"]).raw_values
    if len(thumbnails) > 0 and len(thumbnails[0]) > 0:
        thumbnail = thumbnails[0]
    else:
        thumbnail = None

    emails = getattr(entry, mapped["email"]).values
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
        "first_name": clean_value(
            getattr(entry, mapped["first_name"]) or entry.cn
        ),
        "last_name": clean_value(getattr(entry, mapped["last_name"])),
        "email": emails[0].lower(),
        "emails": emails,
        "desktop_login": desktop_login,
        "thumbnail": thumbnail,
        "active": active,
        "ldap_uid": ldap_uid,
    }


def is_dn(group):
    """
    Whether a configured group is written as a DN rather than as a name.
    """
    return "=" in group


def get_group_member_dns(conn, settings, group=None):
    """
    Normalized DNs of the members of the given group, by default the
    configured group (OpenLDAP only). The group is a DN or a name; several
    groups with the same name are refused, not picked at random. None when
    no group is configured.
    """
    if group is None:
        group = settings["LDAP_GROUP"]
    if len(group) == 0:
        return None
    if settings["LDAP_NESTED_GROUPS"]:
        return get_nested_group_member_dns(conn, settings, group)
    if is_dn(group):
        try:
            conn.search(
                # Without the spaces after the commas, refused by ldap3.
                ",".join(part.strip() for part in to_dn(group)),
                "(objectClass=groupOfUniqueNames)",
                search_scope=ldap3.BASE,
                attributes=["uniqueMember"],
            )
        except (
            ldap3.core.exceptions.LDAPNoSuchObjectResult,
            ldap3.core.exceptions.LDAPInvalidDNSyntaxResult,
            ldap3.core.exceptions.LDAPInvalidDnError,
        ):
            raise LdapGroupNotFoundException(f"LDAP group not found: {group}")
    else:
        escaped = escape_filter_chars(group)
        conn.search(
            settings["LDAP_BASE_DN"],
            f"(&(objectClass=groupOfUniqueNames)(cn={escaped}))",
            attributes=["uniqueMember"],
        )
    if len(conn.entries) == 0:
        raise LdapGroupNotFoundException(f"LDAP group not found: {group}")
    if len(conn.entries) > 1:
        raise_ambiguous_group(
            group, [entry.entry_dn for entry in conn.entries]
        )
    return {normalize_dn(dn) for dn in conn.entries[0].uniqueMember.values}


def raise_ambiguous_group(group, dns):
    """
    Refuse a group name shared by several groups: whoever can create a
    group under the base DN could otherwise choose who gets its role.
    """
    raise LdapAmbiguousGroupException(
        f"Several LDAP groups are named {group}: {'; '.join(dns)}. "
        "Set the group DN instead."
    )


def get_nested_group_member_dns(conn, settings, group):
    """
    Normalized DNs of the members of the given group (a DN or a name) and
    of its subgroups, at any depth (OpenLDAP only). The groups are read in
    one search under the base DN, then expanded in memory.
    """
    groups = {}
    roots = []
    wanted_dn = normalize_dn(group) if is_dn(group) else None
    for entry in paged_search(
        conn,
        settings["LDAP_BASE_DN"],
        "(objectClass=groupOfUniqueNames)",
        ["cn", "uniqueMember"],
    ):
        dn = normalize_dn(entry.entry_dn)
        groups[dn] = [
            normalize_dn(member) for member in entry.uniqueMember.values
        ]
        if wanted_dn is not None:
            if dn == wanted_dn:
                roots.append(entry.entry_dn)
        elif group.lower() in [name.lower() for name in entry.cn.values]:
            roots.append(entry.entry_dn)
    if len(roots) == 0:
        raise LdapGroupNotFoundException(f"LDAP group not found: {group}")
    if len(roots) > 1:
        raise_ambiguous_group(group, roots)
    root = normalize_dn(roots[0])
    members = set()
    seen_groups = {root}
    to_expand = [root]
    while to_expand:
        for member in groups[to_expand.pop()]:
            if member in groups:
                if member not in seen_groups:
                    seen_groups.add(member)
                    to_expand.append(member)
            else:
                members.add(member)
    return members


def paged_search(conn, base_dn, search_filter, attributes):
    """
    Entries of a search read page by page, so that the server size limit
    does not cut the result. A server without paging support returns
    everything in the first page.
    """
    entries = []
    cookie = None
    while True:
        conn.search(
            base_dn,
            search_filter,
            attributes=attributes,
            paged_size=SEARCH_PAGE_SIZE,
            paged_cookie=cookie,
        )
        entries.extend(conn.entries)
        cookie = (
            conn.result.get("controls", {})
            .get(PAGED_RESULTS_CONTROL, {})
            .get("value", {})
            .get("cookie")
        )
        if not cookie:
            return entries


def search_users(conn, settings):
    """
    Read the user entries of the directory (or of the configured group) and
    return them as dicts the person sync understands. Raise when the
    configured group is missing: an empty result would make the sync
    deactivate every LDAP person.
    """
    group_members = None
    if is_ad(settings):
        check_group_exists(conn, settings)
    else:
        group_members = get_group_member_dns(conn, settings)
    role_members = get_role_member_dns(conn, settings)
    users = []
    for entry in paged_search(
        conn,
        settings["LDAP_BASE_DN"],
        build_person_filter(settings),
        get_user_attributes(settings),
    ):
        if is_excluded(settings, get_desktop_login(entry, settings)):
            continue
        if (
            group_members is not None
            and normalize_dn(entry.entry_dn) not in group_members
        ):
            continue
        user = entry_to_user(entry, settings)
        if role_members is not None:
            user["role"] = get_role(entry.entry_dn, role_members)
        users.append(user)
    return users


def check_group_exists(conn, settings, group=None):
    """
    Raise when the given group, by default the configured group, is not in
    the directory. Nothing to check when no group is configured.
    """
    if group is None:
        group = settings["LDAP_GROUP"]
    if len(group) == 0:
        return
    if is_ad(settings):
        try:
            conn.search(group, "(objectClass=group)", search_scope=ldap3.BASE)
        except (
            ldap3.core.exceptions.LDAPNoSuchObjectResult,
            ldap3.core.exceptions.LDAPInvalidDNSyntaxResult,
            ldap3.core.exceptions.LDAPInvalidDnError,
        ):
            raise LdapGroupNotFoundException(f"LDAP group not found: {group}")
        if len(conn.entries) == 0:
            raise LdapGroupNotFoundException(f"LDAP group not found: {group}")
    else:
        get_group_member_dns(conn, settings, group)


def get_role_groups(settings):
    """
    Configured role groups, as (role, group) pairs, the highest role first.
    """
    return [
        (role, settings[key].strip())
        for role, key in ROLE_GROUPS
        if settings[key].strip()
    ]


def get_role_member_dns(conn, settings):
    """
    Normalized DNs of the members of each configured role group, as
    (role, DNs) pairs, the highest role first. None when no role group is
    configured. Raise when a role group is missing: its members would lose
    their role.
    """
    role_groups = get_role_groups(settings)
    if len(role_groups) == 0:
        return None
    role_members = []
    for role, group in role_groups:
        if is_ad(settings):
            check_group_exists(conn, settings, group)
            members = {
                normalize_dn(entry.entry_dn)
                for entry in paged_search(
                    conn,
                    settings["LDAP_BASE_DN"],
                    build_member_of_filter(settings, group),
                    ldap3.NO_ATTRIBUTES,
                )
            }
        else:
            members = get_group_member_dns(conn, settings, group)
        role_members.append((role, members))
    return role_members


def get_role(entry_dn, role_members):
    """
    Role of the entry with given DN: the one of its highest role group, else
    "user".
    """
    dn = normalize_dn(entry_dn)
    for role, members in role_members:
        if dn in members:
            return role
    return "user"


def get_entry_role(conn, settings, entry):
    """
    Role of a single directory entry, read from the role groups. None when
    no role group is configured. Raise when a role group is missing.
    """
    role_groups = get_role_groups(settings)
    if len(role_groups) == 0:
        return None
    for role, group in role_groups:
        if is_ad(settings):
            check_group_exists(conn, settings, group)
            conn.search(
                entry.entry_dn,
                build_member_of_filter(settings, group),
                search_scope=ldap3.BASE,
                attributes=ldap3.NO_ATTRIBUTES,
            )
            if len(conn.entries) > 0:
                return role
        elif normalize_dn(entry.entry_dn) in get_group_member_dns(
            conn, settings, group
        ):
            return role
    return "user"


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
        email = get_mapped_attributes(settings)["email"]
        if is_ad(settings):
            return f"(|({email}={escaped})(userPrincipalName={escaped}))"
        return f"({email}={escaped})"
    return f"({get_login_attribute(settings)}={escaped})"


def search_entries(conn, settings, identity_filter, group_members=None):
    """
    Entries matching the identity filter anywhere under the base DN. When
    group members are given (normalized DNs), keep only their entries.
    """
    conn.search(
        settings["LDAP_BASE_DN"],
        build_person_filter(settings, identity_filter),
        attributes=get_user_attributes(settings),
    )
    entries = list(conn.entries)
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
    group_members = None
    if is_ad(settings):
        check_group_exists(conn, settings)
    else:
        group_members = get_group_member_dns(conn, settings)
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
        entries = search_entries(
            conn, settings, identity_filter, group_members
        )
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
    if is_ad(settings) and not settings["LDAP_IS_AD_SIMPLE"]:
        user = f"{settings['LDAP_DOMAIN']}\\{entry.sAMAccountName}"
        authentication = ldap3.NTLM
    else:
        user = entry.entry_dn
        authentication = ldap3.SIMPLE
    check_bind(settings, user, authentication, password)


def check_legacy_password(settings, desktop_login, password):
    """
    Check the password of a person by binding with an identity built from
    its desktop login, without any search: the legacy LDAP login.
    """
    if settings["LDAP_IS_AD_SIMPLE"]:
        user = f"cn={desktop_login},{settings['LDAP_BASE_DN']}"
        authentication = ldap3.SIMPLE
    elif settings["LDAP_IS_AD"]:
        user = f"{settings['LDAP_DOMAIN']}\\{desktop_login}"
        authentication = ldap3.NTLM
    else:
        user = f"uid={desktop_login},{settings['LDAP_BASE_DN']}"
        authentication = ldap3.SIMPLE
    check_bind(settings, user, authentication, password)


def check_bind(settings, user, authentication, password):
    """
    Bind with the given identity and password, through the same connection
    settings as the service account (TLS, timeouts). An empty password makes
    an unauthenticated bind (RFC 4513, 5.1.2) that some directories accept:
    it is refused before any bind.
    """
    if not password:
        raise WrongPasswordException()
    try:
        conn = connect(
            settings, user, password, authentication, get_info=ldap3.NONE
        )
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


def is_role_managed(user, person):
    """
    Whether the directory sets the role of the person: a role group is
    configured and the person is an LDAP person, not a protected account.
    """
    return (
        "role" in user
        and person["is_generated_from_ldap"]
        and person["email"] not in config.PROTECTED_ACCOUNTS
    )


def get_sync_conflict(person):
    """
    Why the sync must leave the given person untouched, or None. Protected
    accounts must be local accounts, out of the directory. A local account
    matching a directory user is never taken over: its owner may not be
    the directory user.
    """
    if person["email"] in config.PROTECTED_ACCOUNTS:
        return (
            f"{person['email']} is in PROTECTED_ACCOUNTS: protected "
            "accounts must be local accounts, out of the directory sync"
        )
    if not person["is_generated_from_ldap"]:
        return (
            f"{person['email']} is a local account that matches a "
            "directory user"
        )
    return None


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
            role=user.get("role", "user"),
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
    if user["email"] != person["email"]:
        try:
            holder = persons_service.get_person_by_email(user["email"])
        except PersonNotFoundException:
            holder = None
        if holder is not None and holder["id"] != person["id"]:
            current_app.logger.error(
                f"LDAP login refused for {user['desktop_login']}: the "
                f"directory email belongs to person {holder['id']}, not to "
                f"person {person['id']}."
            )
            raise LdapAccountConflictException()
    if person["ldap_uid"] and person["ldap_uid"] != user["ldap_uid"]:
        current_app.logger.warning(
            f"ldap_uid of person {person['id']} changed from "
            f"{person['ldap_uid']} to {user['ldap_uid']}."
        )
    fields = {
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "active": user["active"],
        "is_generated_from_ldap": True,
        "desktop_login": user["desktop_login"],
        "ldap_uid": user["ldap_uid"],
    }
    if is_role_managed(user, person):
        fields["role"] = user["role"]
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
