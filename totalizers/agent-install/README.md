# Quick install instructions for the Totalizer Agent

### Prerequisites

* netcat
* (plain) (python) redis

### 1) Clone this repo

Clone the repo into `/usr/local/share/`

### 2) Copy `totalizer-log-agent` to `/usr/sbin/`

### 3) Copy `*.service` to `/etc/systemd/system/`

### 4) Create the config file for the Totalizer Agent

Copy `agent_config-sample.py` to `agent_config.py` and edit, paying attention to the following items:

* `REDIS_SERVER`: where to contact the Redis service.
* `STATS`: 60 seconds is the least practical setting. I recommend 3600 (1 hour) or `None` to disable statistics reporting entirely.
* `LOG_LEVEL`: maybe you don't want `INFO`? It's up to you.
* `SOURCE`: an identifier for the server / service.
* `address` and `port`: where to listen for UDP traffic. If you change these you will need to edit `apache-log-agent.service` as well.
* `ttl` and `buckets`: as shipped it uses 4 buckets every 24 hours. **NOTE:** This TTL is the Redis TTL, see the note in the parent directory about RKVDNS TTL settings.
* `prefix`: adjust if needed to avoid namespace conflicts.

### 5) Adjust the Apache log rotation

After log rotation, Apache is restarted. `apache-log-agent` also needs to be restarted.

Refer to `logrotate-apache2` in this directory.

### 6) Start the services

```
systemctl enable apache-log-agent totalizer-agent
systemctl start totalizer-agent
systemctl start apache-log-agent
```
## A note about the totalizer-log-agent

All this is doing is tailing the log and piping that to _netcat_ (`nc`). `nc` will quit with no warning if the UDP
socket the totalizer agent is supposed to be listening to is unavailable, and this leaves the `tail` running and consuming
100% of CPU (at least on SuSE Leap 15.0). If you want it to start at system boot, you may need to put a one-shot timer in
front of it to give the agent a chance to start up.
