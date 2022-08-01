# Peers

Show netflow peers of a host.

    peers.py <fqdn> [<rkvdns-domain> [<dns-server>] ] {+debug}
    
No external dependencies, however assumes you've got some DNS resources
configured.

* [rkvdns](https://github.com/m3047/rkvdns)
* [shodohflo](https://github.com/m3047/shodohflo)
* [rear_view_rpz](https://github.com/m3047/rear_view_rpz)

In the configured environment _RKVDNS_ is proxying the _ShoDoHFlo_ database, and the
preferred DNS server is running _Rear View RPZ_. This makes for output like
this:

```
# ./peers.py sophia.m3047
ec2-44-238-3-246.us-west-2.compute.amazonaws.com.
alive.github.com.
avatars.githubusercontent.com.
github.com.
shavar.services.mozilla.com.
github.githubassets.com.
collector.github.com.
api.github.com.
github.com.
collector.github.com.
firefox.settings.services.mozilla.com.
api.github.com.
content-signature-2.cdn.mozilla.net.
```

