#!/usr/bin/python3
# Copyright (c) 2024 by Fred Morris Tacoma WA
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

"""Health Check.

Command line:

    health.py <fanout-fqdn>
    
Performs a health check of the specified fanout. See ../fanout/README.md for a
description of what fanout is and how it works. Essentially PTR records identify
multiple RKVDNS instances to be queried simultaneously (like CNAMEs but different).

The following checks are performed:

* Does the fanout FQDN exist?
* Do all of the enumerated RKVDNS instances answer SOA and NS queries?
* Can the Redis database be read?
* Do the read values comport with what was expected?

Each line contains the following information:

    <rkvdns-zone-name>  [<soa-ns-valid>] [<redis-valid>]

Here is example output:

    redis.athena.m3047  [SOA] [VAL]
    redis.flame.m3047   [   ] [VAL]
    redis.sophia.m3047  [SOA] [   ]

In the second record, for some reason the SOA / NS records can't be read or have incorrect
values. In the third record the Redis database can't be read or the value was incorrect.

Redis Keys
----------

In the configuration file, the key to be read is specified with HEALTH_KEY. The
default is "health" (lower case).

HEALTH_KEY Values
-----------------

By default the HEALTH_KEY in each Redis instance is supposed to return a value which
is identical to the lower-cased Redis instance name specified with <fanout-fqdn>. It
is also possible to specify a fixed value for all instances, or to have the read value
ignored (only the successful read is evaluated).

HEALTH_VALUE can be set to one of the following:

a string literal    The string literal will be expected for all RKVDNS instances.
Fanout_FQDN         The value should be the (lowercased) fanout instance name.
No_Check            Don't check the value, a successful read is all that is expected.

Fanout_FQDN and No_Check are singletons.
"""

import sys
from os import path

from dns.resolver import Resolver
import dns.rdatatype as rdtype
import dns.rcode as rcode

sys.path.insert(0,path.dirname(path.dirname(path.abspath(__file__))))

import fanout

ESCAPED = '.;'
WARN_IF_NOERROR = True

def lart(msg=None, help='health fanout-fqdn'):
    if msg:
        print(msg, file=sys.stderr)
    if help:
        print(help, file=sys.stderr)
    sys.exit(1)

class HealthValueType(object):
    """Base class for HEALTH_VALUE singletons."""
    pass
class FanoutFQDNType(HealthValueType):
    """Indicates that the value should be the fanout instance name."""
    pass
Fanout_FQDN = FanoutFQDNType()
class NoCheckType(HealthValueType):
    """Indicates that the value should be ignored."""
    pass
No_Check = NoCheckType()

HEALTH_KEY = 'health'
HEALTH_VALUE = Fanout_FQDN

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

class InstanceReturn(object):
    """Encapsulation of the return from an RKVDNS instance."""
    def __init__(self, value=None, exc=None):
        self.value = value
        self.exc = exc
        return

def query(server, q, rdt):
    if q is not None:
        q += '.'
    else:
        q = ''
    try:
        if hasattr(Resolver, 'resolve'):
            result = InstanceReturn(value=Resolver().resolve('{}{}'.format(q,server), rdt))
        else:
            result = InstanceReturn(value=Resolver().query('{}{}'.format(q,server), rdt))
    except Exception as e:
        result = InstanceReturn(exc=e)
    return result

def main( target ):
    
    def soa_ok(soa, ns):
        if soa.value is None or ns.value is None:
            return False
        return soa.value[0].mname.to_text().rstrip('.') == ns.value[0].to_text().rstrip('.')
    
    def v_ok(v, fqdn):
        fqdn = fqdn.rstrip('.')
        if v.value is None:
            return False
        v = ''.join( s.decode() for s in v.value[0].strings )
        if   HEALTH_VALUE is Fanout_FQDN:
            return v.rstrip('.') == fqdn.rstrip('.')
        elif HEALTH_VALUE is No_Check:
            return True
        return v == HEALTH_VALUE
    
    base = fanout.BaseName( target, WARN_IF_NOERROR )
    instances = sorted( base.fanout )
    if base.qstatus != rcode.NOERROR:
        print('Failed to resolve {} ({})'.format(target, rcode.to_text(base.qstatus)), file=sys.stderr)
    
    soa = base.map( query, None, rdtype.SOA )
    ns = base.map( query, None, rdtype.NS )
    results = base.map( query, HEALTH_KEY + '.get', rdtype.TXT )
    
    fsize = max( len(fqdn) for fqdn in results.keys() ) + 1

    for instance in instances:
        print('{:<{fsize}s} [{:s}] [{:s}]'.format(instance,
                                                soa_ok(soa[instance], ns[instance]) and 'SOA' or '   ',
                                                v_ok(results[instance], instance) and 'VAL' or '   ',
                                                      fsize=fsize
             )                                   )

    return

if __name__ == '__main__':
    
    argv = sys.argv

    if len(argv) < 2:
        lart('No FQDN')

    fqdn = argv[1].lower()
    
    main(fqdn)




