import random
import os
from typing import List

import numpy as np
import redis
from fastapi import FastAPI

from models import InteractEvent, RecommendationsResponse, NewItemsEvent
from watched_filter import WatchedFilter

app = FastAPI()

redis_conn = 'redis://{username}:{password}@{host}:{port}/0'.format(
    username=os.environ.get('REDIS_USER', 'default'),
    password=os.environ.get('REDIS_PASSWORD'),
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=os.environ.get('REDIS_PORT', 6379),
)
redis_connection = redis.Redis.from_url(redis_conn)
watched_filter = WatchedFilter()

unique_item_ids = set()
EPSILON = 0.05


@app.get('/healthcheck')
def healthcheck():
    return 200


@app.get('/cleanup')
def cleanup():
    global unique_item_ids
    unique_item_ids = set()
    try:
        redis_connection.delete('*')
        redis_connection.json().delete('*')
    except redis.exceptions.ConnectionError:
        pass
    return 200


@app.post('/add_items')
def add_movie(request: NewItemsEvent):
    global unique_item_ids
    for item_id in request.item_ids:
        unique_item_ids.add(item_id)
    return 200


@app.get('/recs/{user_id}')
def get_recs(user_id: str):
    global unique_item_ids

    try:
        item_ids = redis_connection.json().get('top_items')
    except redis.exceptions.ConnectionError:
        item_ids = None

    if item_ids is None or random.random() < EPSILON:
        item_ids = np.random.choice(list(unique_item_ids), size=20, replace=False).tolist()
    return RecommendationsResponse(item_ids=item_ids)


@app.post('/interact')
async def interact(request: InteractEvent):
    watched_filter.add(request.user_id, request.item_id)
    return 200
