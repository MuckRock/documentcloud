FROM python:3.12-slim
ENV PYTHONUNBUFFERED 1

RUN apt-get -qq -y update && apt-get -qq -y install \
  # psycopg2 dependencies
  gcc python3-dev libpq-dev \
  # Pillow dependencies
  libjpeg62-turbo zlib1g-dev libfreetype6-dev liblcms2-dev libopenjp2-7-dev libtiff6 tk-dev tcl-dev \
  # CFFI dependencies
  libffi-dev python3-cffi

RUN groupadd -r django \
    && useradd -r -g django django

# Requirements are installed here to ensure they will be cached.
COPY ./requirements /requirements
RUN pip install --no-cache-dir -r /requirements/production.txt \
    && rm -rf /requirements

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint
RUN chown django /entrypoint

COPY ./compose/production/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start
RUN chown django /start
COPY ./compose/production/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r$//g' /start-celeryworker
RUN chmod +x /start-celeryworker
RUN chown django /start-celeryworker

COPY ./compose/production/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r$//g' /start-celerybeat
RUN chmod +x /start-celerybeat
RUN chown django /start-celerybeat

COPY ./compose/production/django/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /start-flower
RUN chmod +x /start-flower
COPY . /app

RUN chown -R django /app

USER django

WORKDIR /app

ENTRYPOINT ["/entrypoint"]
