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

import dns.resolver as resolver
import dns.rdatatype as rdtype
import dns.rdataclass as rdclass
from dns.exception import DNSException
import dns.rcode

class Resolver(object):
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
        return self.resp is not None and self.resp.response.rcode() == dns.rcode.NOERROR
            
    @property
    def result(self):
        for rset in self.resp.response.answer:
            if rset.rdtype != self.qtype:
                continue
            return rset
        return []
    


