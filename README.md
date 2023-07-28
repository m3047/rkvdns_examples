# rkvdns_examples
Examples for RKVDNS under a more permissive license.

[RKVDNS](https://github.com/m3047/rkvdns) is licensed under the _Affero General Public License_, but the examples
here are licensed under the _Apache 2.0_ license which is more amenable to commercial use.

Each example is in a separate subdirectory. **If you have an example you'd like to submit, encapsulate it within
a subdirectory and send a PR.** _Python_ is not required, any language will do!

* `fanout` map a function to multiple servers based on DNS PTRs
* `peers` get netflow peers (by name) for a host, and friends `hosts` and `compare`
* `totalizers` UDP listening agent which posts to redis, and RKVDNS reporting tools

In addition to the examples here:

* [The ShoDoHFlo app](https://github.com/m3047/shodohflo/tree/master/app) offers a (readonly) RKVDNS transport.
