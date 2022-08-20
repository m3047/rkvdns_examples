***I have a feeling...*** that this may turn into a menagerie.

```
# ./test_data.py 10.0.0.224
# hosts 10.1.0.0/24
10.1.0.11
10.1.0.12
10.1.0.10
# peers 10.1.0.10
www.cnn.com.
infoblox.com.
# peers 10.1.0.11
www.microsoft.com.
www.cnn.com.
# peers 10.1.0.12
www.microsoft.com.
infoblox.com.
# pcompare any same 10.1.0.10 10.1.0.0/24
infoblox.com.
www.cnn.com.
# pcompare all same 10.1.0.10 10.1.0.0/24  
# pcompare any diff 10.1.0.10 10.1.0.0/24       
# pcompare all diff 10.1.0.10 10.1.0.0/24  
infoblox.com.
www.cnn.com.
```

# Peers

Show netflow peers of a host. Requires `dnspython`.

    peers.py <fqdn> [<rkvdns-domain> [<dns-server>] ] {+debug}
    
No external dependencies other than `dnspython`, however assumes
you've got some DNS resources configured.

* [rkvdns](https://github.com/m3047/rkvdns)
* [shodohflo](https://github.com/m3047/shodohflo) just the pcap agent is required
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

# hosts

Show hosts on a network.

    hosts.py <network>

```
# ./hosts.py 10.0.1.0/24
kindle.m3047.
UPSTAIRS-ROKU.M3047.
```

# compare

Compare peers of an fqdn to those of the network.

    compare.py [any|all] [same|different] <fqdn> [<network> | <fqdn>][...] {+addresses}
