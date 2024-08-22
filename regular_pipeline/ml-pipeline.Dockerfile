FROM python:3.11.9-bullseye

WORKDIR /app
COPY main.py ml_model.py requirements.txt /app/

EXPOSE 5000

RUN pip install -r requirements.txt

CMD ["python", "main.py"]