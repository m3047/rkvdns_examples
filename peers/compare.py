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

"""Comparisons of Peers between Different Hosts

Command line:

    compare.py [any|all] [same|different] <fqdn> [<network> | <fqdn>][...] {+addresses}
    
Lists, similarities and differences in the netflow peers of the specified host versus
the other hosts / networks.

    any same     Any netflow shared by the fqdn and at least one peer.
    all same     Any netflow shared by the fqdn and all peers.
    any diff     Netflows not shared by the fqdn and any peers.
    all diff     Netflows not shared by the fqdn and all peers.

    fqdn         This is the (resolvable) fully qualified hostname, or an address.
    network      A network spec. All found hosts will be used for reference.
    addresses    The addresses are printed after the hostnames in all cases, not just
                 when the reverse lookup fails.
                 
EXCEPTION REGARDING <fqdn> + <network>: If <fqdn> is in <network>, it is excluded
from <network>.

Expects entries to be set in `configuration.py`:

    DOMAIN      Akin to a search list, this is the domain to be appended to the
                hostnames/fqdns.
    RKVDNS      The domain that rkvdns serves responses under. See below.
    SERVER      The address of the dns server.
    
Refer to the documentation for RKVDNS. Our query will be fabricated into a domain
name looking variously like

    address;*;flow.keys.proxy.redis.example.com
    clients;*.keys.proxy.redis.example.com

The RKVDNS domain in this example is proxy.redis.example.com

Order of Operation
------------------

1) fqdn / hostnames are resolved.

    Unless the name parses as an IPv4 or IPv6 address, it is resolved with A / AAAA
    queries to identify the actual address. IPv6 is preferred.
    
    If DOMAIN is defined, then it is appended to the fqdn (unless it matches the
    righthand side of the fqdn) before attempting DNS resolution.
    
2) Networks are queried for hosts.

    The clients;... pattern is utilized to discover the hosts in any network specs,
    and these are added to the other list(s).
    
3) Uses rkvdns to query a redis database containing flow information.

    There is a Redis database with keys conforming to the following pattern:
    
        <client>;<peer>;<port>;flow
        
    Notice that this is case sensitive, that is "flow" is lower case.
    
    The address established in step 1 is queried for as client keys:
    
        "<resolved-address>;*;flow"
    
    The Redis database is maintained by pcap-agent.
    (https://github.com/m3047/shodohflo/blob/master/agents/pcap_agent.py)
    
4 Set arithmetic is utilized to identify the desired flows.

    The flows represent peers.
    
3) Reverse (PTR) lookups are performed for each peer.

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
from ipaddress import ip_address, ip_network
import dns.rdatatype as rdtype
from rkvdns import Resolver, prefixes

DOMAIN = None
RKVDNS = None
SERVER = None
# NOTE: See pydoc for information about CASE_FOLDING.
FLOW_QUERY = "{};*;flow"
CLIENT_QUERY = "client;{}*"
ESCAPED = '.;'
OUTPUT_FORMAT = '{} [{}]'
MISSING_NAME = ''
ADDITIONAL_NAMES = '...'

def lart(msg=None, help='compare.py [any|all] [same|different] <fqdn> [<network> | <fqdn>][...] {+addresses}'):
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

def resolve_fqdn(target, resolver, msg='Failed to resolve {}'):
    """Attempt to convert an FQDN to an address.
    
    If the attempt fails, an attempt is made to treat it as a bare
    address.
    """
    addresses = []
    for qtype in ADDRESS_TYPES:
        if not resolver.query( target + '.', qtype ).success:
            continue        
        addresses += [ rr.to_text() for rr in resolver.result ]

    if not addresses:
        try:
            addresses = [str(ip_address(target))]
        except:
            pass
    if not addresses:
            lart(msg.format(target), help=None)
    
    return addresses

def resolve_corpus(corpus, rkvdns, resolver):
    """Take a corpus of networks / addresses / fqdns and resolve it.
    
    Returns the corpus as discrete addresses.
    """
    new_corpus = []
    for item in corpus:

        # Is it a network?
        try:

            network = ip_network(item)  # Might kick ValueError

            # Get the hosts.
            for prefix in prefixes(network):
                qname = '{}.keys.{}.'.format( escape( CLIENT_QUERY.format(prefix) ), rkvdns)
                if not resolver.query( qname, rdtype.TXT).success:
                    continue

                new_corpus += [ rr.to_text().strip('"').split(';')[1] for rr in resolver.result ]
            continue

        except ValueError:
            pass
        
        
        try:
            new_corpus += str(ip_address(item))
            continue
        except:
            pass

        # Must be an FQDN then.
        fqdn = item.strip('.').lower().split('.')
        if   len(fqdn) < len(DOMAIN):
            fqdn += DOMAIN
        elif fqdn[ -1 * len(DOMAIN) : ] != DOMAIN:
            fqdn += DOMAIN
        fqdn = '.'.join(fqdn)
        
        # FQDN can't be NX.
        new_corpus += resolve_fqdn(fqdn, resolver)
        
    return new_corpus

def peers(addresses, rkvdns, resolver):
    all_peers = []
    for address in addresses:
        qname = '{}.keys.{}.'.format( escape( FLOW_QUERY.format(address) ), rkvdns)

        if not resolver.query( qname, rdtype.TXT).success:
            continue

        all_peers += [ rr.to_text().strip('"').split(';')[1] for rr in resolver.result ]
    
    return set(all_peers)
    
def main( target, corpus, scope, mode, rkvdns, resolver, print_addresses ):

    def print_peer(peer, addr):
        if print_addresses:
            print(OUTPUT_FORMAT.format(peer or MISSING_NAME, str(addr)))
        else:
            print(peer or str(addr))
        return
        
    # Resolve the target and the corpus.
    addresses = resolve_fqdn(target, resolver)          # returns a list
    corpus = resolve_corpus(corpus, rkvdns, resolver)   # returns a list
    
    # Get target peers.
    target_peers = peers(addresses, rkvdns, resolver)   # returns a set
    
    # Corpus peers.
    addresses = set(addresses)
    corpus_peers = set()
    for item in corpus:
        if item in addresses:
            continue
        if scope == 'any':
            corpus_peers |= peers([item], rkvdns, resolver)
        else:   # 'all'
            corpus_peers &= peers([item], rkvdns, resolver)
            
    # Calculate the desired list of peers.
    if mode == 'same':
        desired_peers = target_peers & corpus_peers
    else:       # 'diff'
        desired_peers = target_peers - corpus_peers

    # Do reverse lookups.
    for desired_peer in desired_peers:
        addr = ip_address(desired_peer)
        if not resolver.query(addr.reverse_pointer, rdtype.PTR).success:
            print_peer('', addr)
            continue

        result = resolver.result
        if len(result):
            peer = result[0].to_text() + (len(result) > 1 and ADDITIONAL_NAMES or '')
        else:
            peer = ''

        print_peer(peer, addr)
    
    return

SCOPES = { 'an':'any', 'al':'all' }
MODES = {'s':'same', 'd':'different' }

if __name__ == '__main__':
    
    argv = sys.argv

    print_addresses = False
    while argv[-1].startswith('+'):
        arg = argv.pop()[1:]
        if   arg == 'addresses'[:len(arg)]:
            print_addresses = True
        else:
            lart('Unrecognized option "{}"'.format(arg))

    if len(argv) < 5:
        lart('Not enough arguments.')

    try:
        scope = SCOPES[argv[1][:2]]
        if argv[1] != scope[:len(argv[1])]:
            lart('Unrecognized scope {}. Expected any or all.')
    except:
        lart('Unrecognized scope {}. Expected any or all.')
    
    try:
        mode = MODES[argv[2][:1]]
        if argv[2] != mode[:len(argv[2])]:
            lart('Unrecognized mode {}. Expected same or diff.')
    except:
        lart('Unrecognized mode {}. Expected same or diff.')

    try:
        fqdn = str(ip_address(argv[3]))
    except:
        fqdn = argv[3].strip('.').lower().split('.')
        if   len(fqdn) < len(DOMAIN):
            fqdn += DOMAIN
        elif fqdn[ -1 * len(DOMAIN) : ] != DOMAIN:
            fqdn += DOMAIN
        fqdn = '.'.join(fqdn)
    
    corpus = argv[4:]
    
    resolver = Resolver()
    if SERVER is not None:
        resolver.nameservers = [SERVER]
    
    main(fqdn, corpus, scope, mode, RKVDNS, resolver, print_addresses)

