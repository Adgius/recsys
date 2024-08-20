import os
import asyncio
import json
import time
import logging

import redis
import aio_pika
from aio_pika.abc import AbstractRobustExchange, AbstractRobustConnection
from fastapi import FastAPI

from models import RecommendationsResponse, NewItemsEvent
from watched_filter import WatchedFilter

logging.basicConfig(level=logging.INFO, filename=".logs",filemode="w",
                    format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI()
redis_conn = 'redis://{username}:{password}@{host}:{port}/0'.format(
    username=os.environ.get('REDIS_USER', 'default'),
    password=os.environ.get('REDIS_PASSWORD'),
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=os.environ.get('REDIS_PORT', 6379),
)
redis_connection = redis.Redis.from_url(redis_conn)
watched_filter = WatchedFilter()

queue_name = "user_interactions"
routing_key = "user.interact.message"
exchange = "user.interact"

_rabbitmq_connection: AbstractRobustConnection = None
_rabbitmq_exchange = None

unique_item_ids = set()
EPSILON = 0.05


@app.get('/healthcheck')
def healthcheck():
    logging.info('/healthcheck')
    return 200


@app.post('/add_items')
def add_movie(request: NewItemsEvent):
    global unique_item_ids
    for item_id in request.item_ids:
        logging.info(f'/add_item {item_id}')
        unique_item_ids.add(item_id)
    return 200


@app.get('/recs/{user_id}')
def get_recs(user_id: str):
    logging.info(f'/recs/{user_id}')
    global unique_item_ids

    try:
        item_ids = redis_connection.json().get('top_items')
    except redis.exceptions.ConnectionError:
        item_ids = None

    if item_ids is None or random.random() < EPSILON:
        item_ids = np.random.choice(list(unique_item_ids), size=20, replace=False).tolist()
    return RecommendationsResponse(item_ids=item_ids)

@app.post('/cleanup')
async def cleanup():
    logging.info(f'/cleanup')

    # Clear Redis
    global unique_item_ids
    unique_item_ids = set()
    redis_connection.flushall()
    
    # Clear RabbitMQ
    global _rabbitmq_exchange, _rabbitmq_connection
    await create_rabbitmq_exchange()

    # Getting channel
    channel = await _rabbitmq_connection.channel()

    # Getting queue
    queue = await channel.declare_queue(queue_name)

    # Clear queue
    await queue.purge()
    return 200

async def create_rabbitmq_exchange() -> AbstractRobustExchange:
    global _rabbitmq_exchange, _rabbitmq_connection
    if _rabbitmq_exchange is None or _rabbitmq_connection.is_closed:
        conn_url = "amqp://{}:{}@{}/".format(
            os.environ.get('RABBITMQ_USER', 'guest'),
            os.environ.get('RABBITMQ_PASS', 'guest'),
            os.environ.get('RABBITMQ_HOST', 'localhost')
        )
        _rabbitmq_connection = await aio_pika.connect_robust(
            conn_url,
            loop=asyncio.get_event_loop(),
            port=int(os.environ.get('RABBITMQ_PORT', 5672))
        )

        # Creating channel
        channel = await _rabbitmq_connection.channel()

        # Declaring exchange
        _rabbitmq_exchange = await channel.declare_exchange("user.interact", type='direct')

        # Declaring queue
        queue = await channel.declare_queue(queue_name)

        # Binding queue
        await queue.bind(_rabbitmq_exchange, routing_key)
    return _rabbitmq_exchange