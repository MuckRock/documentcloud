#!/usr/bin/env python
# This will create your initial .env files
# These are not to be checked in to git, as you may populate them
# with confidential information

# Standard Library
import os
import random
import string


def random_string(n):
    return "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(n)
    )


CONFIG = [
    {
        "name": ".django",
        "sections": [
            {
                "name": "General",
                "envvars": [
                    ("USE_DOCKER", "yes"),
                    ("DJANGO_SECRET_KEY", lambda: random_string(20)),
                    ("IPYTHONDIR", "/app/.ipython"),
                    ("DOCUMENTCLOUD_URL", "http://dev.documentcloud.org"),
                ],
            },
            {
                "name": "Redis",
                "envvars": [
                    ("REDIS_URL", "redis://documentcloud_redis:6379/0"),
                    (
                        "REDIS_PROCESSING_URL",
                        "redis://documentcloud_processing_redis:6379/0",
                    ),
                    ("REDIS_PROCESSING_PASSWORD", ""),
                ],
            },
            {
                "name": "Squarelet",
                "envvars": [("SQUARELET_KEY", ""), ("SQUARELET_SECRET", "")],
            },
            {"name": "JWT", "envvars": [("JWT_VERIFYING_KEY", "")]},
            {
                "name": "Processing Environment",
                "envvars": [
                    ("ENVIRONMENT", "local-minio"),
                    ("SERVERLESS", "False"),
                    ("DOC_PROCESSING_URL", "http://process.dev.documentcloud.org"),
                    ("API_CALLBACK", "http://api.dev.documentcloud.org/api/"),
                    ("PROCESSING_TOKEN", lambda: random_string(64)),
                    ("DOCUMENT_BUCKET", "documents"),
                    ("SERVERLESS", "False"),
                ],
            },
            {
                "name": "MinIO",
                "envvars": [
                    ("MINIO_ACCESS_KEY", lambda: random_string(64)),
                    ("MINIO_SECRET_KEY", lambda: random_string(64)),
                    ("MINIO_URL", "http://minio.documentcloud.org:9000"),
                ],
            },
        ],
    },
    {
        "name": ".postgres",
        "sections": [
            {
                "name": "PostgreSQL",
                "envvars": [
                    ("POSTGRES_HOST", "documentcloud_postgres"),
                    ("POSTGRES_PORT", "5432"),
                    ("POSTGRES_DB", "documentcloud"),
                    ("POSTGRES_USER", lambda: random_string(30)),
                    ("POSTGRES_PASSWORD", lambda: random_string(60)),
                ],
            }
        ],
    },
]


def main():
    os.makedirs(".envs/.local/", 0o775)
    for file_config in CONFIG:
        with open(".envs/.local/{}".format(file_config["name"]), "w") as file_:
            for section in file_config["sections"]:
                for key in ["name", "url", "description"]:
                    if key in section:
                        file_.write("# {}\n".format(section[key]))
                file_.write("# {}\n".format("-" * 78))
                for var, value in section["envvars"]:
                    file_.write(
                        "{}={}\n".format(var, value() if callable(value) else value)
                    )
                file_.write("\n")


if __name__ == "__main__":
    main()
