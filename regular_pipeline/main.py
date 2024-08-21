import asyncio
import json
import os.path
import time

import aio_pika
import polars as pl
import redis
from aio_pika import Message

redis_conn = 'redis://{username}:{password}@{host}:{port}/0'.format(
    username=os.environ.get('REDIS_USER', 'default'),
    password=os.environ.get('REDIS_PASSWORD'),
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=os.environ.get('REDIS_PORT', 6379),
)
print(redis_conn)
redis_connection = redis.Redis.from_url(redis_conn)


async def collect_messages():
    conn_url = "amqp://{}:{}@{}/".format(
        os.environ.get('RABBITMQ_USER', 'guest'),
        os.environ.get('RABBITMQ_PASS', 'guest'),
        os.environ.get('RABBITMQ_HOST', 'localhost')
    )
    print(conn_url)
    connection = await aio_pika.connect_robust(
        conn_url,
        loop=asyncio.get_event_loop(),
        port=int(os.environ.get('RABBITMQ_PORT', 5672))
    )

    queue_name = "user_interactions"
    routing_key = "user.interact.message"
    exchange = "user.interact"

    async with connection:
        # Creating channel
        channel = await connection.channel()

        # Will take no more than 10 messages in advance
        await channel.set_qos(prefetch_count=10)

        # Declaring queue
        queue = await channel.declare_queue(queue_name)

        # Declaring exchange
        exchange = await channel.declare_exchange(exchange, type='direct')
        await queue.bind(exchange, routing_key)
        # await exchange.publish(Message(bytes(queue.name, "utf-8")), routing_key)

        t_start = time.time()
        data = []
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    message = message.body.decode()
                    message = json.loads(message)
                    data.append(message)
                    if time.time() - t_start > 10:
                        print('saving events from rabbitmq')
                        print(data)
                        # update data if 10s passed
                        new_data = pl.DataFrame(data).explode(['item_ids', 'actions']).rename({
                            'item_ids': 'item_id',
                            'actions': 'action'
                        })

                        if len(new_data) > 0:
                            if os.path.exists('./data/interactions.csv'):
                                data = pl.concat([pl.read_csv('./data/interactions.csv', schema_overrides={'item_id': pl.String}), new_data])
                            else:
                                data = new_data
                            data.write_csv('./data/interactions.csv')

                        data = []
                        t_start = time.time()



async def calculate_top_recommendations():
    while True:
        if os.path.exists('./data/interactions.csv'):
            print('calculating top recommendations')
            interactions = pl.read_csv('./data/interactions.csv', schema_overrides={'item_id': pl.String})
            top_items = (
                interactions
                .sort('timestamp')
                .unique(['user_id', 'item_id', 'action'], keep='last')
                .filter(pl.col('action') == 'like')
                .group_by('item_id')
                .len()
                .sort('count', descending=True)
                .head(500)
            )['item_id'].to_list()

            top_items = [str(item_id) for item_id in top_items]

            redis_connection.json().set('top_items', '.', top_items)
        await asyncio.sleep(10)


async def main():
    await asyncio.gather(
        collect_messages(),
        calculate_top_recommendations(),
    )


if __name__ == '__main__':
    asyncio.run(main())
