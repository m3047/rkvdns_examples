#!/usr/bin/python3
# Copyright (c) 2022-2023 by Fred Morris Tacoma WA
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Totalizer Utilities.

This is in two parts:

 * agent_utils:     for the agent feeding Redis
 * client_utils:    for consumers of the Redis data
 
There is a client (consumer) extension for federated data sources:

   * fanout:        enables consumers to harvest data from multiple
                    federated Redis / RKVDNS sources.

Together the agent and client(s) implement time windowed counters for events
of interest.

Architecturally, a capture window period (also used as the TTL for Redis) is
divided into buckets. The buckets have starting timestamps. Then we do some
magic to collect all of the buckets and summarize them.

Federated Data Sources
----------------------

One of the chief powers of The DNS and a federated architecture is the potential
to do just-in-time harvesting of operational data from distributed sources. To
do this, RKVDNS is specified as an FQDN which resolves to a set of PTR records
each of which specifies an individual RKVDNS instance. (So it's kind of like CNAME
except that there are multiple rnames and they are all queried simultaneously.)
"""
