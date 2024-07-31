import os

import redis


class WatchedFilter:
    def __init__(self):
        self.redis_connection = redis.Redis(
            os.environ.get('REDIS_HOST', 'localhost'),
            port=int(os.environ.get('REDIS_PORT', 6397)),
            password=os.environ.get('REDIS_PASSWORD')
        )

    def add(self, user_id, item_id):
        try:
            self.redis_connection.set(f'{user_id}-{item_id}', 1)
        except redis.exceptions.ConnectionError:
            # ignore errors if redis unavailable
            pass

    def remove_all(self):
        try:
            self.redis_connection.delete('*')
        except redis.exceptions.ConnectionError:
            # ignore errors if redis unavailable
            pass
