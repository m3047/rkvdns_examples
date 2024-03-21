# Totalizers

The notion here is to create aggregating keys in Redis which can then be reported upon with RKVDNS.
There are two parts to this:

* The **agent** which listens for UDP traffic and updates Redis keys
* The **totalizing client** which uses RKVDNS to query Redis and returns totals.

#### The challenge

The challenges which are addressed are:

* collection, network or server failure interrupting service
* multiple sources of the same data

For context, imagine you have a load balancer with several servers behind it, all serving the same content.
You want to be able to aggregate across all servers, as well as report on individual servers. Of course,
you have a load balancer because the individual servers are not completely reliable and periodically
restart themselves.

## The Agent

The Agent (`agent.py`) listens on one or more UDP ports for line-oriented, log-type data. It parses those
lines based on a configuration harkening to _fail2ban_ and increments Redis keys accordingly; it also sets
the TTL on those keys.

A _total_ is represented by multiple keys. Conceptually:

* a total can be partitioned by _source_
* a source has one or more time-bounded _buckets_

This is captured in a _keypattern_. Here is the keypattern used in the sample file:

```
<prefix>;<matched>;<source>;<start_ts>
```

* **prefix** represents the particular _totalizer_
* **matched** represents a part of the totalizer space being counted (a _total_)
* **source** represents a particular server
* **start_ts** is when the bucket was first created

#### Feeding the beast

The sample is analyzing an _Apache_ access log. All we're using to send it to the Agent is:

```
tail -f access_log | nc -u 127.0.0.1 3430
```

If you needed something more featureful and complicated, you could use for example _Logstash_.

#### You can point syslog (UDP) at it

Somebody asked, and so I wrote an article about it:
[Can I send Syslog Data to the Totalizer, and What Has Redis Got To Do With It?](http://consulting.m3047.net/dubai-letters/syslog-totalizer-redis.html)

## The Client(s)

__Further information and examples will follow.__

Take a look at `totalizer.client_utils`, in particular `total()`. Here's an interactive
Python example:

```
>>> from totalizer.client_utils import total
>>> total(['web_client',None], 4, 3600, 'redis.sophia.m3047')
{'10.0.0.224,200': 7, '10.0.0.224,304': 2}
```

Two command line clients are provided for demonstration purposes:

```
# pages 86400 +count +trend | sort
a                               1   0.00
about.php                       1   0.00
ads.txt                         1   0.00
app.d7b0caa9.js                 2   2.00
auth_simple.php                 1   0.00
c/                              1   4.00
config                          2   2.00
dev/                            1   0.00
ecp                             2   2.00
.env                            2   0.00
favicon.ico                    12   1.67
file.ext                        1   0.00
health                          1   0.00
humans.txt                      1   0.00
...
# clients 86400 +count +trend | sort     
10.0.0.118          200     18   0.67
100.24.29.155       200      1   0.00
101.0.73.142        404      1   0.00
109.248.6.38        200      2   2.00
110.235.254.248     200      1   0.00
112.46.68.26        400      1   4.00
117.215.147.106     200      1   0.00
118.126.82.157      404      2   2.00
120.78.170.21       400      1   0.00
124.156.223.97      200      1   0.00
137.175.42.66       200      1   0.00
138.246.253.24      200      1   0.00
139.198.41.148      200      1   0.00
149.18.50.22        404      1   0.00
...
```

## Fanout

One example is provided of `fanout`: the ability to send a query to multiple RKVDNS instances and aggregate the data from all of them.

* `clients_fanout.py` The fanout version of `clients.py`.
* `totalizer.fanout.BaseName` The fanout replacement for `totalizer.client_utils.total`

I suggest doing a diff of `clients.py` and `clients_fanout.py`:

```
43c51
< from totalizer.client_utils import total
---
> from totalizer.fanout import BaseName
96c104,106
<     counts = total(search_spec, 4, window, rkvdns, **kwargs)
---
>     
>     rkvdns = BaseName(rkvdns)
>     counts = rkvdns.total(search_spec, 4, window, **kwargs)
98c108
<         recent_counts = total(search_spec, 4, int(window * TREND_WINDOW), rkvdns, **kwargs)
---
>         recent_counts = rkvdns.total(search_spec, 4, int(window * TREND_WINDOW), **kwargs)
```

To make this work `RKVDNS` (or the equivalent command line argument) should be an FQDN which resolves to one or more (probably more!) `PTR` records,
each representing one RKVDNS instance. `../fanout/README.md` has more information.

## The Administrivia

#### TTL

Most importantly the TTL utilized by the Agent defines the ___maximum___ reporting window. You're going to
be referencing it via the DNS, which does a really good job of caching: you might want to report on data for
the past 24 hours, but you probably don't want to wait that long for the data to refresh!

This means that you should choose the RKVDNS TTLs with care. In the RKVDNS configuration:

* `DEFAULT_TTL` will be used for the Redis (wildcarded) `keys` query. I set this to 30 seconds so that new values show up fairly quickly.
* `MAX_TTL` determines how often the data for individual values is refreshed. I set this to 5 minutes.

#### Testing Agent Configurations

I assume you'll make your own configs, and testing should be easy... I hope you agree! If you have a configuration you'd
like to test and it's named `test_config.py` then you can run:

```
agent test_config +test
```

and instead of writing to Redis it will write the keys to STDOUT.

**NOTE:** If you're running this on the same node where for example your live agent is capturing on port 3430,
you need to specify a different port to listen on in your `test_config`.
