#!/bin/sh

python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py poblar_db
python manage.py poblar_base 
python manage.py generate_daily_report 
python -m gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 2 mysiteFulbo.wsgi:application