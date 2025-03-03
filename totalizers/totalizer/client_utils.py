#!/usr/bin/python3
# Copyright (c) 2022-2023 by Fred Morris Tacoma WA
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
import threading

REDIS_WILDCARD = '*'
ESCAPED = { c for c in '.;' }
DEFAULT_DELIMITER = ';'
FATAL_RCODES = { 'SERVFAIL', 'NXDOMAIN' }
    
def escape(qname):
    """Escape . and ;"""
    for c in ESCAPED:
        qname = qname.replace(c, '\\{}'.format(c))
    return qname

class SpecError(Exception):
    pass

class Resolver(object):
    """A wrapper around dns.resolver.Resolver.
    
    Support for ENABLE_ERROR_TXT
    ----------------------------
    
    RKVDNS has a configuration parameter which when enabled turns errors into
    TXT responses. If such an error is seen, success returns False and any_txt
    will return the error text.
    """
    
    ATTRS = {'resolver', 'resp', 'qtype', 'exc'}
    
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
    
    def query(self, qname, qtype, **kwargs):
        """Query. FLUENT
        
        This makes a lot of assumptions which aren't enforced by the DNS. Don't
        expect this to work very well with something which is not RKVDNS.
        
        Returns a reference to the object itself.
        """
        self.qtype = qtype
        try:
            self.resp = None
            self.exc = None
            self.resp = self.resolver.query(qname, qtype, **kwargs)
        except DNSException as exc:
            self.exc = type(exc).__name__

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
    
class Resources(object):
    """A thing which preprocesses totalizer buckets.
    
    total() makes a KEYS request for a tranche of totalizer buckets which
    are distinguished by timestamps as the rightmost part.
    
    append() creates lists of the timestamp values for each distinguishing
    key. sort() then sorts the timestamp values (in descending order) for each
    distinguishing key.
    
    When buckets() is called on the (now sorted) lists of timestamp values
    for each key, it stops yielding timestamp values when the timestamp of the
    previously yielded bucket was below the window floor. total() does some
    additional work to pro-rate the bucket which was opened earlier than the
    window floor.
    """
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
    
class FieldHandlerType(object):
    """Enhanced field handling for total().
    
    Subclasses of FieldHandlerType are expressed as singletons which can be utilized
    with similar semantics to None, using "is" in the total() match_spec.
    
    Refer to the documentation for total() match_spec.
    """
    pass

class BreakType(FieldHandlerType):
    """The field should be treated as a break for grouping purposes.
    
    This is equivalent to what specifying None accomplishes. The field is used
    as a group/break.
    
    The singleton created with this type is Break.
    """
    pass

Break = BreakType()

class IgnoreType(FieldHandlerType):
    """The field should be ignored for grouping purposes.
    
    Allows inner fields to be ignored (not supported by None semantics).
    
    The singleton created with this type is Ignore.
    """
    pass

Ignore = IgnoreType()

MATCH_SPEC_HANDLERS = { None, Break, Ignore }
MATCH_SPEC_BREAK = { None, Break }
    
