FROM python:3.11.9-bullseye

WORKDIR /app
COPY app.py /app/app.py
COPY static /app/static
COPY templates /app/templates
COPY requirements.txt /app/requirements.txt

EXPOSE 8000

RUN pip install -r requirements.txt

CMD ["uvicorn", "app:app", "--port", "8000", "--host", "0.0.0.0"]