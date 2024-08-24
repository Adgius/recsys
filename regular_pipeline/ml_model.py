import polars as pl
import numpy as np
import optuna
import redis
import logging
import os

from gensim.models import Word2Vec

from ml_metrics import user_ndcg, user_recall

RANDOM_STATE = 42
TOP_K = 30

redis_conn = 'redis://{username}:{password}@{host}:{port}/0'.format(
    username=os.environ.get('REDIS_USER', 'default'),
    password=os.environ.get('REDIS_PASSWORD'),
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=os.environ.get('REDIS_PORT', 6379),
)
redis_connection = redis.Redis.from_url(redis_conn)

class W2V_model:

    @classmethod
    def create_dataset(cls):
        logging.info('Creating dataset for w2v ...')
        interactions = pl.read_csv('./data/interactions.csv', schema_overrides={'item_id': pl.String})
        cls.user_mapping = {k: v for v, k in enumerate(interactions['item_id'].unique())}
        cls.user_mapping_inverse = {k: v for v, k in cls.user_mapping.items()}
        
        grouped_df = (
            interactions
            .sort('timestamp')
            # оставляем только положительные взаимодействия
            .filter(pl.col('action') == 'like')
            # .unique(['user_id', 'item_id', 'action'], keep='last')
            .with_columns(pl.col('item_id').map_elements(cls.user_mapping.get))
            .group_by('user_id')
            .agg([
                # для валидации оставим последнее взаимодействие в истории
                pl.col('item_id').map_elements(lambda x: x[:-1]).alias('train_item_ids'),
                pl.col('item_id').map_elements(lambda x: x[-1:]).alias('test_item_ids'),
            ])
            # и оставим только те сессии, где есть какая-то тренировочная выборка
            .filter(pl.col('train_item_ids').list.len() > 0)
        )
        cls.grouped_df = grouped_df
        logging.info('Dataset created!')

    @classmethod
    def evaluate_model(cls, model):
        ndcg_list = []
        recall_list = []
        # для оптимизации вычислений будем оценивать модель только на подвыборке
        for train_ids, y_rel in cls.grouped_df.select('train_item_ids', 'test_item_ids').rows():
            model_preds = model.predict_output_word(
                train_ids[-model.window:],
                topn=(TOP_K + len(train_ids))
            )
    
            if model_preds is None:
                ndcg_list.append(0)
                recall_list.append(0)
                continue
    
            y_rec = [pred[0] for pred in model_preds]
            ndcg_list.append(user_ndcg(y_rel, y_rec, TOP_K))
            recall_list.append(user_recall(y_rel, y_rec, TOP_K))
        return np.mean(ndcg_list), np.mean(recall_list)

    @classmethod
    def objective(cls, trial):
        try:
            sg = trial.suggest_categorical('sg', [0, 1])
            window = trial.suggest_int('window', 1, 10)
            ns_exponent = trial.suggest_float('ns_exponent', -3, 3)
            negative = trial.suggest_int('negative', 3, 20)
            min_count = trial.suggest_int('min_count', 0, 20)
            vector_size = trial.suggest_categorical('vector_size', [16, 32, 64, 128])
        
            logging.info({
                'sg': sg,
                'window_len': window,
                'ns_exponent': ns_exponent,
                'negative': negative,
                'min_count': min_count,
                'vector_size': vector_size,
            })
        
            model = Word2Vec(
                cls.grouped_df['train_item_ids'].to_list(),
                window=window,
                sg=sg,
                min_count=min_count,
                vector_size=vector_size,
                negative=negative,
                ns_exponent=ns_exponent,
                seed=RANDOM_STATE,
                epochs=10,
            )
        
            mean_ndcg, mean_recall = cls.evaluate_model(model)
            logging.info(f'NDCG@{TOP_K} = {mean_ndcg}, Recall@{TOP_K} = {mean_recall}')
        except:
            return 0
        return mean_recall

    @classmethod
    def fit_best(cls, best_params):
        logging.info('Fitting the best model ...')
        try:
            cls.model = Word2Vec(
                cls.grouped_df['train_item_ids'].to_list(),
                epochs=10, 
                **best_params
            )
            logging.info('Best model was created!')
        except BaseException as e:
            logging.critical(e)
            
        
    @classmethod
    def fit(cls):
        logging.info('Starting optuna validation ...')
        study = optuna.create_study(directions=('maximize',))
        study.optimize(cls.objective, n_trials=100)
        cls.fit_best(study.best_params)

    @classmethod
    def get_recommendations(cls):
        logging.info('Get recommendations ')
        global redis_connection
        try:
            for user_id, ids in cls.grouped_df.select('user_id', pl.struct('train_item_ids', 'test_item_ids')).rows():
                item_ids = ids['train_item_ids'] + ids['test_item_ids']
                y_rec = [cls.user_mapping_inverse.get(pred[0]) for pred in cls.model.predict_output_word(item_ids, TOP_K)]
                redis_connection.json().set(user_id, '.', y_rec)
        except BaseException as e:
            logging.critical(e)

    @classmethod
    def run_pipeline(cls):    
        cls.create_dataset()
        cls.fit()
        cls.get_recommendations()