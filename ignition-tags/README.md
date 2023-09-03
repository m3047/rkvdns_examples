# Tags in _Ignition SCADA_

[Ignition](https://inductiveautomation.com/) is a _SCADA_ platform which bundles the _Azul_ JVM, which in turn bundles _Python 2.7_ (Jython).

Any DNS `A` (address) record can be read, converted into an integer value, and used to update a tag without installation of third party
libraries. Presuming you've got a _Redis_ key named `test_x` and an _RKVDNS_ instance which talks to us and is delegated the `redis.sophia.m3047`
namespace, the following can be run as a _gateway timer_ script to update the `RKVDNS_Tag`:

```
from socket import gethostbyname, inet_aton
from struct import unpack

from com.inductiveautomation.ignition.common.model.values import BasicQualifiedValue, QualityCode

TAG = "RKVDNS_Tag"
RKVDNS_GATEWAY = "redis.sophia.m3047"
REDIS_KEY = "test_x"

try:
    value = unpack('>l',inet_aton(gethostbyname(REDIS_KEY+'.get.'+RKVDNS_GATEWAY)))[0]
    quality = QualityCode.Good
except Exception as e:
    value = system.tag.readBlocking([TAG])[0].value
    quality = QualityCode.Bad
    system.util.getLogger(TAG).error(str(e))
bqv = BasicQualifiedValue(value, quality, system.date.now())
system.tag.writeBlocking([TAG], [bqv])
```

* `gethostbyname()` retrieves the `A` record for `test_x.get.redis.sophia.m3047.`
* `inet_aton()` converts this from "dotted quad" to a (big endian) binary string
* `unpack()` converts this from a binary string to a _python_ integer

We take advantage of the fact that although _RKVDNS_ conceptually prefers returning `TXT` records, if you ask for an `A`
record and the value can be converted to a 32 bit int _RKVDNS_ will return it as an "address".

### Some caveats

The implementation of `gethostbyname()` is unreasonably paranoid about DNS labels and insists that they roughly conform
to "hostname" syntax; this accrues to the targets of `CNAME`s too. In regex speak your _Redis_ key needs to be restricted
to the character set `[-_0-9a-z]`.

The DNS is not case sensitive, and may change case on you for no good reason. Because of this and the foregoing limitation
on the allowed characters in a label, it is strongly recommended that you set _RKVDNS_ case folding to either `lower` or `upper`
(and eschew per-character escaping), choosing your _Redis_ keys accordingly.

TTLs matter for how quickly changes are reflected in the tag. You have the TTLs in both _Redis_ and _RKVDNS_ to consider.
As a practical consideration I wouldn't expect a key update to be reflected in less than 30 seconds (TTL of 30), and in
consideration of that an update frequency for the _gateway timer_ script of 5 seconds is probably overkill.

 The above conversion is _signed_, meaning that the value range is -2,147,483,648 to 2,147,483,647.

### General observations about DNS A records

An `A` record represents an _IPv4_ address, or in other words an unsigned 32 bit big endian integer.

* `0.0.0.1` is **1**
* `0.0.0.255` is **255**
* `0.0.1.0` is **256**

...and so on. You can use any DNS record you like and any address you like, subject to the first caveat above about the
implementation of `gethostbyname()` and the second caveat about case insensitivity. You don't have to use _RKVDNS_.

### RKVDNS, especially timeouts (TTLs)

_Redis_ has TTLs (time to live), and _RKVDNS_ allows you to specify TTLs which override the _Redis_ values; a caching nameserver
(which you should have in front of _RKVDNS_ in all but the simplest configurations) also manage and potentially override TTLs.

The ultimate TTL after everybody has their hands on it will control how quickly changes in the DNS value are seen in the tag; it
also controls how often e.g. _RKVDNS_ is expected to requery the _Redis_ key.
