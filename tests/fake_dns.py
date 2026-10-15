"""
Stand-in for the dnspython resolver email_validator queries when it
checks deliverability, so that no test reaches the network.

Every domain answers with one MX record, so reserved test domains such
as example.com (published with a Null MX) stay usable in fixtures.
NO_MX_DOMAIN answers no record at all, like a domain that does not
receive email: the library runs its MX, then A and AAAA fallbacks, and
refuses the address.
"""

from types import SimpleNamespace

import dns.resolver

NO_MX_DOMAIN = "no-mx.example.com"


class FakeDnsResolver:
    lifetime = None

    def resolve(self, qname, rdtype):
        if qname == NO_MX_DOMAIN:
            raise dns.resolver.NoAnswer()
        if rdtype != "MX":
            raise ValueError(f"Unexpected DNS query type: {rdtype}")
        return [SimpleNamespace(preference=10, exchange=f"mx.{qname}.")]
