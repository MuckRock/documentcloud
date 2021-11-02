"""
Base settings to build other settings files upon.
"""

# Standard Library
import os
from tempfile import NamedTemporaryFile

# Third Party
import environ

ROOT_DIR = (
    environ.Path(__file__) - 3
)  # (documentcloud/config/settings/base.py - 3 = documentcloud/)
APPS_DIR = ROOT_DIR.path("documentcloud")

env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(ROOT_DIR.path(".env")))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "UTC"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n
USE_L10N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [ROOT_DIR.path("locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.contrib.flatpages",
]
THIRD_PARTY_APPS = [
    "django_celery_beat",
    "django_filters",
    "drf_yasg",
    "rest_framework",
    "reversion",
    "rules.apps.AutodiscoverRulesConfig",
    "social_django",
    "corsheaders",
    "squarelet_auth.organizations.apps.OrganizationsConfig",
    "squarelet_auth.apps.SquareletAuthConfig",
    "django_premailer",
    "robots",
]

LOCAL_APPS = [
    "documentcloud.core.apps.CoreConfig",
    "documentcloud.documents.apps.DocumentsConfig",
    "documentcloud.oembed.apps.OembedConfig",
    "documentcloud.organizations.apps.OrganizationsConfig",
    "documentcloud.projects.apps.ProjectsConfig",
    "documentcloud.statistics.apps.StatisticsConfig",
    "documentcloud.sidekick.apps.SidekickConfig",
    "documentcloud.users.apps.UsersConfig",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "rules.permissions.ObjectPermissionBackend",
    "squarelet_auth.backends.SquareletBackend",
    "django.contrib.auth.backends.ModelBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
SQUARELET_ORGANIZATION_MODEL = "organizations.Organization"

# SQUARELET AUTHENTICATION
# ------------------------------------------------------------------------------
SOCIAL_AUTH_POSTGRES_JSONFIELD = True
SOCIAL_AUTH_SQUARELET_KEY = env("SQUARELET_KEY")
SOCIAL_AUTH_SQUARELET_SECRET = SQUARELET_SECRET = env("SQUARELET_SECRET")
SOCIAL_AUTH_SQUARELET_SCOPE = ["uuid", "organizations", "preferences"]
SOCIAL_AUTH_SQUARELET_AUTH_EXTRA_ARGUMENTS = {"intent": "documentcloud"}
SOCIAL_AUTH_TRAILING_SLASH = False

SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "social_core.pipeline.social_auth.social_user",
    "social_core.pipeline.user.get_username",
    "squarelet_auth.pipeline.associate_by_uuid",
    "squarelet_auth.pipeline.save_info",
    "squarelet_auth.pipeline.save_session_data",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
)

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "dogslow.WatchdogMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "reversion.middleware.RevisionMiddleware",
    "documentcloud.core.middleware.ProfilerMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(ROOT_DIR("staticfiles"))
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR.path("static"))]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR("media"))
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# TEMPLATESgmo
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#template-dirs
        "DIRS": [str(APPS_DIR.path("templates"))],
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-loaders
            # https://docs.djangoproject.com/en/dev/ref/templates/api/#loader-types
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR.path("fixtures")),)

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "redis_lock.django_cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # Mimicing memcache behavior.
            # http://niwinz.github.io/django-redis/latest/#_memcached_exceptions_behavior
            "IGNORE_EXCEPTIONS": True,
        },
    }
}
DEFAULT_CACHE_TIMEOUT = 15 * 60

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = False
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-browser-xss-filter
SECURE_BROWSER_XSS_FILTER = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
# https://docs.djangoproject.com/en/2.2/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5
DEFAULT_FROM_EMAIL = env(
    "DJANGO_DEFAULT_FROM_EMAIL", default="MuckRock <info@muckrock.com>"
)

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = [("Mitchell Kotler", "mitch@muckrock.com")]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s "
            "%(process)d %(thread)d %(message)s"
        }
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        }
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}
if 1 or DEBUG:
    LOGGING["loggers"] = {
        "rules": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        # "django.db.backends": {
        #     "level": "DEBUG",
        #     "handlers": ["console"],
        #     "propogate": False,
        # },
    }

