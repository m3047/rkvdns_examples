"""Agent Configuration. This is unambiguously a Python sourcefile.

There are a few bits which are global, but most of the working stuff,
such as what port(s) to listen on and what to listen for, are in a DSL
which is built on top of Python. I don't know why I'm apologizing for this,
how many DAGs have I written in not only Python, but Java?

FOR FURTHER INFORMATION: See the pydoc for totalizer.agent_utils.WatchRule
"""

from totalizer.agent_utils import WatchList
rules = WatchList()

REDIS_SERVER = '10.0.0.224'
REDIS_CONNECTIONS = 2
REDIS_QUEUE_MAX = 100
# Set this to an integer number of seconds to log statistics at intervals.
# STATS = 3600 # one hour
STATS = 60

# Determines the logging level if not None
import logging
LOG_LEVEL = logging.INFO # to set it to INFO
# LOG_LEVEL = None

SOURCE = 'sophia'

rules.define(
        address =       '127.0.0.1',    # to listen on
        port =          3430,           # to listen on
        keypattern =    '<prefix>;<matched>;<source>;<start_ts>',
        source =        SOURCE,         # to differentiate sources
        ttl =           86400,          # for the Redis key
        buckets =       4,              # buckets should never be zero, but can be undefined
        start_ts =      None            # simply defining it enables it
    )

# Web pages.
rules.rule(
        prefix =        'web_page',
        matchex =       r'"GET .*?([^/]+[/]?) HTTP/'
    )

# Web clients with statuses.
def web_client_postproc(matched):
    return dict(
            matched = '{},{}'.format(matched.group(1), matched.group(2))
        )
rules.rule(
        prefix =        'web_client',
        matchex =       r'^([^ ]+).*?"GET .*? HTTP/[^"]*" (\d\d\d)',
        postproc=       web_client_postproc
    )

