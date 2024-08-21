import os
import asyncio
import json
import time
import logging

import redis
import aio_pika
from aio_pika import Message
from aio_pika.abc import AbstractRobustExchange, AbstractRobustConnection
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import InteractEvent
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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE", "PATCH", "PUT"],
    allow_headers=["Content-Type", "Set-Cookie", "Access-Control-Allow-Headers", "Access-Control-Allow-Origin",
                   "Authorization"],
)

@app.get('/healthcheck')
def healthcheck():
    logging.info('/healthcheck')
    return 200


@app.post('/interact')
async def interact(message: InteractEvent):
    logging.info(f'/interact {message.user_id} {message.item_ids}')
    message.timestamp = time.time()
    await publish_message(Message(
        bytes(json.dumps(message.model_dump()), "utf-8"),
        content_type="text/json",
    ))

    for item_id in message.item_ids:
        await watched_filter.add(message.user_id, item_id)
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


async def publish_message(message: Message):
    rabbitmq_exchange = await create_rabbitmq_exchange()
    await rabbitmq_exchange.publish(
        message,
        routing_key,
    )
