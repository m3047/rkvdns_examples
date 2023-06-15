#!/usr/bin/python3
# Copyright (c) 2023 by Fred Morris Tacoma WA
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

"""A fanout widget for DNS-as-data.

The general notion here is that you can define (multiple) PTR records for an FQDN,
and a lookup will be performed for that FQDN and then some action(s) will be 
parallelized in queries sent to all of those FQDNs.

Assets here address the following concerns:

* Does the FQDN resolve to one or more PTRs?
* Marshalling the task out to those PTRs.
* Reducing the task results to a single result set.

This is a specialized copypasta version of rkvdns_examples/fanout/fanout.py that
explicitly supports totalizer.client_utils.total() across federated resources.

Comparison of Calling Signatures
--------------------------------

client_utils.total():

    counts = total( search_spec, number_of_parts, window, rkvdns_spec, ... )

fanout.BaseName.total():

    counts = BaseName(rkvdns_spec).total( search_spec, number_of_parts, window, ... )

"""

from dns.resolver import Resolver
import dns.rcode as rcode
import dns.rdatatype as rdtype

import concurrent.futures
import logging

from . import client_utils

class BaseName(object):
    """The encapsulation of the FQDN to be fanned out."""
    
    def __init__(self, fqdn, warn_if_noanswer=False):
        self.fqdn = fqdn
        self.fanout_ = None
        self.warn_if_noanswer = warn_if_noanswer
        return
    
    @property
    def fanout(self):
        """Return a list of the PTR FQDNs to be fanned out to."""
        if self.fanout_ is None:
            resolver = Resolver()
            try:
                qstatus = None
                resp = resolver.query( self.fqdn, 'PTR', raise_on_no_answer=False ).response
                qstatus = resp.rcode()                
                if qstatus != rcode.NOERROR:
                    if self.warn_if_noanswer:
                        logging.warn('Query failure: {}'.format(rcode.to_text(qstatus)))
                    qstatus = None
            except Exception as e:
                if self.warn_if_noanswer:
                    logging.warn('Query failure: {}'.format(type(e).__name__))
                pass
            if qstatus is None:
                self.fanout_ = []
                return self.fanout_
            for rrset in resp.answer:
                if rrset.rdtype == rdtype.PTR:
                    self.fanout_ = [ rd.to_text().strip('.').lower() for rd in rrset ]
                    break
            if not self.fanout_:
                if self.warn_if_noanswer:
                    logging.warn('Empty PTR result.')
        return self.fanout_
    
    def map(self, task, *args, **kwargs):
        """Perform some operation on the fanout and return the results.
        
        task() is called as follows:
        
            task( server, *args, **kwargs )
            
        It should return the results (typically as a list).
        
        Return: A hash of the fanout server FQDNs with the individual results as
        values.
        """
        with concurrent.futures.ThreadPoolExecutor() as executor:
            threads = dict()
            results = dict()
            for server in self.fanout:
                threads[ executor.submit( task, server, *args, **kwargs ) ] = server
            for thread in concurrent.futures.as_completed( threads ):
                results[ threads[thread] ] = thread.result()
                
        return results
    
    @staticmethod
    def total_( server, *args, **kwargs ):
        """Wrapper for client_utils.total() for use with BaseName.map()."""
        return client_utils.total( *args, server, **kwargs )
    
    def total(self, match_spec, parts, window, delimiter=client_utils.DEFAULT_DELIMITER, nameservers=None, debug_print=None):
        """Wraps totalizer.client_utils.total()
        
        The output is the same type as totalizer.client_utils.total(), it is just summed across the
        federated resources.
        
        The rkvdns argument can be either the RKVDNS domain name expected by
        totalizer.client_utils.total() or an FQDN to be fanned out using PTR expansion. Each fanout
        RKVDNS domain is queried in a separate (parallel) thread. If the same (singular) RKVDNS
        domain expected by totalizer.client_utils.total() is supplied, then this is essentially
        identical to simply calling totalizer.client_utils.total() and no parallelism is
        provided.
        """
        if self.fanout:
            counts = client_utils.DictOfTotals()
            for server_result in self.map( self.total_, match_spec, parts, window,
                                           delimiter=delimiter, nameservers=nameservers, debug_print=debug_print
                    ):
                for k,v in server_result.items():
                    counts.add(k,v)            
        else:
            counts = client_utils.total( match_spec, parts, window, self.fqdn, delimiter, nameservers, debug_print )
        
        return counts
    
    