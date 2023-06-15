#!/usr/bin/python3
"""Fanout to query multiple RKVDNS servers via PTR redirection.

By creating multiple PTR records to which an FQDN resolves you can fan out
RKVDNS queries to multiple servers, fulfilling the objective of federated data
availability.
"""

from fanout.py import BaseName

WARN_IF_NO_ANSWER = True

def map(fqdn, task, *args, **kwargs):
    """A wrapper around BaseName.map().
    
    The first argument is the FQDN to be resolved to PTR records. All of the other
    arguments are passed to BaseName.map().
    
    You may need to write a wrapper for your task, because map() will call it with
    the PTR result as the first argument.
    """
    
    return BaseName( fqdn, WARN_IF_NO_ANSWER ).map( task, *args, **kwargs )
