#!/usr/bin/python3
# Copyright (c) 2020-2022 by Fred Morris Tacoma WA
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

"""Aggregate Log Lines to Redis Keys.

    agent {<config-name>} {+test}
    
Parameters:

    config-name The name of an alternate config module (just the module name,
                omit .py). Default is agent_config
    test        If supplied, then Redis is not written to and the key which would
                have been written is instead written to stdout.

This is a beast! You define rules (see agent_config.py) and based on those
it:

  * listens on any number of UDP ports
  * processes them based on match expressions
  * uses the foregoing to build Redis keys
  * increments the values associated with said keys
  * and sets the TTL for the key.
  
The intention is that you'd use RKVDNS (https://github.com/m3047/rkvdns)
to query those keys. You can look at totalizer.client for further inspiration
concerning that.

More about Redis
----------------

We use a thread pool to manage redis commits.

REDIS_SERVER expects the address of the Redis instance.

REDIS_CONNECTIONS determines the number of connections established to the database,
as well as the number of threads in the thread pool.

A separate queue is maintained of pending writes. The maximum depth of that queue
is determined by REDIS_QUEUE_MAX. When the queue is full incoming messages (log lines
via UDP) are dropped.
"""

import sysconfig

PYTHON_IS_311 = int( sysconfig.get_python_version().split('.')[1] ) >= 11

import sys
import logging
import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor, CancelledError
import redis

import importlib

if PYTHON_IS_311:
    from asyncio import CancelledError
else:
    from concurrent.futures import CancelledError

# Set this to a print func to enable it.
PRINT_COROUTINE_ENTRY_EXIT = None

# Similar to the foregoing, but always set to something valid.
STATISTICS_PRINTER = logging.info

LOG_LEVEL = None
    
from totalizer.statistics import StatisticsFactory, StatisticsCollector, UndeterminedStatisticsCollector

def lart(msg=None, help='agent {config} {+testing}'):
    if msg:
        print(msg, file=sys.stderr)
    if help:
        print(help, file=sys.stderr)
    sys.exit(1)

class Controller(object):

    CONNECT_TIMEOUT = 5 # for Redis
    
    def __init__(self, redis_server, redis_conns, max_queue, event_loop, testing=False):
        self.max_queue = max_queue
        self.event_loop = event_loop
        self.queue = asyncio.Queue(max_queue)
        self.semaphore = asyncio.Semaphore( redis_conns+1 )
        self.pool = ThreadPoolExecutor(redis_conns)
        if testing:
            self.redis = None
        else:
            self.redis = redis.client.Redis(redis_server, decode_responses=False,
                                            socket_connect_timeout=self.CONNECT_TIMEOUT
                                        )
        self.queue_processor = event_loop.create_task(self.process_queue())
        return

    def queue_full(self):
        return self.queue.qsize() >= self.max_queue
        
    async def submit(self, *args):
        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('> submit')

        await self.queue.put(args)

        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('< submit')
        return
    
    async def process_queue(self):
        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('> process_queue')
            
        while True:
            update = await self.queue.get()
            
            self.queue.task_done()
            await self.semaphore.acquire()
            self.event_loop.run_in_executor(self.pool, self.redis_update, *update)
            
        raise RuntimeError("Control loop should never exit.")
    
    def redis_update(self, key, ttl, redis_timer):
        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('> redis_update')
            
        if self.redis is None:
            print('>> {} <<'.format(key))
        else:
            try:
                exc = result = None
                self.redis.incr( key )
                self.redis.expire( key, ttl )
            except redis.exceptions.RedisError as e:
                logging.error('Redis error: {} {}'.format(type(e).__name__, e))
            except Exception as e:
                logging.error('{}:\n{}'.format(e, traceback.format_exc()))

        asyncio.run_coroutine_threadsafe( self.finish(redis_timer), self.event_loop )
        
        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('< redis_update')
        return
    
    async def finish(self, redis_timer):
        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('> finish')

        self.semaphore.release()
        
        redis_timer.stop()

        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('< finish')
        return

MIN_GOOD_ASCII = 32
MAX_GOOD_ASCII = 126

class UDPListener(asyncio.DatagramProtocol):
    
    def connection_made(self, transport):
        self.transport = transport
        return
    
    @staticmethod
    def asciify(line):
        """Convert nonprintables to hex and convert to unicode."""
        converted = []
        for c in line:
            if c >= MIN_GOOD_ASCII and c <= MAX_GOOD_ASCII:
                converted.append(c)
                continue
            converted += [ ord('\\'), ord('x') ] + [ x for x in '{:02x}'.format(c).encode() ]
        return bytes(converted).decode()
    
    async def handle_request(self, request, datagram_timer):
        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('> handle_request')
        if self.controller.queue_full():
            if PRINT_COROUTINE_ENTRY_EXIT:
                PRINT_COROUTINE_ENTRY_EXIT('< handle_request')
            datagram_timer.stop('dropped')
            return
        
        for line in request.split(b'\n'):
            matched = rules.match(self.local_addr[0], self.local_addr[1], self.asciify(line))
            for match in matched:
                args = match + (self.redis_stats.start_timer(), )
                await self.controller.submit( *args )

        datagram_timer.stop('processed')

        if PRINT_COROUTINE_ENTRY_EXIT:
            PRINT_COROUTINE_ENTRY_EXIT('< handle_request')
        return

    def datagram_received(self, request, addr):
        self.event_loop.create_task(self.handle_request( request, self.datagram_stats.start_timer() ))
        return

