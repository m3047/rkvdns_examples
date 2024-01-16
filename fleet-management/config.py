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

"""Configuration Report.

Command line:

    config.py <fanout-fqdn>

Reads and reports the configurations of all of the RKVDNS instances in
the fanout.
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
        
    base = fanout.BaseName( target, WARN_IF_NOERROR )
    instances = base.fanout
    if base.qstatus != rcode.NOERROR:
        print('Failed to resolve {} ({})'.format(target, rcode.to_text(base.qstatus)), file=sys.stderr)
        sys.exit(1)
    instances = sorted( instances )

    configurations = base.map( query, 'config', rdtype.TXT )

    for instance in instances:
        configurations[instance] = dict( b''.join(rr.strings).decode().split(':') for rr in configurations[instance].value )

    # Builds a list of all config items and their maximum lengths.
    instance_max = {}
    all_params = set()
    for instance in instances:
        instance_max[instance] = len(instance)
        for k,v in configurations[instance].items():
            all_params.add(k)
            if len(v) > instance_max[instance]:
                instance_max[instance] = len(v)

    param_max = max( len(p) for p in all_params )
    sorted_params = sorted(all_params)
    sorted_params.insert(0, '')
    
    def row_func():
        row = []
        for param in sorted_params:
            row = []
            if not param:
                row.append( '{:{}s}'.format('', param_max) )
                for instance in instances:
                    row.append( '{:{}s}'.format( instance, instance_max[instance] ) )
                yield row
            else:
                row.append( '{:{}s}'.format( param, param_max ) )
                for instance in instances:
                    v = configurations[instance].get(param, '')
                    row.append( '{:<{}s}'.format( v, instance_max[instance] ) )
                yield row
    
    for row in row_func():
        print('|'.join(row) + '|')
        
    return
    
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