def total(match_spec, parts, window, rkvdns, delimiter=DEFAULT_DELIMITER, nameservers=None, debug_print=None):
    """Compute a total over the window for some set of keys.
    
    Parameters:
    
      match_spec        The matching / break spec, see below.
      parts             The expected number of parts in the key after splitting with the
                        delimiter.
      window            The number of seconds in the aggregation window. Note that the
                        maximum aggregation window is bounded by the number of buckets
                        and the bucket period being used for aggregation.
      rkvdns            The RKVDNS domain name. See totalizer.fanout if you want to use a
                        fanout FQDN.
      delimiter         Keys are comprised of delimited parts. This is the delimiter.
      nameservers       A way to explicitly call out the nameservers to use.
      debug_print       A print function for debug output.
      
    Returns a dictionary of totals (DictOfTotals), where the key is the item of interest
    or "break" to aggregate.
    
    Pass something like print or logging.info as debug_print to get logging of queries,
    it can be useful to wrap your head around the DNS traffic.
    
    Use None to identify the values to aggregate.
    
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
    

    FieldHandlerType Semantics
    --------------------------
    
    You could also have multiple values being aggregated on:
    
      conn;<proto>;<port>;<server>;<timestamp>
      
    You would specify that both proto and port should be aggregated on:
    
      [ 'conn', None, None, 'athena' ]
    
    When constructing the match_spec, None essentially identifies one or more
    fields which should be utilized as breaks for aggregation. This does not
    provide a way to identify internal fields which should not be utilized as
    breaks when their value changes.
    
    In this previous example the break is protocol + port. If you want to break
    on just one or the other of those (while still focusing on a single server)
    there's no way to do that.
    
    FieldHandlerType semantics address this with the two singletons Ignore and
    Break. For instance the following breaks only on port:
    
        [ 'conn', Ignore, Break, 'athena' ]
        
    The available FieldHandlerType singletons (exportable from this module) are:
    
        Ignore  Don't use this field as a break.
        Break   Use this field as a break (equivalent to None)
        

    Count Reported as Zero
    ----------------------
    
    You may rarely see a count reported as zero. Fractional counts have to be
    computed when a bucket's start time lies outside (prior) to the start of the
    reporting period. It is possible for this computed value to be less than one,
    in which case it is reported as zero.
    
    Example: Only one third (0.33) of the bucket's window lies within the reporting
    period, and there were only two occurrences observed. The computed value is
    0.66 which is less than one; if this is the only bucket for the key, it will be
    reported as zero.
    """
    now = int(time())
    window_floor = now - window

    if nameservers:
        resolver = Resolver(configure=False)
        resolver.nameservers = nameservers
    else:
        resolver = Resolver()
    
    match_spec = match_spec.copy()
    item_of_interest = []
    for i in range(len(match_spec)):
        if match_spec[i] in MATCH_SPEC_HANDLERS:
            if match_spec[i] in MATCH_SPEC_BREAK:
                # Ignore items are not added here.
                item_of_interest.append(i)
            match_spec[i] = REDIS_WILDCARD
    if not item_of_interest:
        raise SpecError('No item of interest found in match_spec.')
    
    if not match_spec[-1].endswith(REDIS_WILDCARD):
        match_spec.append(REDIS_WILDCARD)
    match_spec = delimiter.join(match_spec)
    
    qname = '{}.keys.{}'.format( escape( match_spec ), rkvdns )
    if resolver.query( qname, rdtype.TXT, raise_on_no_answer=False ).success:
        if debug_print:
            debug_print('{} -- success ({})'.format(qname, len(resolver.result)))
    else:
        # SERVFAIL or NXDOMAIN here means something more serious.
        if   (resolver.exc or dns.rcode.to_text(resolver.resp.response.rcode())) in FATAL_RCODES:
            logging.error('Fatal error in query: {} -- {}, check logs'.format(qname, resolver.exc or dns.rcode.to_text(resolver.resp.response.rcode())))
        elif debug_print:
            debug_print('{} -- failure: {}'.format(qname, resolver.exc or dns.rcode.to_text(resolver.resp.response.rcode())))
        return dict()
    resources = Resources(window_floor, delimiter, parts)
    for bucket in resolver.result:
        try:
            resources.append( bucket.to_text().strip('"') )
        except ValueError as e:
            logging.warn('Invalid bucket key in result set for {}: {}'.format(qname, e))
    resources.sort()
    
    totals = DictOfTotals()
    
    last_resource = ''
    # Iterates over distinguishing keys (resource) and timestamps within those in
    # descending order (bucket). The count (value) for each complete key is fetched
    # and the (pro-rated if necessary) value is summed into the item_of_interest.
    for resource, bucket in resources.buckets():

        if resource != last_resource:
            last_bucket = now
            last_resource = resource

        qname = '{}.get.{}'.format(escape(delimiter.join( resource + (str(bucket),) )), rkvdns)
        if resolver.query( qname, rdtype.TXT, raise_on_no_answer=False ).success:
            value = int(resolver.result[0].to_text().strip('"'))
            if debug_print:
                debug_print('{} -- success ({})'.format(qname, value))
        else:
            if debug_print:
                debug_print('{} -- failure: {}'.format(qname, resolver.exc or dns.rcode.to_text(resolver.resp.response.rcode())))
            continue
        
        if bucket >= window_floor:
            totals.add( delimiter.join( resource[item] for item in item_of_interest ), value )
            last_bucket = bucket
            continue
        
        # This should never happen.
        if last_bucket < window_floor:
            continue
    
        # Our presumption at this point is that last_bucket is within the window, but the
        # bucket start time is outside of it.
        portion = (last_bucket - window_floor) / (last_bucket - bucket)
        totals.add( delimiter.join( resource[item] for item in item_of_interest ), int(value * portion) )
    
    return totals


