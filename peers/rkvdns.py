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

import threading

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
        
        * has the correct qtype.
        """
        for rset in self.resp.response.answer:
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

class ResolverPool(object):
    """This is a self-managed pool of Resolver instances.
    
    The notion here is to be threadsafe. The instantiation arguments follow those
    of Resolver:
    
    * Any arguments to __init__() are passed to resolver.Resolver()
    * Any attributes set are applied as attributes on the newly created
      resolver.Resolver instances.
      
    This object is Context Manager aware and supports the with statement as an
    alternative to calling allocate() / free():
    
        with resolver_pool:
          resolver_pool.query(...)
          
    instead of:
    
        resolver = resolver_pool.allocate()
        resolver.query(...)
        resolver.free()
    
    """
    
    ATTRS = { 'args', 'kwargs', 'attrs', 'free_list', 'lock', 'contexts' }
    
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.attrs = {}
        self.free_list = set()
        self.lock = threading.Lock()
        self.contexts = {}
        return
    
    def __setattr__(self, k, v):
        if k in self.ATTRS:
            object.__setattr__(self, k, v)
        else:
            self.attrs[k] = v
        return
    
    def __enter__(self):
        resolver = self.allocate()
        with self.lock:
            self.contexts[threading.get_ident()] = resolver
        return self
    
    def __exit__(self, *exc):
        ident = threading.get_ident()
        self.free(self.contexts[ident])
        with self.lock:
            del self.contexts[ident]
        return False
    
    def allocate(self):
        """Allocate a Resolver from the pool.
        
        A new Resolver is allocated if none are free.
        """
        with self.lock:
            if not self.free_list:
                resolver = Resolver(*self.args,**self.kwargs)
                for attr,v in self.attrs.items():
                    setattr( resolver, attr, v )
                self.free_list.add( resolver )
            resolver = self.free_list.pop()
        return resolver
    
    def free(self, resolver):
        """Allow a Resolver instance to be returned to the pool."""
        with self.lock:
            self.free_list.add( resolver )
        return
    
    #
    # Wrappers for the actual Resolver methods / properties.
    #

    def query(self, qname, qtype):
        """Wrapper for the Resolver method."""
        return self.contexts[threading.get_ident()].query( qname, qtype )
    
    @property
    def success(self):
        """Wrapper for the Resolver property."""
        return self.contexts[threading.get_ident()].success

    @property
    def result(self):
        """Wrapper for the Resolver property."""
        return self.contexts[threading.get_ident()].result

    @property
    def any_txt(self):
        """Wrapper for the Resolver property."""
        return self.contexts[threading.get_ident()].any_txt
