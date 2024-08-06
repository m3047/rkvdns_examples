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

"""Utilities for the Totalizer Agent."""

from time import time
import re
from ipaddress import ip_address

# This set of definitions just can't live inside of WatchRule for whatever reasons. :-(
# ++++++++++++++++
POSITIONAL_ARGS = ('address', 'port', 'matchex', 'keypattern', 'ttl', 'buckets', 'source')

TOKEN_SPECS = {
        'SUBSTITUTION'     : '<([^{}<>]+)>',
        'OPTIONAL'         : '{([^}]+)}',
        'LITERAL'          : '([^{}<>]+)',
        'BAD'              : '(.)'
    }
TOKEN_PRECEDENCE = ('SUBSTITUTION', 'OPTIONAL', 'LITERAL', 'BAD')

TOKEN_SETS = dict(
        OUTER_TOKENS        = { k for k in TOKEN_SPECS.keys() },
        OPTIONAL_TOKENS     = { 'SUBSTITUTION', 'LITERAL', 'BAD' }
    )

# NOTE: It'd be nice to do all of this natively as bytes (I guess), however
#       at least with Python 3.6 group names MUST BE VALID PYTHON IDENTIFIERS
#       which means strings and things break.
for k in TOKEN_SETS.keys():
    tokens = [ tok for tok in TOKEN_PRECEDENCE if tok in TOKEN_SETS[k] ]
    TOKEN_SETS[k] = re.compile(
        '|'.join('(?P<%s>%s)' % (spec, TOKEN_SPECS[spec])
                  for spec in TOKEN_PRECEDENCE if spec in TOKEN_SETS[k]
                )
            )
for k in TOKEN_SPECS.keys():
    TOKEN_SPECS[k] = re.compile(TOKEN_SPECS[k])
# ----------------

class Token(object):
    def __init__(self, spec, value):
        self.spec = spec
        self.value = value
        return
    
    def __repr__(self):
        return '<%s %s %s>' % (type(self).__name__, self.spec, self.value)
    
    def emit(self, substitutions):
        """The only two specs in a Token list should be SUBSTITUTION and LITERAL."""
        if self.spec == 'SUBSTITUTION':
            return substitutions[self.value]
        return self.value       # LITERAL
    
class OptionalToken(Token):
    def __init__(self, spec, value):
        Token.__init__(self, spec, value)
        self.substitution = None
        for tok in value:
            if tok.spec == 'SUBSTITUTION':
                self.substitution = tok.value
                break
        if self.substitution is None:
            raise ParseError('No substitution defined in optional token.')
        return
        
    def emit(self, substitutions):
        if self.substitution not in substitutions:
            return ''
        return ''.join(tok.emit(substitutions) for tok in self.value)

class ParseError(Exception):
    pass

class WatchRule(object):
    """A watch rule.
    
    A rule consists of the following components:
    
        address     The address (representing an interface) to listen on.
        port        The port to listen on.
        matchex     A match expression which should return some matched value.
        keypattern  A key pattern consisting of literals and substitutions.
        ttl         The time-to-live to be assigned to Redis keys.
        buckets     Number of buckets. The TTL will be divided into the buckets.
        source      A (relatively arbitrary) source identifier, e.g. hostname.
    
    All of these can be defaulted or redefined by using rules.define(). See the
    sample configuration.
    
    The following are generated internally:
    
        start_ts    If defined (set it to None) then a starting timestamp is tracked
                    for buckets.
        matched     The captured part of matchex.
    
    The following is defaulted internally:
    
        postproc    A python function which returns a dictionary of substitutions.

    All of the above can be substituted into the keypattern. (Why would you want to
    substitute keypattern into the keypattern? Never mind, I don't wanna know!)
    
    NOTE: ttl is utilized to set the TTL of the redis key, and is not normally
    substituted into the key. On the other hand start_ts (which is often incorporated
    into the key, and representing when the bucket was started) is internally generated
    and cannot be overridden.
    
      * More than one rule can watch / listen on the same address + port.
      * More than one source can post to the same address + port.
    
    This is to minimize the number of ports that the agent needs to listen on.
    
    Things that are only differentiated by the matchex but are coming from different
    sources may need to send to different ports. For instance if you're matching the
    mail or webserver log(s) from multiple servers behind a load balancer, you probably
    want that reflected in the source; and for that reason you'd want those servers to
    post to different ports. Alternatively you could insert some string into
    the message(s) on the sending side and look for it in the matchex.
    
    keypatterns
    -----------
    
    Keypatterns consist of literals and substitutions.
    
    Substitution:
    
    A substitution consists of a component (above) enclosed in angle brackets:
    
        <address>
        <start_ts>
        
    They can be interspersed with literals. In this example, ";" is a literal:
    
        <address>;<start_ts>
        
    They can be optional, and the optional part can contain literals:
    
        {;<start_ts>}
        
    postprocs
    ---------

    The postproc is supplied with the match object generated after a successful scan
    for the matchex. The default postproc is essentially a dict with the one key
    "matched" representing the single match expected to be produced by the matchex:
    
        lambda matched: dict(matched=matched.group(1))
        
    If defined it can return None, signaling that the match should be ignored.
    
    postprocs are useful:
    
      * if the matchex returns multiple match groups
      * if the matched value requires additional processing for safety, brevity, etc.
      * if there are cases which the matchex produces which should be ignored
     
    """
    
    def __init__(self, defaults, *args, **kwargs):
        substitutions = defaults.copy()
        for i,arg in enumerate(args):
            substitutions[self.POSITIONAL_ARGS[i]] = arg
        substitutions.update(kwargs)
        self.substitutions = substitutions
        self.start_ts = None
        if 'buckets' in substitutions and substitutions['buckets']:
            self.bucket_time = int(substitutions['ttl'] / substitutions['buckets'])
        else:
            self.bucket_time = int(substitutions['ttl'])
        self.keypattern = self.parse_keypattern(substitutions['keypattern'])
        return
    
    def parse_keypattern(self, pattern, context=TOKEN_SETS['OUTER_TOKENS']):
        items = []
        for matchop in re.finditer(context, pattern):
            spec = matchop.lastgroup
            inner = TOKEN_SPECS[spec].match(matchop.group(spec)).group(1)
            if   spec == 'OPTIONAL':
                items.append(
                    OptionalToken(spec, 
                        self.parse_keypattern(inner, context=TOKEN_SETS['OPTIONAL_TOKENS'])
                    )
                )
            elif spec == 'BAD':
                raise ParseError('Syntax error in "{}"'.format(pattern))
            else:
                items.append(
                    Token(spec, inner)
                )
        return items
    
    def generate_key(self):
        k = []
        for tok in self.keypattern:
            k.append(tok.emit(self.substitutions))
        return ''.join(k)
    
    def new_ts(self):
        self.start_ts = time()
        self.substitutions['start_ts'] = str(int(self.start_ts))
        return

    def key(self, **updates):
        """Returns the Redis key.
        
        NOTE: start_ts is only updated if it already exists as a key. This allows
        for it to be optional in a rule. Technically speaking the keypattern is
        parsed and the optionality of start_ts is determined at that time.
        """
        if updates:
            self.substitutions.update(updates)
        if ( 'start_ts' in self.substitutions
         and (
             not self.start_ts or (time() - self.start_ts) > self.bucket_time
           ) ):
            self.new_ts()
        return self.generate_key()

