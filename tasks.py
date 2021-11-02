# Third Party
from invoke import task

COMPOSE_PREFIX = "docker-compose -f local.yml"
COMPOSE_BUILD = f"{COMPOSE_PREFIX} build {{opt}} {{service}}"
COMPOSE_RUN_OPT = f"{COMPOSE_PREFIX} run {{opt}} --rm {{service}} {{cmd}}"
COMPOSE_RUN_OPT_USER = COMPOSE_RUN_OPT.format(
    opt="-u $(id -u):$(id -g) {opt}", service="{service}", cmd="{cmd}"
)
COMPOSE_RUN = COMPOSE_RUN_OPT.format(opt="", service="{service}", cmd="{cmd}")
DJANGO_RUN = COMPOSE_RUN.format(service="documentcloud_django", cmd="{cmd}")
DJANGO_RUN_USER = COMPOSE_RUN_OPT_USER.format(
    opt="", service="documentcloud_django", cmd="{cmd}"
)
WEB_OPEN = "xdg-open {} > /dev/null 2>&1"


@task
def test(
    c, path="documentcloud", create_db=False, ipdb=False, slow=False, warnings=False
):
    """Run the test suite"""
    create_switch = "--create-db" if create_db else ""
    ipdb_switch = "--pdb --pdbcls=IPython.terminal.debugger:Pdb" if ipdb else ""
    slow_switch = "" if slow else '-m "not slow"'
    warnings = "-e PYTHONWARNINGS=always" if warnings else ""

    c.run(
        COMPOSE_RUN_OPT_USER.format(
            opt=f"-e DJANGO_SETTINGS_MODULE=config.settings.test {warnings}",
            service="documentcloud_django",
            cmd=f"pytest {create_switch} {ipdb_switch} {slow_switch} {path}",
        ),
        pty=True,
    )


@task
def testwatch(c, path="documentcloud"):
    """Run the test suite and watch for changes"""

    c.run(
        COMPOSE_RUN_OPT_USER.format(
            opt="-e DJANGO_SETTINGS_MODULE=config.settings.test",
            service="documentcloud_django",
            cmd=f"ptw {path}",
        ),
        pty=True,
    )


@task
def launchall(c):
    """Run all the necessary programs in Squarelet and DocumentCloud in Linux program terminator"""
    c.run('terminator -g terminator2.config -l "DocumentCloud"')


@task
def openreport(c):
    """Open the generated test reports file in a web browser (run `inv test` first)"""
    c.run(
        WEB_OPEN.format(
            "file://$PWD/documentcloud/document/processing/tests/reports.html"
        )
    )


@task
def openapp(c):
    """Open the local Django app in a web browser"""
    c.run(WEB_OPEN.format("http://dev.documentcloud.org"))


@task
def coverage(c):
    """Run the test suite with coverage report"""
    c.run(
        COMPOSE_RUN_OPT_USER.format(
            opt="-e DJANGO_SETTINGS_MODULE=config.settings.test",
            service="documentcloud_django",
            cmd="coverage erase",
        )
    )
    c.run(
        COMPOSE_RUN_OPT_USER.format(
            opt="-e DJANGO_SETTINGS_MODULE=config.settings.test",
            service="documentcloud_django",
            cmd='coverage run --source documentcloud -m py.test -m "not slow"',
        )
    )
    c.run(
        COMPOSE_RUN_OPT_USER.format(
            opt="-e DJANGO_SETTINGS_MODULE=config.settings.test",
            service="documentcloud_django",
            cmd="coverage html",
        )
    )


@task
def pylint(c):
    """Run the linter"""
    c.run(DJANGO_RUN.format(cmd="pylint documentcloud"))


@task
def format(c):
    """Format your code"""
    c.run(
        DJANGO_RUN_USER.format(
            cmd="black documentcloud --exclude migrations && "
            "black config/urls.py && "
            "black config/settings && "
            "isort -rc documentcloud && "
            "isort config/urls.py && "
            "isort -rc config/settings"
        )
    )


