release: ./postdeploy.sh
web: DB_STATEMENT_TIMEOUT=25000 bin/start-nginx gunicorn -c config/gunicorn.conf config.wsgi:application
worker: REMAP_SIGTERM=SIGQUIT celery --app=config.celery_app worker --loglevel=info
solr_worker: REMAP_SIGTERM=SIGQUIT celery --app=config.celery_app worker --loglevel=info -Q solr,celery
beat: REMAP_SIGTERM=SIGQUIT celery --app=config.celery_app beat --loglevel=info