def format_statistics(stat):
    if 'depth' in stat:
        return '{}: emin={:.4f} emax={:.4f} e1={:.4f} e10={:.4f} e60={:.4f} dmin={} dmax={} d1={:.4f} d10={:.4f} d60={:.4f} nmin={} nmax={} n1={:.4f} n10={:.4f} n60={:.4f}'.format(
                stat['name'],
                stat['elapsed']['minimum'], stat['elapsed']['maximum'], stat['elapsed']['one'], stat['elapsed']['ten'], stat['elapsed']['sixty'],
                stat['depth']['minimum'], stat['depth']['maximum'], stat['depth']['one'], stat['depth']['ten'], stat['depth']['sixty'],
                stat['n_per_sec']['minimum'], stat['n_per_sec']['maximum'], stat['n_per_sec']['one'], stat['n_per_sec']['ten'], stat['n_per_sec']['sixty'])
    else:
        return '{}: emin={:.4f} emax={:.4f} e1={:.4f} e10={:.4f} e60={:.4f} nmin={} nmax={} n1={:.4f} n10={:.4f} n60={:.4f}'.format(
                stat['name'],
                stat['elapsed']['minimum'], stat['elapsed']['maximum'], stat['elapsed']['one'], stat['elapsed']['ten'], stat['elapsed']['sixty'],
                stat['n_per_sec']['minimum'], stat['n_per_sec']['maximum'], stat['n_per_sec']['one'], stat['n_per_sec']['ten'], stat['n_per_sec']['sixty'])

async def statistics_report(statistics, frequency):
    """The statistics report.
    
    You will need to look through code to determine exactly what is being measured.
    """
    logging.info('statistics_report started')
    while True:
        await asyncio.sleep(frequency)
        for stat in sorted(statistics.stats(), key=lambda x:x['name']):
            STATISTICS_PRINTER(format_statistics(stat))
    return

async def close_tasks(tasks):
    all_tasks = asyncio.gather(*tasks)
    all_tasks.cancel()
    try:
        await all_tasks
    except (CancelledError, redis.exceptions.RedisError):
        pass
    return

def main(testing=False):

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop( event_loop )

    if STATS:
        statistics = StatisticsFactory()
        event_loop.create_task(statistics_report(statistics, STATS))
        datagram_stats = statistics.Collector( ('dropped', 'processed'), using=UndeterminedStatisticsCollector)
        redis_stats = statistics.Collector('redis')
    else:
        statistics = datagram_stats = None

    controller = Controller(REDIS_SERVER, REDIS_CONNECTIONS, REDIS_QUEUE_MAX, event_loop, testing)
    transports = []
    for binding in rules.port_rules.keys():
        address, port = binding.split(':')
        listener = event_loop.create_datagram_endpoint(
            UDPListener,
            local_addr=(address, int(port))
        )
        try:
            transport, service = event_loop.run_until_complete(listener)
        except PermissionError:
            print('Permission Denied! (are you root? is the port free?)', file=sys.stderr)
            sys.exit(1)
        except OSError as e:
            print('{} (did you supply an interface address?)'.format(e), file=sys.stderr)
            sys.exit(1)
            
        service.event_loop = event_loop
        service.controller = controller
        service.datagram_stats = datagram_stats
        service.redis_stats = redis_stats
        service.local_addr=(address, int(port))

        transports.append(transport)

    try:
        event_loop.run_forever()
    except KeyboardInterrupt:
        pass

    for transport in transports:
        transport.close()

    if PYTHON_IS_311:
        tasks = asyncio.all_tasks(event_loop)
    else:
        tasks = asyncio.Task.all_tasks(event_loop)

    if tasks:
        event_loop.run_until_complete(close_tasks(tasks))

    event_loop.close()

if __name__ == "__main__":
    argv = sys.argv.copy()
    
    testing = False
    while len(argv) > 1 and argv[-1].startswith('+'):
        arg = argv.pop()[1:]
        if   arg == 'testing'[:len(arg)]:
            testing = True
    
    if len(argv) > 2:
        lart('Too many arguments')
    
    if len(argv) > 1:
        config_name = argv[1]
    else:
        config_name = 'agent_config'

    try:
        config = importlib.import_module(config_name)
        for sym in ('REDIS_SERVER', 'REDIS_CONNECTIONS', 'REDIS_QUEUE_MAX', 'STATS', 'LOG_LEVEL', 'rules'):
            globals()[sym] = getattr(config, sym)
    except Exception as e:
        lart('Config load for {} failed: {}'.format(config_name, e))
    
    if LOG_LEVEL is not None:
        logging.basicConfig(level=LOG_LEVEL)
    
    main(testing)