# Celery
# ------------------------------------------------------------------------------
if USE_TZ:
    # http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = env("REDIS_URL")
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ["json"]
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = "json"
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = "json"
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#task-time-limit
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=5 * 60)
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#task-soft-time-limit
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=60)
CELERY_SLOW_TASK_TIME_LIMIT = env.int("CELERY_SLOW_TASK_TIME_LIMIT", default=6 * 60)
CELERY_SLOW_TASK_SOFT_TIME_LIMIT = env.int(
    "CELERY_SLOW_TASK_SOFT_TIME_LIMIT", default=5 * 60
)
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#beat-scheduler
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_IMPORTS = []
CELERY_REDIS_MAX_CONNECTIONS = env.int("CELERY_REDIS_MAX_CONNECTIONS", default=40)
CELERY_BROKER_POOL_LIMIT = env.int("CELERY_BROKER_POOL_LIMIT", default=0)
CELERY_TASK_IGNORE_RESULT = True
CELERY_WORKER_CONCURRENCY = env.int("CELERY_WORKER_CONCURRENCY", default=8)
CELERY_WORKER_MAX_TASKS_PER_CHILD = env.int(
    "CELERY_WORKER_MAX_TASKS_PER_CHILD", default=100
)
CELERY_WORKER_MAX_MEMORY_PER_CHILD = env.int(
    "CELERY_WORKER_MAX_MEMORY_PER_CHILD", default=20 * 1024
)

# django-compressor
# ------------------------------------------------------------------------------
# https://django-compressor.readthedocs.io/en/latest/quickstart/#installation
INSTALLED_APPS += ["compressor"]
STATICFILES_FINDERS += ["compressor.finders.CompressorFinder"]

# Rest Framework
# ------------------------------------------------------------------------------
REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        "documentcloud.core.permissions.DjangoObjectPermissionsOrAnonReadOnly"
    ],
    "DEFAULT_PAGINATION_CLASS": "documentcloud.core.pagination.PageNumberPagination",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "HTML_SELECT_CUTOFF": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "documentcloud.core.authentication.ProcessingTokenAuthentication",
    ),
}
AUTH_PAGE_LIMIT = env.int("AUTH_PAGE_LIMIT", default=1000)
ANON_PAGE_LIMIT = env.int("ANON_PAGE_LIMIT", default=100)

# django-extensions
# ------------------------------------------------------------------------------
# https://django-extensions.readthedocs.io/en/latest/installation_instructions.html#configuration
INSTALLED_APPS += ["django_extensions"]  # noqa F405

# Your stuff...
# ------------------------------------------------------------------------------

# first party urls
# ------------------------------------------------------------------------------
SQUARELET_URL = env("SQUARELET_URL", default="http://dev.squarelet.com")
MUCKROCK_URL = env("MUCKROCK_URL", default="http://dev.muckrock.com")
FOIAMACHINE_URL = env("FOIAMACHINE_URL", default="http://dev.foiamachine.org")
DOCCLOUD_URL = env("DOCCLOUD_URL", default="http://www.dev.documentcloud.org")
DOCCLOUD_API_URL = env("DOCCLOUD_API_URL", default="http://api.dev.documentcloud.org")
DOCCLOUD_EMBED_URL = env(
    "DOCCLOUD_EMBED_URL", default="http://www.dev.documentcloud.org"
)
BASE_URL = DOCCLOUD_URL

PUBLIC_ASSET_URL = env(
    "PUBLIC_ASSET_URL", default="http://minio.documentcloud.org:9000/documents/"
)
PRIVATE_ASSET_URL = env("PRIVATE_ASSET_URL", default=f"{DOCCLOUD_API_URL}/files/")

SOCIAL_AUTH_LOGIN_ERROR_URL = f"{DOCCLOUD_URL}?error=login"

