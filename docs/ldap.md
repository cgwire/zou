# LDAP

Authentication can be managed through a LDAP (or Active Directory) server. It
allows you to start using Kitsu directly with the accounts listed in your LDAP.


## Activate LDAP

To activate LDAP, you must set the *AUTH\_STRATEGY* environment variable (in /etc/zou/zou.env) with
the following value:

```
AUTH_STRATEGY=auth_remote_ldap
```

*NB: If you are using Active directory you must set the `IS_LDAP` flag to true.* 


## Required environment variables

Once this authentication scheme selected, you must set the following variables:

* `LDAP_HOST` (default: "127.0.0.1"): the IP address of your LDAP server.
* `LDAP_PORT` (default: "389"): the listening port of your LDAP server.
* `LDAP_BASE_DN` (default: "CN=Users,DC=studio,DC=local"): the base domain of
  your LDAP configuration.
* `LDAP_DOMAIN` (default: "studio.local"): the domain used for your LDAP
  authentication.
* `LDAP_FALLBACK` (default: "False"): Set to True if you want to allow admins
  to fallback on default auth strategy when the LDAP server is down.
* `LDAP_IS_AD` (default: "False"): Set to True if you use LDAP with active directory.

Example:

```
LDAP_HOST=192.168.1.10
LDAP_PORT=389
LDAP_BASE_DN=CN=Users,DC=mystudio,DC=local
LDAP_DOMAIN=mystudio.com
LDAP_FALLBACK=True
```


## User list synchronization

You will have to synchronize the user list with users from the LDAP. A good
option is to handle it via a Python script. But, to makes things simpler, 
we added a command in `zou` binary to do it for you. 
It's a one way sync. We consider that Zou should not alter your LDAP user list.

This command requires additional environment variables:

* `LDAP_USER`: Username of a LDAP user that can lists all LDAP users.
* `LDAP_PASSWORD`: Password of a LDAP user that can lists all LDAP users.
* `LDAP_EMAIL_DOMAIN`: User email will be built with username + @ + email domain.
* `LDAP_EXCLUDED_ACCOUNTS`: Set the list of people that should not be created
  in Kitsu API (Zou).

Example:

```
LC_ALL=C.UTF-8 \
LANG=C.UTF-8 \
DB_HOST=yourdbhost \
LDAP_HOST=192.168.1.10
LDAP_PORT=389 \
LDAP_BASE_DN=CN=Users,DC=mystudio,DC=local \
LDAP_DOMAIN=mystudio.com \
LDAP_USER=myusername \
LDAP_PASSWORD=myuserpassword \
LDAP_EMAIL_DOMAIN=mystudio.com \
LDAP_EXCLUDED_ACCOUNTS=Administrator,TestAccount \
zou sync-with-ldap-server
```


## Note about Kitsu

When LDAP is activated, it is not possible anymore to change following user
information through the Kitsu web UI:

* email
* first name
* last name
* avatar
