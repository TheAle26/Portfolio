FROM python:3.10-slim

# Set environment variables to prevent Python from writing .pyc files and to ensure that output is sent directly to the terminal
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

COPY . /app/

CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000"]

EXPOSE 8000