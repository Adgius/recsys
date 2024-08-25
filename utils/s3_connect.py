import boto3
import os
import requests 
import zipfile

from io import BytesIO


def download_static_images(path):
    s3 = boto3.client(service_name='s3',
                    region_name="ru-central1",
                    endpoint_url="https://storage.yandexcloud.net",
                    aws_access_key_id=os.environ.get('S3_PUB'),
                    aws_secret_access_key=os.environ.get('S3_SECRET'))

    os.makedirs(path)

    for key in s3.list_objects(Bucket='web-images')['Contents']:
        s3.download_file(Bucket='web-images',
                    Key=key['Key'],
                    Filename=os.path.join(path, key['Key']))

def download_static_images_arch(path):
    arch = requests.get('https://storage.yandexcloud.net/web-imgs-arch/images.zip')
    with zipfile.ZipFile(BytesIO(arch.content)) as zip_file:
        zip_file.extractall(path)
