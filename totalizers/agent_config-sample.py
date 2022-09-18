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
        # If no postprocessor is provided, the first capture pattern is returned.
        # If you're a practitioner of the black arts, technically you can put other
        # keys in the dictionary and then reference them in the keypattern.
        # postproc =    lambda matched: dict(matched=matched.group(1))
    )

# Web pages. Unfortunately nothing is easy. We can't trust user input to be
# sane.
def web_page_postproc(matched):
    value = matched.group(1)

    # There is a hard limit on DNS keys of 255 bytes, we need to fit in that
    # while also including the other parts of the key.
    if len(value) > 64:
        value = value[:64]

    # We're using ";" as our delimiter.
    value = value.strip(';').split(';')[0]

    # DNS is case-insensitive. We're running the RKVDNS instance serving this
    # Redis database in lowercase mode. There is a per-character escaping mode,
    # but this is good enough for our purposes.
    value = value.lower()

    return dict(matched=value)
rules.rule(
        prefix =        'web_page',
        matchex =       r'"(?:GET|POST) .*?([^/]+[/]?) HTTP/',
        postproc =      web_page_postproc
    )

# Web clients with statuses.
def web_client_postproc(matched):
    return dict(
            matched = '{},{}'.format(matched.group(1), matched.group(2))
        )
rules.rule(
        prefix =        'web_client',
        matchex =       r'^([^ ]+).*?"(?:GET|POST) .*? HTTP/[^"]*" (\d\d\d)',
        postproc=       web_client_postproc
    )