@task
def runserver(c):
    """Run the development server"""
    c.run(
        COMPOSE_RUN_OPT.format(
            opt="--service-ports --use-aliases", service="documentcloud_django", cmd=""
        )
    )


@task
def shell(c, opts=""):
    """Run an interactive python shell"""
    c.run(DJANGO_RUN.format(cmd=f"python manage.py shell_plus {opts}"), pty=True)


@task
def sh(c):
    """Run an interactive shell"""
    c.run(
        COMPOSE_RUN_OPT.format(
            opt="--use-aliases", service="documentcloud_django", cmd="sh"
        ),
        pty=True,
    )


@task
def dbshell(c, opts=""):
    """Run an interactive db shell"""
    c.run(DJANGO_RUN.format(cmd=f"python manage.py dbshell {opts}"), pty=True)


@task
def celeryworker(c):
    """Run a celery worker"""
    c.run(
        COMPOSE_RUN_OPT.format(
            opt="--use-aliases", service="documentcloud_celeryworker", cmd=""
        )
    )


@task
def celerybeat(c):
    """Run the celery scheduler"""
    c.run(
        COMPOSE_RUN_OPT.format(
            opt="--use-aliases", service="documentcloud_celerybeat", cmd=""
        )
    )


@task
def manage(c, cmd):
    """Run a Django management command"""
    c.run(DJANGO_RUN_USER.format(cmd=f"python manage.py {cmd}"), pty=True)


@task
def run(c, cmd):
    """Run a command directly on the docker instance"""
    c.run(DJANGO_RUN_USER.format(cmd=cmd))


@task(name="pip-compile")
def pip_compile(c, upgrade=False, package=None):
    """Run pip compile"""
    if package:
        upgrade_flag = f"--upgrade-package {package}"
    elif upgrade:
        upgrade_flag = "--upgrade"
    else:
        upgrade_flag = ""
    c.run(
        COMPOSE_RUN_OPT_USER.format(
            opt="-e PIP_TOOLS_CACHE_DIR=/tmp/pip-tools-cache",
            service="documentcloud_django",
            cmd=f"sh -c 'pip-compile {upgrade_flag} requirements/base.in && "
            f"pip-compile {upgrade_flag} requirements/local.in && "
            f"pip-compile {upgrade_flag} requirements/production.in'",
        )
    )


@task
def build(c, opt="", service=""):
    """Build the docker images"""
    c.run(COMPOSE_BUILD.format(opt=opt, service=service))


@task
def heroku(c, staging=False):
    """Run commands on heroku"""
    if staging:
        app = "documentcloud-staging"
    else:
        app = "documentcloud-prod"
    c.run(f"heroku run --app {app} python manage.py shell_plus", pty=True)


@task
def download_tesseract_data(c):
    """Download Tesseract data files. Needed to be able to do OCR locally."""
    c.run("cd config/aws/lambda; ./build.sh")


@task
def deploy_lambdas(c, staging=False):
    """Deploy lambda functions on AWS"""
    if staging:
        stack = "info-and-image-staging"
        env = "staging"
    else:
        stack = "processing-production"
        env = "prod"
    c.run(f"cd config/aws/lambda; ./deploy.sh {stack} {env}")


@task
def update_solr_config(c):
    """Update the solr config to the local docker images
    Be sure to bring the container down and up again after updating
    """
    template = (
        "docker cp config/solr/{file} documentcloud_documentcloud_{container}:"
        "/var/solr/data/{collection}/"
    )

    for file_ in ["managed-schema", "solrconfig.xml"]:
        for container, collection in [
            ("solr_1", "documentcloud"),
            ("test_solr_1", "documentcloud_test"),
        ]:
            c.run(
                template.format(file=file_, container=container, collection=collection)
            )
