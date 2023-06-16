# Fanout

The notion of _fanout_ is to make the same request against multiple RKVDNS instances:

```
>>> import fanout
>>> from dns.resolver import Resolver
>>> def query(server,q):
...   try:
...     return [rr.to_text() for rr in Resolver().query('{}.{}'.format(q,server), 'TXT')]
...   except Exception as e:
...     print(e)
...   return []
... 
>>> fanout.BaseName('redis.m3047').map( query, 'test*.keys' )
{'redis.flame.m3047': ['"test;bar"'], 'redis.athena.m3047': ['"test;foo"'], 'redis.sophia.m3047': ['"test;baz"']}
```

This works because `redis.m3047` resolves to multiple `PTR` records (which is what you need to set up for yourself):

```
# dig redis.m3047 any +answer

; <<>> DiG 9.12.3-P1 <<>> redis.m3047 any +answer
;; global options: +cmd
;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 37610
;; flags: qr aa rd ra; QUERY: 1, ANSWER: 3, AUTHORITY: 1, ADDITIONAL: 2

;; OPT PSEUDOSECTION:
; EDNS: version: 0, flags:; udp: 1280
; COOKIE: 9aa4d3f3de7a38be30269d14648b6593bed2a4c9feed7001 (good)
;; QUESTION SECTION:
;redis.m3047.                   IN      ANY

;; ANSWER SECTION:
REDIS.m3047.            600     IN      PTR     REDIS.SOPHIA.M3047.
REDIS.m3047.            600     IN      PTR     REDIS.ATHENA.M3047.
REDIS.m3047.            600     IN      PTR     REDIS.FLAME.M3047.

;; AUTHORITY SECTION:
m3047.                  600     IN      NS      ATHENA.m3047.

;; ADDITIONAL SECTION:
ATHENA.m3047.           600     IN      A       10.0.0.220
```
## Let me save you some grief...

I've neglected to supply `task` as the first argument to `BaseName.map()` several times. It always
produces inscrutable runtime messages.
