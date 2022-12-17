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

"""Web Page Hits.

Command line:

    pages.py <window> [<server>] [<rkvd-domain> [<dns-server>]] {+count} {+trend}
    
Lists the number of hits for pages within the window.

    window       The reporting window, in seconds.
    server       The server identifier. If omitted all servers are included. Optionally
                 "-" can be specified as a placeholder representing "all servers".
    rkvd-domain  The domain that rkvdns serves responses under.
    dns-server   This is the (optional) dns server to use for DNS requests.
    counts       If passed, counts are included.
    trend        If passed, a trend is computed and included.
    
Corresponding entries can be set in an optional `client_config.py`:

    RKVDNS      The domain that rkvdns serves responses under. See below.
    DNS_SERVER  The address of the dns server.
    TREND_WINDOW It's possible to override the default trend window, which
                is 0.25 of the reporting window.
    
Refer to the documentation for RKVDNS and totalizer.client_utils.
"""

import sys
from totalizer.client_utils import total

RKVDNS = None
DNS_SERVER = None
TREND_WINDOW = 0.25
MAX_TREND = 9.99

def lart(msg=None, help='pages window [server] [rkvdns-domain [dns-server]]'):
    if msg:
        print(msg, file=sys.stderr)
    if help:
        print(help, file=sys.stderr)
    sys.exit(1)

try:
    from client_config import *
except ImportError:
    pass
except Exception as e:
    lart('{}: {}'.format(type(e).__name__, e))

if RKVDNS is not None:
    RKVDNS = RKVDNS.strip('.').lower()
else:
    RKVDNS = None

NUMBER_OF_PARTS = 4
    
def main( window, server, rkvdns, dns_server, print_count, print_trend ):

    def print_item(item, width, count, trend=None):
        fmt = '{:<{width}s}'
        args = [ item ]
        if print_count:
            fmt += ' {:>6d}'
            args.append(count)
        if print_trend:
            fmt += ' {:>6.2f}'
            base = count * TREND_WINDOW
            if base == 0:
                args.append(MAX_TREND)
            else:
                trend /= base
                args.append( trend > MAX_TREND and MAX_TREND or trend )
        print(fmt.format(*args, width=width))
        return
    
    search_spec = ['web_page', None ]
    if server:
        search_spec.append( server.lower() )
        
    kwargs = dict()
    if dns_server:
        kwargs['nameservers'] = dns_server
    counts = total(search_spec, NUMBER_OF_PARTS, window, rkvdns, **kwargs)
    if print_trend:
        recent_counts = total(search_spec, NUMBER_OF_PARTS, int(window * TREND_WINDOW), rkvdns, **kwargs)
        
    max_k = max(len(k) for k in counts.keys())
    
    trend = None
    for k,v in counts.items():
        if not v:
            continue
        if print_trend:
            trend = recent_counts[k]
        print_item(k, max_k, v, trend)
    
    return

if __name__ == '__main__':
    
    argv = sys.argv

    print_count = False
    print_trend = False
    while argv[-1].startswith('+'):
        arg = argv.pop()[1:]
        if   arg == 'counts'[:len(arg)]:
            print_count = True
        elif arg == 'trends'[:len(arg)]:
            print_trend = True
        else:
            lart('Unrecognized option "{}"'.format(arg))

    if len(argv) < 2:
        lart('No window')
    try:
        window = int(argv[1])
    except:
        lart('Invalid window')
        
    if len(argv) < 3:
        server = None
    else:
        server = argv[2].lower()
    if server and server == '-':
        server = None

    if len(argv) < 4:
        rkvdns = None
    else:
        rkvdns = argv[3].lower()
    if rkvdns is None:
        rkvdns = RKVDNS
    if rkvdns is None:
        lart('RKVDNS domain not specified')

    if len(argv) < 5:
        dns_server = None
    else:
        dns_server = argv[4]
    if dns_server is None:
        dns_server = DNS_SERVER
        
    main( window, server, rkvdns, dns_server, print_count, print_trend)




