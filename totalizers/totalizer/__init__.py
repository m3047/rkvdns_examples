"""Totalizer Utilities.

This is in two parts:

 * agent_utils:     for the agent feeding Redis
 * client_utils:    for consumers of the Redis data

Together the agent and client(s) implement time windowed counters for events
of interest.

Architecturally, a capture window period (also used as the TTL for Redis) is
divided into buckets. The buckets have starting timestamps. Then we do some
magic to collect all of the buckets and summarize them.
"""
