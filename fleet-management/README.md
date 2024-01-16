# Fanout System Health Check

This script uses `../fanout` to perform a (fanout) health check.

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
