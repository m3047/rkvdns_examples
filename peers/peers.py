#!/usr/bin/python3
# Copyright (c) 2022 by Fred Morris Tacoma WA
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Netflow Peers.

Command line:

    peers.py <fqdn> [<rkvd-domain> [<dns-server>]] {+debug}
    
Lists, symbolically when possible, the netflow peers of the specified host.

    fqdn         This is the (resolvable) fully qualified hostname, or an address.
    rkvd-domain  The domain that rkvdns serves responses under.
    dns-server   This is the (optional) dns server to use for DNS requests.
    debug        If specified (preceded by '+') then intermediate results are
                 printed to STDOUT.
    
Corresponding entries can be set in an optional `configuration.py`:

    DOMAIN      Akin to a search list, this is the domain to be appended to the
                hostname/fqdn.
    RKVDNS      The domain that rkvdns serves responses under. See below.
    SERVER      The address of the dns server.
    
Refer to the documentation for RKVDNS. Our query will be fabricated into a domain
name looking something like

    address;*;flow.keys.proxy.redis.example.com

The RKVDNS domain in this example is proxy.redis.example.com

Order of Operation
------------------

1) fqdn / hostname is resolved.

    Unless the name parses as an IPv4 or IPv6 address, it is resolved with A / AAAA
    queries to identify the actual address. IPv6 is preferred.
    
    If DOMAIN is defined, then it is appended to the fqdn (unless it matches the
    righthand side of the fqdn) before attempting DNS resolution.
    
2) Uses rkvdns to query a redis database containing flow information.

    There is a Redis database with keys conforming to the following pattern:
    
        <client>;<peer>;<port>;flow
        
    Notice that this is case sensitive, that is "flow" is lower case.
    
    The address established in step 1 is queried for as client keys:
    
        "<resolved-address>;*;flow"
    
    The Redis database is maintained by pcap-agent.
    (https://github.com/m3047/shodohflo/blob/master/agents/pcap_agent.py)
    
3) Reverse (PTR) lookups are performed for each <peer>

    Straightforward. Personally however I'm using a nameserver which offers
    synthesized PTR records, increasing my coverage to over 90%; good luck if
    you even get 50% accuracy with normal DNS.
    
    I synthesize PTR records with Rear View RPZ.
    (https://github.com/m3047/rear_view_rpz)


Assumptions
-----------

The RKVDNS instance is configured with CASE_FOLDING = 'lower'.
"""

import sys

from dns.resolver import Resolver
import dns.rdatatype as rdtype
import dns.rdataclass as rdclass
from dns.exception import DNSException
import dns.rcode

from ipaddress import ip_address

DOMAIN = None
RKVDNS = None
SERVER = None
# NOTE: See pydoc for information about CASE_FOLDING.
QUERY = "{};*;flow"
ESCAPED = '.;'

def lart(msg=None, help='peers fqdn [rkvdns-domain [dns-server]]'):
    if msg:
        print(msg, file=sys.stderr)
    if help:
        print(help, file=sys.stderr)
    sys.exit(1)

try:
    from configuration import *
except ImportError:
    pass
except Exception as e:
    lart('{}: {}'.format(type(e).__name__, e))

if DOMAIN is not None:
    DOMAIN = DOMAIN.strip('.').lower().split('.')
else:
    DOMAIN = []

if RKVDNS is not None:
    RKVDNS = RKVDNS.strip('.').lower()
else:
    RKVDNS = ''

ADDRESS_TYPES = (rdtype.AAAA, rdtype.A)
ESCAPED = { c for c in ESCAPED }
    
def escape(qname):
    """Escape . and ;"""
    for c in ESCAPED:
        qname = qname.replace(c, '\\{}'.format(c))
    return qname

def main( target, rkvdns, resolver, debug ):
    
    if debug:
        print('Looking up {} using server(s) {}'.format(target, resolver.nameservers))
        
    # Look up the target.
    addresses = []
    for qtype in ADDRESS_TYPES:

        try:
            resp = None
            resp = resolver.query( target + '.', qtype )
        except DNSException:
            pass

        if resp is None or resp.response.rcode() != dns.rcode.NOERROR:
            continue
        
        for rset in resp.response.answer:
            if rset.rdtype not in ADDRESS_TYPES:
                continue
            addresses += [ rr.to_text() for rr in rset ]

    if not addresses:
        try:
            addresses = [str(ip_address(target))]
        except:
            pass
    if not addresses:
            lart('Failed to resolve {}'.format(target), help=None)
    
    if debug:
        print('Addresses:\n  {}'.format('\n  '.join(addresses)))
        
    # Get peers.
    peers = []
    for address in addresses:
        qname = '{}.keys.{}.'.format( escape( QUERY.format(address) ), rkvdns)
        if debug:
            print('Querying: {}'.format(qname))
        try:
            resp = None
            resp = resolver.query( qname, rdtype.TXT)
        except DNSException:
            pass
        
        if resp is None or resp.response.rcode() != dns.rcode.NOERROR:
            continue

        for rset in resp.response.answer:
            if rset.rdtype != rdtype.TXT:
                continue
            peers += [ rr.to_text().strip('"').split(';')[1] for rr in rset ]

    if debug:
        print('Peers:\n  {}'.format('\n  '.join(peers)))

    # Do reverse lookups.
    for i in range(len(peers)):
        addr = ip_address(peers[i])
        try:
            resp = None
            resp = resolver.query(addr.reverse_pointer, rdtype.PTR)
        except DNSException:
            print(str(addr))
            continue
        
        if resp is None or resp.response.rcode() != dns.rcode.NOERROR:
            print(str(addr))
            continue

        for rset in resp.response.answer:
            if rset.rdtype != rdtype.PTR:
                continue
            printed = False
            for rr in rset:
                print(rr.to_text())
                printed = True
            if not printed:
                print(str(addr))
    
    return

if __name__ == '__main__':
    
    argv = sys.argv
    if argv[-1].startswith('+'):
        debug = argv.pop()[1:]
        if debug != 'debug':
            lart('Unrecognized option "{}"'.format(debug))
    else:
        debug = ''

    if len(argv) < 2:
        lart('No FQDN')
    try:
        fqdn = str(ip_address(argv[1]))
    except:
        fqdn = argv[1].strip('.').lower().split('.')
        if   len(fqdn) < len(DOMAIN):
            fqdn += DOMAIN
        elif fqdn[ -1 * len(DOMAIN) : ] != DOMAIN:
            fqdn += DOMAIN
        fqdn = '.'.join(fqdn)
        
    if len(argv) < 3:
        rkvdns = None
    else:
        rkvdns = argv[2].strip('.').lower()
    if rkvdns is None:
        rkvdns = RKVDNS
    if rkvdns is None:
        lart('RKVDNS domain cannot be determined.')

    if len(argv) < 4:
        resolver = Resolver()
        if SERVER is not None:
            resolver.nameservers = [SERVER]
    else:
        resolver = Resolver(configure=False)
        resolver.nameservers = [argv[3]]
    
    main(fqdn, rkvdns, resolver, debug)