class DictOfLists(dict):
    def append(self, k, v):
        if k not in self:
            self[k] = []
        self[k].append(v)
        return

class PortMissingError(Exception):
    pass

class RegexError(Exception):
    pass

class WatchList(object):
    """The watch list.
    
    There are three kinds of errors this can be expected to raise due to user
    error:
    
        Parse Time
        ----------
        ParseError          An error detected when a rule is defined.
        PortMissingError    Address or port missing / invalid for rule.
        
        Run Time
        ----------
        KeyError            An error when attempting to generate a key.
    """
    PORT_KEY_FORMAT = '{}:{}'

    def __init__(self):
        self.rules = []
        self.defaults = dict()
        self.port_rules = DictOfLists()
        return
    
    def define(self,**kwargs):
        """Define one or more default substitution values."""
        self.defaults.update(kwargs)
        return
    
    def undef(self,*args):
        """Undefine one or more default substitution values."""
        for k in args:
            del self.defaults[k]
        return
    
    def rule(self, *args, **kwargs):
        """Define a WatchRule.
        
        The following are the allowed positional arguments. They may also be
        specified as positional arguments:
        
          * address
          * port
          * matchex
          * keypattern
          * ttl
          * buckets
          * source        
        """
        rule = WatchRule( self.defaults, *args, **kwargs )
        self.rules.append( rule )

        try:
            rule.substitutions['matchex'] = re.compile(rule.substitutions['matchex'])
        except Exception as e:
            raise RegexError('Invalid matchex: {}:{}'.format(type(e).__name__, e))

        try:
            rule.substitutions['address'] = ip_address(rule.substitutions['address'])
            rule.substitutions['port'] = int(rule.substitutions['port'])
            self.port_rules.append(
                self.PORT_KEY_FORMAT.format( rule.substitutions['address'], rule.substitutions['port']
                ), rule
            )
        except:
            raise PortMissingError('Missing / invalid address or port for "rule({},{})"'.format(
                        ','.join(str(arg) for arg in args),
                        ','.join('='.join((str(k), str(v))) for k,v in kwargs.items())
                  )     )

        return
    
    def match(self, address, port, message):
        """Triggers any rules which match.
        
        Matching requires address, port and also the match expression in the
        rule to match.
        
        Returns a list of tuples of the keys to write to + TTL.
        """
        matches = []
        
        port_key = self.PORT_KEY_FORMAT.format(address, port)
        if port_key not in self.port_rules:
            return matched

        for rule in self.port_rules[port_key]:
            matched = rule.substitutions['matchex'].search(message)
            if not matched:
                continue
            if 'postproc' in rule.substitutions:
                try:
                    kwargs = rule.substitutions['postproc'](matched)
                except Exception as e:
                    logging.warn('postproc error: {} prefix={} in <{}>'.format(
                                    e, rule.substitutions.get('prefix','--none--'), message
                                ) )
                    kwargs=None
            else:
                kwargs = dict(matched=matched.group(1))
            if kwargs is None:
                continue
            matches.append( (rule.key(**kwargs), rule.substitutions['ttl']) )
        
        return matches
