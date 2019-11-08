web: bin/start-nginx gunicorn -c config/gunicorn.conf config.wsgi:application
worker: celery worker --app=config.celery_app --loglevel=info
beat: celery beat --app=config.celery_app --loglevel=info
