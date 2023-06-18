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

"""RKVDNS Data Query Encapsulation.

Basic order of operations is to allocate a Resolver and then call query()
and test success and result.
"""

from ipaddress import IPv4Address, IPv6Address, IPv4Network, IPv6Network
from math import floor

import dns.resolver as resolver
import dns.rdatatype as rdtype
import dns.rdataclass as rdclass
from dns.exception import DNSException
import dns.rcode

def prefixes(network):
    """Determine ShoDoHFlo network prefixes.
    
    Parameters:
    
        network         An IPv4Network or IPv6Network object.
    
    Addresses are stored in the ShoDoHFlo Redis database in standard stringified
    form. Examples: "1:2345::1" "1.2.3.4".
    
    Under other (normal) circumstances we'd compute a bit mask but that won't
    work here. In particular, we may need to generate multiple stringified
    prefixes to capture the entirety of an actual bitmask prefix.
    """
    if isinstance(network, IPv4Network):

        octets = floor(network.prefixlen / 8)
        iterable = network.prefixlen - octets * 8
        if iterable:
            octets += 1
            iterable = 8 - iterable
        base = str(network.network_address).split('.')[:octets]
        if   base:
            iter_base = int(base.pop())
            all_prefixes = [ '.'.join(base + [ str(iter_base+i) ]) for i in range(2**iterable) ]
        else:
            all_prefixes = ['']
            
    else: # IPv6Network

        nybbles = floor(network.prefixlen / 4)
        iterable = network.prefixlen - nybbles * 4
        if iterable:
            nybbles += 1
            iterable = 4 - iterable
        as_hex = '%032x' % int(network.network_address)        
        base = as_hex[:nybbles]
        if base:
            iter_base = int(base[-1], 16)
            base = base[:-1]
            all_prefixes = [ str(IPv6Address(int((base + '%x' % (iter_base+i) + '0'*32)[:32], 16))) for i in range(2**iterable) ]
        else:
            all_prefixes = ['']
        
    return all_prefixes

class Resolver(object):
    """A wrapper around dns.resolver.Resolver."""
    
    ATTRS = {'resolver', 'resp', 'qtype'}
    
    def __init__(self, *args, **kwargs):
        """Initialize the resolver.
        
        Arguments are passed to dns.resolver.Resolver().
        
        Additionally, attempts to modify certain attributes are passed to the
        Resolver.
        
        This is not threadsafe.
        """
        self.resolver = resolver.Resolver(*args, **kwargs)
        self.resp = None
        self.qtype = rdtype.TXT
        return
    
    def __setattr__(self, k, v):
        if k in self.ATTRS:
            object.__setattr__(self, k, v)
        else:
            setattr(self.resolver, k, v)
        return
    
    def query(self, qname, qtype):
        """Query. FLUENT
        
        This makes a lot of assumptions which aren't enforced by the DNS. Don't
        expect this to work very well with something which is not RKVDNS.
        
        Returns a reference to the object itself.
        """
        self.qtype = qtype
        try:
            self.resp = None
            self.resp = self.resolver.query(qname, qtype)
        except DNSException:
            pass
        
        return self
    
    @property
    def success(self):
        if self.resp is None or self.resp.response.rcode() != dns.rcode.NOERROR:
            return False
        # This part supports ENABLE_ERROR_TXT in RKVDNS.
        qname = self.resp.response.question[0].name.to_text().lower()
        for rset in self.resp.response.answer:
            rname = rset.name.to_text().lower()
            if rname != qname:
                continue
            if rset.rdtype == rdtype.CNAME and 'error' in rset[0].to_text().lower():
                return False
        return True
            
    @property
    def result(self):
        """Returns the result.
        
        This is first rrset from the answer section which:
        
        * matches the query name; and
        * has the correct qtype.
        
        Both the query name and rset name are lowercased before comparison.
        """
        qname = self.resp.response.question[0].name.to_text().lower()
        for rset in self.resp.response.answer:
            if rset.name.to_text().lower() != qname:
                continue
            if rset.rdtype != self.qtype:
                continue
            return rset
        return []
    
    @property
    def any_txt(self):
        """Return error text.
        
        There is a mode in RKVDNS which is enabled by setting ENABLE_ERROR_TXT
        which returns the error as a TXT record. If that is enabled, this returns
        the error text.
        """
        for rset in self.resp.response.answer:
            if rset.rdtype != rdtype.TXT:
                continue
            return rset
        return []
