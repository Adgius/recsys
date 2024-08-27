import os
from typing import Optional
import uuid

import polars as pl

import requests
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import FastAPI, Response, Request, Cookie
from fastapi.templating import Jinja2Templates

from s3_connect import download_static_images_arch


IMAGE_PATH = './static/images'
if not os.path.exists(IMAGE_PATH):
    download_static_images_arch('static')

templates = Jinja2Templates(directory="templates")

app = FastAPI(title='Recommendation')
    
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.getcwd(), "static")),
    name="static",
)
# app.secret_key = os.urandom(24)

recommendation_service_url = os.environ.get('RECSYS_SERVICE_URL')
print(recommendation_service_url)
interactions_url = os.environ.get('SERVICE_API_URL')

links_data = (
    pl.read_csv('static/links.csv')
    .with_columns(pl.col('movieId').cast(pl.Utf8))
)
movies_data = (
    pl.read_csv('static/movies.csv')
    .with_columns(pl.col('movieId').cast(pl.Utf8))
)


def imdb_url(imdb_id):
    imdb_id = str(imdb_id)
    return 'https://www.imdb.com/title/tt' + '0' * (7 - len(imdb_id)) + imdb_id


movie_id_title = {
    movie_id: title
    for movie_id, title in movies_data.select('movieId', 'title').rows()
}
movie_id_imdb = {
    movie_id: imdb_url(imdb_id)
    for movie_id, imdb_id in links_data.select('movieId', 'imdbId').rows()
}
# отображаем только топ-12 рекомендаций
TOP_K = 12


@app.get('/healthcheck')
def health_check():
    return {"status": "healthy"}


@app.get('/get_all_items')
def get_all_items():
    return set([str(i) for i in movie_id_imdb.keys()])

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    print(recommendation_service_url)
    # если передан идентификатор пользователя, используем его
    user_id = get_user_id_from_cookies(request)

    # получить рекомендации через api модели
    recommendations_url = f"{recommendation_service_url}/recs/{user_id}"
    response = requests.get(recommendations_url)

    if response.status_code == 200:
        recommended_item_ids = response.json()['item_ids']
    else:
        # тут можно сделать fallback на стороне фронтенда
        recommended_item_ids = []
    items_data = fetch_items_data_for_item_ids(recommended_item_ids)
    response = templates.TemplateResponse(
        request=request,
        name='index.html',
        context=dict(
            request=request,
            items_data=items_data,
            interactions_url=interactions_url
        )
    )

    # если пользователь первый раз, сгенерируем user_id
    if user_id is None:
        response.set_cookie(key="user_id", value=uuid.uuid4())
    return response

def get_user_id_from_cookies(request: Request) -> Optional[str]:
    return request.cookies.get("user_id")

def fetch_items_data_for_item_ids(item_ids):
    return [
               {
                   "item_id": item_id,
                   "imdb_url": movie_id_imdb[item_id],
                   "image_filename": f'{item_id}.jpg',
                   "title": movie_id_title[item_id]
               }
               for item_id in item_ids
               if item_id in movie_id_title
           ][:TOP_K]