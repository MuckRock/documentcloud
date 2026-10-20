FROM python:3.12-slim
ENV PYTHONUNBUFFERED 1
USER root

RUN apt-get -qq -y update && \
  apt-get -qq -y install \
  # Build dependencies
  build-essential \
  # Postgres dependencies
  libpq-dev postgresql-client python3-psycopg2 \
  # Tesseract dependencies
  libjpeg62-turbo libtiff6 \
  # LibreOffice dependencies
  libnss3-dev libcurl4-openssl-dev libxslt1-dev libpixman-1-0 libxcb-render0-dev \
  # Utilities
  curl git ca-certificates


# set up makecert root CA
RUN curl http://localhost/rootCA.pem > /usr/local/share/ca-certificates/rootCA.crt && update-ca-certificates

# Requirements are installed here to ensure they will be cached.
COPY ./requirements /requirements

RUN python -m pip install "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" && pip install -r /requirements/local.txt

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

WORKDIR /app

ENV LD_LIBRARY_PATH /app/documentcloud/documents/processing/ocr/tesseract

ENTRYPOINT ["/entrypoint"]
