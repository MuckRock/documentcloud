# FROM python:3.6-alpine
FROM matthewfeickert/docker-python3-ubuntu:3.6.8

ENV PYTHONUNBUFFERED 1

USER root

RUN apt-get -qq -y update && \
  apt-get -qq -y upgrade && \
  apt-get -qq -y install \
  # Pip dependencies
  python3-pip \
  # Postgres dependencies
  libpq-dev postgresql-client python-psycopg2 \
  # Tesseract dependencies
  libjpeg-turbo8 libtiff5 \
  # LibreOffice dependencies
  libnss3-dev libcurl4-nss-dev libxslt1-dev libpixman-1-0 libxcb-render0-dev && \
  # Symlink bash and python
  ln -sf bash /bin/sh && rm -f /usr/bin/python && \
  ln -s /usr/bin/python3 /usr/bin/python && \
  curl https://bootstrap.pypa.io/pip/3.6/get-pip.py -o get-pip.py && \
  python3 get-pip.py --force-reinstall

# set up makecert root CA
RUN curl http://localhost/rootCA.pem > /usr/local/share/ca-certificates/rootCA.crt && update-ca-certificates

# Requirements are installed here to ensure they will be cached.
COPY ./requirements /requirements
# RUN pip install --upgrade pip && pip install -r /requirements/local.txt
RUN pip install -r /requirements/local.txt

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint && chmod +x /entrypoint

COPY ./compose/local/django/start /start
RUN sed -i 's/\r//' /start && chmod +x /start

COPY ./compose/local/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r//' /start-celeryworker && chmod +x /start-celeryworker

COPY ./compose/local/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r//' /start-celerybeat && chmod +x /start-celerybeat

COPY ./compose/local/django/celery/flower/start /start-flower
RUN sed -i 's/\r//' /start-flower && chmod +x /start-flower

# =-=-=-=-=-=
# Entry point
# =-=-=-=-=-=

# Temporary measure to get pip-compile to work
# RUN pip install 'pip<19.2'

WORKDIR /app

ENV LD_LIBRARY_PATH /app/documentcloud/documents/processing/ocr/tesseract

ENTRYPOINT ["/entrypoint"]
