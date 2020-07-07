web: bin/start-nginx gunicorn -c config/gunicorn.conf config.wsgi:application
worker: REMAP_SIGTERM=SIGQUIT celery worker --app=config.celery_app --loglevel=info
beat: REMAP_SIGTERM=SIGQUIT celery beat --app=config.celery_app --loglevel=info
