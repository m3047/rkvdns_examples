# Fanout Fleet Management

These scripts use `../fanout` to perform a fanout to a fleet of _RKVDNS_ instances.

## Health Check

Command line:
```
health.py <fanout-fqdn>
```
Performs a health check of the specified fanout. See [../fanout/README.md](../fanout/) for a
description of what fanout is and how it works. Essentially PTR records identify
multiple RKVDNS instances to be queried simultaneously (like CNAMEs but different).

The following checks are performed:

* Does the fanout FQDN exist?
* Do all of the enumerated RKVDNS instances answer SOA and NS queries?
* Can the Redis database be read?
* Do the read values comport with what was expected?

Each line contains the following information:

    <rkvdns-zone-name>  [<soa-ns-valid>] [<redis-valid>]

Here is example output:

    # health redis.m3047
    redis.athena.m3047  [SOA] [VAL]
    redis.flame.m3047   [   ] [VAL]
    redis.sophia.m3047  [SOA] [   ]

In the second record, for some reason the SOA / NS records can't be read or have incorrect
values. In the third record the Redis database can't be read or the value was incorrect.

Redis Keys
----------

In the configuration file, the key to be read is specified with `HEALTH_KEY`. The
default is `health` (lower case).

`HEALTH_KEY` Values
-----------------

By default the `HEALTH_KEY` in each Redis instance is supposed to return a value which
is identical to the lower-cased Redis instance name specified with <fanout-fqdn>. It
is also possible to specify a fixed value for all instances, or to have the read value
ignored (only the successful read is evaluated).

`HEALTH_VALUE` can be set to one of the following:

* a string literal    The string literal will be expected for all RKVDNS instances.
* `Fanout_FQDN`         The value should be the (lowercased) fanout instance name.
* `No_Check`            Don't check the value, a successful read is all that is expected.

`Fanout_FQDN` and `No_Check` are singletons.

## Configuration Reporting

Command line:
```
config.py <fanout-fqdn>
```
Here is example output:

```
# config redis.m3047
                     |redis.athena.m3047|redis.flame.m3047|redis.sophia.m3047|
all_queries_as_txt   |False             |False            |False             |
conformance          |True              |True             |True              |
debounce             |True              |True             |True              |
default_ttl          |30                |30               |30                |
enable_error_txt     |False             |False            |False             |
max_tcp_payload      |60000             |60000            |60000             |
max_ttl              |300               |300              |300               |
max_udp_payload      |1200              |1200             |1200              |
max_value_payload    |255               |255              |255               |
min_ttl              |5                 |5                |5                 |
nxdomain_for_servfail|True              |True             |True              |
redis_server         |'127.0.0.1'       |'127.0.0.1'      |'10.0.0.224'      |
redis_timeout        |5                 |5                |5                 |
return_partial_tcp   |False             |False            |False             |
return_partial_value |True              |True             |True              |
```
