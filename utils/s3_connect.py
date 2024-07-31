import boto3
import os

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