# SESSION/COOKIES
# ----
# https://docs.djangoproject.com/en/2.2/ref/settings/#session-cookie-domain
SESSION_COOKIE_DOMAIN = env("DJANGO_COOKIE_DOMAIN", default=".dev.documentcloud.org")
CSRF_COOKIE_DOMAIN = env("DJANGO_COOKIE_DOMAIN", default=".dev.documentcloud.org")

# CORS middleware
# https://pypi.org/project/django-cors-headers/
# Configure nginx.conf.erb if you change this
CORS_ORIGIN_WHITELIST = [DOCCLOUD_URL, DOCCLOUD_EMBED_URL]
# This enables cookies
CORS_ALLOW_CREDENTIALS = True

# this allows communication from muckrock to squarelet to bypass rate limiting
BYPASS_RATE_LIMIT_SECRET = env("BYPASS_RATE_LIMIT_SECRET", default="")

# bucket to store files in
DOCUMENT_BUCKET = env("DOCUMENT_BUCKET", default="documents")

# Processing
DOC_PROCESSING_URL = env("DOC_PROCESSING_URL", default="")
PROGRESS_URL = env("PROGRESS_URL", default="")
IMPORT_URL = env("IMPORT_URL", default="")
PROGRESS_TIMEOUT = env.int("PROGRESS_TIMEOUT", default=1)
SIDEKICK_PROCESSING_URL = env("SIDEKICK_PROCESSING_URL", default="")

# Auth
LOGIN_URL = "/accounts/login/squarelet"
LOGIN_REDIRECT_URL = DOCCLOUD_URL + "/app"
LOGOUT_REDIRECT_URL = DOCCLOUD_URL
# This lets us send the session cookie to the API
SESSION_COOKIE_SAMESITE = "None"

SIMPLE_JWT = {
    "ALGORITHM": "RS256",
    "VERIFYING_KEY": env.str("JWT_VERIFYING_KEY", multiline=True),
    "AUDIENCE": ["documentcloud"],
    "USER_ID_FIELD": "uuid",
}

SQUARELET_WHITELIST_VERIFIED_JOURNALISTS = env.bool(
    "SQUARELET_WHITELIST_VERIFIED_JOURNALISTS", default=True
)

PROCESSING_TOKEN = env("PROCESSING_TOKEN")

ENVIRONMENT = env("ENVIRONMENT")

REST_BULK_LIMIT = env.int("REST_BULK_LIMIT", default=25)
UPDATE_ACCESS_CHUNK_SIZE = env.int("UPDATE_ACCESS_CHUNK_SIZE", default=500)

HTTPSUB_RETRY_LIMIT = env.int("HTTPSUB_RETRY_LIMIT", default=10)

# Solr
# ------------------------------------------------------------------------------
SOLR_HOST_URL = env("SOLR_HOST_URL", default="http://documentcloud_solr:8983/")
SOLR_BASE_URL = SOLR_HOST_URL + "solr/"
SOLR_COLLECTION_NAME = env("SOLR_COLLECTION_NAME", default="documentcloud")
SOLR_URL = SOLR_BASE_URL + SOLR_COLLECTION_NAME

SOLR_USERNAME = env("SOLR_USERNAME", default="")
SOLR_PASSWORD = env("SOLR_PASSWORD", default="")
if SOLR_USERNAME and SOLR_PASSWORD:
    SOLR_AUTH = (SOLR_USERNAME, SOLR_PASSWORD)
else:
    SOLR_AUTH = None
SOLR_SEARCH_HANDLER = env("SOLR_SEARCH_HANDLER", default="/mainsearch")
# The certificate needs to be in a file if present
SOLR_VERIFY = env.str("SOLR_VERIFY", multiline=True, default="")
if SOLR_VERIFY == "False":
    SOLR_VERIFY = False
elif SOLR_VERIFY:
    # if present, put the contents into a named temp file
    # and set the var to the name of the file
    cert = NamedTemporaryFile(delete=False)
    cert.write(SOLR_VERIFY.encode("ascii"))
    cert.close()
    SOLR_VERIFY = cert.name
