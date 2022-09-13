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

import logging

import dns.resolver as resolver
import dns.rdatatype as rdtype
import dns.rdataclass as rdclass
from dns.exception import DNSException
import dns.rcode

from time import time

REDIS_WILDCARD = '*'
ESCAPED = { c for c in '.;' }
    
def escape(qname):
    """Escape . and ;"""
    for c in ESCAPED:
        qname = qname.replace(c, '\\{}'.format(c))
    return qname

class SpecError(Exception):
    pass

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
        return self.resp is not None and self.resp.response.rcode() == dns.rcode.NOERROR
            
    @property
    def result(self):
        """Returns the first rrset from the answer section which has the correct qtype."""
        for rset in self.resp.response.answer:
            if rset.rdtype != self.qtype:
                continue
            return rset
        return []
    
class Resources(object):
    
    def __init__(self, window_floor, delimiter, parts):
        self.resources = dict()
        self.window_floor = window_floor
        self.delimiter = delimiter
        self.parts = parts
        return
    
    def append(self, bucket):
        bucket = bucket.split( self.delimiter )
        if len(bucket) != self.parts:
            raise ValueError('Wrong number of parts: {}'.format(bucket))
        resource = tuple( bucket[:-1] )
        if resource not in self.resources:
            self.resources[resource] = []
        self.resources[resource].append(int(bucket[-1]))
        return
    
    def sort(self):
        for item in self.resources.values():
            item.sort(reverse=True)
        return
    
    def buckets(self):
        for k,buckets in self.resources.items():
            for bucket in buckets:
                yield (k, bucket)
                if bucket < self.window_floor:
                    break
        return

class DictOfTotals(dict):
    def add(self, k, n):
        if k not in self:
            self[k] = 0
        self[k] += n
        return
    
def total(match_spec, parts, window, rkvdns, delimiter=';', nameservers=None, debug_print=None):
    """Compute a total over the window for some set of keys.
    
    Returns a dictionary of totals, where the key is the item of interest.
    
    Pass something like print or logging.info as debug_print to get logging of queries,
    it can be useful to wrap your head around the DNS traffic.
    
    Use None to identify the value to aggregate.
    
    You need to coordinate the match_spec with what is being written to Redis.
    For instance you might write keys looking something like this to track web page
    hits:
    
      page;<resource-name>;<server>;<timestamp>
      
    An actual key might look like:
    
      page;index.html;athena;1662966417
      
    We assume the timestamp is at the end of the key. If we want
    to collect from all available servers, the match spec would be:
    
      [ 'page', None ]
      
    On the other hand if you wanted results just for the server athena:
    
      [ 'page', None, 'athena' ]
      
    These would result in the following wildcarded keys to be searched for:
    
      page;*
      page;*;athena;*
      
    The delimiter defaults to ";".
    
    In any case totals will be calculated for all of the page names and returned
    as a list of (<page-name>,<total>) tuples.
    """
    now = int(time())
    window_floor = now - window

    if nameservers:
        resolver = Resolver(configure=False)
        resolver.nameservers = nameservers
    else:
        resolver = Resolver()
    
    match_spec = match_spec.copy()
    item_of_interest = None
    for i in range(len(match_spec)):
        if match_spec[i] is None:
            match_spec[i] = REDIS_WILDCARD
            item_of_interest = i
    if item_of_interest is None:
        raise SpecError('None value (item of interest) not found in match_spec.')
    
    if not match_spec[-1].endswith(REDIS_WILDCARD):
        match_spec.append(REDIS_WILDCARD)
    match_spec = delimiter.join(match_spec)
    
    qname = '{}.keys.{}'.format( escape( match_spec ), rkvdns )
    if debug_print:
        debug_print(qname)
    if not resolver.query( qname, rdtype.TXT ).success:
        return dict()
    resources = Resources(window_floor, delimiter, parts)
    for bucket in resolver.result:
        try:
            resources.append( bucket.to_text().strip('"') )
        except ValueError:
            logging.warn('Invalid timestamp in result set for {}'.format(qname))
    resources.sort()
    
    totals = DictOfTotals()
    
    last_resource = ''
    for resource, bucket in resources.buckets():

        if resource != last_resource:
            last_bucket = now
            last_resource = resource

        qname = '{}.get.{}'.format(escape(delimiter.join( resource + (str(bucket),) )), rkvdns)
        if debug_print:
            debug_print('{}...'.format(qname))
        if not resolver.query( qname, rdtype.TXT ).success:
            continue
        
        value = int(resolver.result[0].to_text().strip('"'))
        if debug_print:
            debug_print('...{}'.format(value))
        if bucket >= window_floor:
            totals.add( resource[item_of_interest], value )
            last_bucket = bucket
            continue
        
        # This should never happen.
        if last_bucket < window_floor:
            continue
    
        # Our presumption at this point is that last_bucket is within the window, but the
        # bucket start time is outside of it.
        portion = (last_bucket - window_floor) / (last_bucket - bucket)
        totals.add( resource[item_of_interest], int(value * portion) )
    
    return totals


