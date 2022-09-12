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

## The Client(s)

__Further information and examples will follow.__

For now, take a look at `totalizer.client_utils`, in particular `total()`. Here's an interactive
Python example:

```
>>> from totalizer.client_utils import total
>>> total(['web_client',None], 3600, 'redis.sophia.m3047')
{'10.0.0.224,200': 7, '10.0.0.224,304': 2}
```

## The Administrivia

#### TTL

Most importantly the TTL utilized by the Agent defines the ___maximum___ reporting window. You're going to
be referencing it via the DNS, which does a really good job of caching: you might want to report on data for
the past 24 hours, but you probably don't want to wait that long for the data to refresh!

This means that you should choose the RKVDNS TTLs with care. In the RKVDNS configuration:

* `DEFAULT_TTL` will be used for the Redis (wildcarded) `keys` query. I set this to 30 seconds so that new values show up fairly quickly.
* `MAX_TTL` determines how often the data for individual values is refreshed. I set this to 5 minutes.