else:
    # otherwise set to true, which uses default certificates to verify
    SOLR_VERIFY = True

SOLR_INDEX_LIMIT = env.int("SOLR_INDEX_LIMIT", default=100)
SOLR_INDEX_BATCH_LIMIT = env.int("SOLR_INDEX_BATCH_LIMIT", default=50)
SOLR_INDEX_CATCHUP_SECONDS = env.int("SOLR_INDEX_CATCHUP_SECONDS", default=300)
SOLR_INDEX_MAX_SIZE = env.int("SOLR_INDEX_MAX_SIZE", default=18 * 1024 * 1024)
SOLR_RETRY_BACKOFF = env.int("SOLR_RETRY_BACKOFF", default=300)
SOLR_HL_SNIPPETS = env.int("SOLR_HL_SNIPPETS", default=25)
SOLR_USE_HL = env.bool("SOLR_USE_HL", default=True)
SOLR_HL_REQUIRE_FIELD_MATCH = env("SOLR_HL_REQUIRE_FIELD_MATCH", default="true")
SOLR_HL_MULTI_TERM = env("SOLR_HL_MULTI_TERM", default="true")
SOLR_TIMEOUT = env.int("SOLR_TIMEOUT", default=20)
SOLR_ANON_MAX_ROWS = env.int("SOLR_ANON_MAX_ROWS", default=25)

# OEmbed
# ------------------------------------------------------------------------------
OEMBED_PROVIDER_NAME = env("OEMBED_PROVIDER_NAME", default="DocumentCloud")
OEMBED_PROVIDER_URL = env("OEMBED_PROVIDER_URL", default=DOCCLOUD_URL)
OEMBED_CACHE_AGE = env.int("OEMBED_CACHE_AGE", default=300)

CACHE_CONTROL_MAX_AGE = env.int("CACHE_CONTROL_MAX_AGE", default=300)

# Squarelet
# ------------------------------------------------------------------------------
SQUARELET_DISABLE_CREATE = env.bool("SQUARELET_DISABLE_CREATE", default=True)
SQUARELET_RESOURCE_FIELDS = {
    "minimum_users": 1,
    "base_pages": 0,
    "pages_per_user": 0,
    "feature_level": 0,
}

# Dogslow
# ------------------------------------------------------------------------------
DOGSLOW = True
DOGSLOW_LOG_TO_FILE = False
DOGSLOW_TIMER = 25
DOGSLOW_LOGGER = "dogslow"
DOGSLOW_LOG_LEVEL = "ERROR"
DOGSLOW_LOG_TO_SENTRY = True
DOGSLOW_STACK_VARS = True

DOGSLOW_EMAIL_TO = env("DOGSLOW_EMAIL_TO", default="mitch@muckrock.com")
DOGSLOW_EMAIL_FROM = env("DOGSLOW_EMAIL_FROM", default="info@muckrock.com")

# Google Language
# ------------------------------------------------------------------------------
# The credentials need to be in a file
GOOGLE_APPLICATION_CREDENTIALS = env.str("GOOGLE_APPLICATION_CREDENTIALS", default="")
# put the contents into a named temp file
# and set the var to the name of the file
gac = NamedTemporaryFile(delete=False)
gac.write(GOOGLE_APPLICATION_CREDENTIALS.encode("ascii"))
gac.close()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gac.name
GOOGLE_API_KEY = env.str("GOOGLE_API_KEY", default="")

# CDN Caches
# ------------------------------------------------------------------------------
CLOUDFRONT_DISTRIBUTION_ID = env("CLOUDFRONT_DISTRIBUTION_ID", default="")

CLOUDFLARE_API_EMAIL = env("CLOUDFLARE_API_EMAIL", default="")
CLOUDFLARE_API_KEY = env("CLOUDFLARE_API_KEY", default="")
CLOUDFLARE_API_ZONE = env("CLOUDFLARE_API_ZONE", default="")
