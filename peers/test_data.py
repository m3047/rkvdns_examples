#!/usr/bin/python3
"""Populate test data.

Command line:

    test_data <redis-server> {<dns-server>}

Inserts flow records into the ShoDoHFlo (https://github.com/m3047/shodohflo) Redis
database for the addresses in LOCAL_ADDRESSES.

Performs DNS queries for REMOTE_RESOURCES, with the intent that these will be picked
up by e.g. the ShoDoHFlo or Rear View RPZ (https://github.com/m3047/rear_view_rpz) DNS
agents.

Note that there are three of each. Two flows will be dummied up for each address,
such that each of the three address has a unique combination of two flows.
"""

import sys
from ipaddress import ip_address

import dns.rdatatype as rdtype

from rkvdns import Resolver
import redis

LOCAL_ADDRESSES = ('10.1.0.10', '10.1.0.11', '10.1.0.12')

# Did you get an error "you may need to edit REMOTE_RESOURCES"? You may.
# It may also be the case that DNS is not working for some other reason,
# such as the DNS server specified.
REMOTE_RESOURCES = ('www.cnn.com', 'infoblox.com', 'www.microsoft.com')

ADDRESS_CLASS = rdtype.A

# This is the ShoDoHFlo flow key format. We use port 3047 for all dummied flows.
CLIENT_KEY = 'client;{}'
FLOW_KEY = '{};{};3047;flow'
REDIS_TTL = 900

def lart(msg=None, help='test_data.py <redis-server> {<dns-server>}'):
    if msg:
        print(msg, file=sys.stderr)
    if help:
        print(help, file=sys.stderr)
    sys.exit(1)
    
def redis_flow(conn, local, remote):
    for k in ( CLIENT_KEY.format(local), FLOW_KEY.format(local, remote) ):
        conn.incr(k)
        conn.expire(k, REDIS_TTL)
    return

def main( resolver, redis_conn ):
    local_addresses = [ ip_address(address) for address in LOCAL_ADDRESSES ]
    resource_addresses = []
    for resource in REMOTE_RESOURCES:
        if not (resolver.query(resource, ADDRESS_CLASS).success and resolver.result):
            lart('Failed to resolve {} so you may need to edit REMOTE_RESOURCES'.format(resource))
        resource_addresses.append(ip_address(resolver.result[0].to_text()))
    resource_addresses *= 2     # [a,b,c] -> [a,b,c,a,b,c]
    for i,address in enumerate(LOCAL_ADDRESSES):
        for j in range(2):
            redis_flow(redis_conn, address, resource_addresses[i*2+j])
    return

if __name__ == '__main__':
    argv = sys.argv
    if len(argv) < 2:
        lart('Need redis-server.')
    try:
        conn = redis.client.Redis(argv[1])
    except Exception as e:
        lart("Can't connect to redis: {}".format(e))
    
    resolver = Resolver()
    if len(argv) == 3:
        resolver.nameservers = [argv[2]]
        
    main( resolver, conn )

