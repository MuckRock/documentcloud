web: bin/start-nginx gunicorn -c config/gunicorn.conf config.wsgi:application
worker: celery worker --app=documentcloud2.taskapp --loglevel=info
beat: celery beat --app=documentcloud2.taskapp --loglevel=info
