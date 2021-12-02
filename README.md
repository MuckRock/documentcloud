# DocumentCloud

Analyze, Annotate, Publish. Turn documents into data.

## Install

### Software required

1. [docker][docker-install]
2. [docker-compose][docker-compose-install]
3. [python][python-install]
4. [invoke][invoke-install]

### Installation Steps

1. Check out the git repository - `git clone git@github.com:MuckRock/documentcloud.git`
2. Enter the directory - `cd documentcloud`
3. Run the dotenv initialization script - `python initialize_dotenvs.py`
   This will create files with the environment variables needed to run the development environment.
4. Start the docker images - `export COMPOSE_FILE=local.yml; docker-compose up`
   This will build and start all of the docker images using docker-compose. It will bind to port 80 on localhost, so you must not have anything else running on port 80. The `local.yml` configuration file has the docker-compose details.
5. Set `api.dev.documentcloud.org` and `minio.documentcloud.org` to point to localhost - `sudo echo "127.0.0.1 api.dev.documentcloud.org minio.documentcloud.org" >> /etc/hosts`
6. Enter `api.dev.documentcloud.org/` into your browser - you should see the Django API root page.
7. Install and run [Squarelet](https://github.com/muckrock/squarelet) and the [DocumentCloud frontend](https://github.com/muckrock/documentcloud-frontend) following the instructions in their repos to view the full-stack application. 
8. In Squarelet, when creating the OpenID as set out in those instructions, also add Redirect URIs: `http://api.dev.documentcloud.org/accounts/complete/squarelet` and `http://minio.documentcloud.org/accounts/complete/squarelet`. You will have to look up three security-related configuration lines from your Squarelet instance, and write their values into the `./.envs/.local/.django` file initialized above and also set several other variables as follows:
9. `SQUARELET_KEY`, `SQUARELET_SECRET`, `JWT_VERIFYING_KEY`
10. Set `SIDEKICK_PROCESSING_URL=mock://sidekick.dev.documentcloud.org`
11. Set `SQUARELET_WHITELIST_VERIFIED_JOURNALISTS=false` to allow you to login.

[docker-install]: https://docs.docker.com/install/
[docker-compose-install]: https://docs.docker.com/compose/install/
[invoke-install]: http://www.pyinvoke.org/installing.html
[python-install]: https://www.python.org/downloads/
