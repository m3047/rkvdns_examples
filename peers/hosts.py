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

"""Network Hosts.

Command line:

    hosts.py network
    
Lists, symbolically when possible, the hosts observed on the network.

    network     The network CIDR.
    
Expects entries to be set in `configuration.py`:

    RKVDNS      The domain that rkvdns serves responses under. See below.
    SERVER      The address of the dns server.
    
Refer to the documentation for RKVDNS. Our query will be fabricated into a domain
name looking something like

    clients;*.keys.proxy.redis.example.com

The RKVDNS domain in this example is proxy.redis.example.com

Order of Operation
------------------

1) clients (above) are resolved to hosts.

2) Reverse (PTR) lookups are performed for each host.

Assumptions / Limitations
-------------------------

The RKVDNS instance is configured with CASE_FOLDING = 'lower'.

Number of hosts within the supplied network is constrained enough that all
of the client keys and hostnames will fit within the 64k DNS limit. This is
probably in the neighborhood of 3000 IPv4 addresses, 1400 for IPv6.

I'm not absolutely certain the (redis database) prefix calculation is correct
for IPv6 in all cases. If it's not working for some case, please let me know.
"""

import sys
from ipaddress import ip_address, ip_network, IPv4Network, IPv6Network, IPv6Address
import dns.rdatatype as rdtype
from rkvdns import Resolver

from math import floor

RKVDNS = None
SERVER = None
# NOTE: See pydoc for information about CASE_FOLDING.
QUERY = "client;{}*"
ESCAPED = '.;'
OUTPUT_FORMAT = '{} [{}]'
MISSING_NAME = ''
ADDITIONAL_NAMES = '...'

def lart(msg=None, help='hosts {network}'):
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

ESCAPED = { c for c in ESCAPED }
    
def escape(qname):
    """Escape . and ;"""
    for c in ESCAPED:
        qname = qname.replace(c, '\\{}'.format(c))
    return qname

def main( target, rkvdns, resolver, print_addresses ):

    def print_peer(peer, addr):
        if print_addresses:
            print(OUTPUT_FORMAT.format(peer or MISSING_NAME, str(addr)))
        else:
            print(peer or str(addr))
        return
        
    # Get hosts.
    if isinstance(target, IPv4Network):

        octets = floor(target.prefixlen / 8)
        iterable = target.prefixlen - octets * 8
        if iterable:
            octets += 1
            iterable = 8 - iterable
        base = str(target.network_address).split('.')[:octets]
        if   base:
            iter_base = int(base.pop())
            prefixes = [ '.'.join(base + [ str(iter_base+i) ]) for i in range(2**iterable) ]
        else:
            prefixes = ['']
            
    else: # IPv6Network

        nybbles = floor(target.prefixlen / 4)
        iterable = target.prefixlen - nybbles * 4
        if iterable:
            nybbles += 1
            iterable = 4 - iterable
        as_hex = '%032x' % int(target.network_address)        
        base = as_hex[:nybbles]
        if base:
            iter_base = int(base[-1], 16)
            base = base[:-1]
            prefixes = [ str(IPv6Address(int((base + '%x' % (iter_base+i) + '0'*32)[:32], 16))) for i in range(2**iterable) ]
        else:
            prefixes = ['']

    hosts = []

    for prefix in prefixes:
        qname = '{}.keys.{}.'.format( escape( QUERY.format(prefix) ), rkvdns)
        if not resolver.query( qname, rdtype.TXT).success:
            continue

        hosts += [ rr.to_text().strip('"').split(';')[1] for rr in resolver.result ]

    # Do reverse lookups.
    for i in range(len(hosts)):
        addr = ip_address(hosts[i])
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

if __name__ == '__main__':
    
    argv = sys.argv

    print_addresses = False
    while argv[-1].startswith('+'):
        arg = argv.pop()[1:]
        if   arg == 'addresses'[:len(arg)]:
            print_addresses = True
        else:
            lart('Unrecognized option "{}"'.format(arg))

    if len(argv) < 2:
        lart('No network.')
    try:
        network = ip_network(argv[1])
    except Exception as e:
        lart('Invalid network {}: {}'.format(argv[1], e))
        fqdn = argv[1].strip('.').lower().split('.')
        if   len(fqdn) < len(DOMAIN):
            fqdn += DOMAIN
        elif fqdn[ -1 * len(DOMAIN) : ] != DOMAIN:
            fqdn += DOMAIN
        fqdn = '.'.join(fqdn)
        
    resolver = Resolver()
    if SERVER is not None:
        resolver.nameservers = [SERVER]
    
    main(network, RKVDNS, resolver, print_addresses)




