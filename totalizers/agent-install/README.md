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
