FROM python:3.11.9-bullseye

WORKDIR /app
COPY main.py requirements.txt /app/

EXPOSE 5001

RUN pip install -r requirements.txt

CMD ["uvicorn", "main:app", "--port", "5001", "--host",  "0.0.0.0"]