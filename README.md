# DocumentCloud

Analyze, Annotate, Publish. Turn documents into data.

## Install

### Software required

1. [docker][docker-install]
2. [docker-compose][docker-compose-install]
3. [python][python-install]
4. [invoke][invoke-install]

### Installation Steps

0. Install Git Large File support [using these instructions](https://docs.github.com/en/repositories/working-with-files/managing-large-files/installing-git-large-file-storage).
1. Check out the git repository - `git clone git@github.com:MuckRock/documentcloud.git`
2. Enter the directory - `cd documentcloud`
3. Run the dotenv initialization script - `python initialize_dotenvs.py`
   This will create files with the environment variables needed to run the development environment.
4. Start the docker images - `export COMPOSE_FILE=local.yml; docker-compose up`
    -   This will build and start all of the docker images using docker-compose. It will bind to port 80 on localhost, so you must not have anything else running on port 80. The `local.yml` configuration file has the docker-compose details.
5. Set `api.dev.documentcloud.org` and `minio.documentcloud.org` to point to localhost - `sudo echo "127.0.0.1 api.dev.documentcloud.org minio.documentcloud.org" >> /etc/hosts`
6. Enter `api.dev.documentcloud.org/` into your browser - you should see the Django API root page.
7. Install and run [Squarelet](https://github.com/muckrock/squarelet) and the [DocumentCloud frontend](https://github.com/muckrock/documentcloud-frontend) following the instructions in their repos to view the full-stack application. 
    - `inv createsuperuser` in Squarelet (not DocumentCloud).
    - Login using `inv shell` in Squarelet
    - Set your user as `is_staff`:
   ```
   tempUser = User.objects.all()[0]
   tempUser.is_staff = True
   tempUser.save()
   ```
   - `make install` and `make dev` on the [DocumentCloud frontend](https://github.com/muckrock/documentcloud-frontend) to start the frontend (used at end).
8. In Squarelet Django admin page, follow the instructions as for the ["Squarelet Integration" on MuckRock](https://github.com/muckrock/muckrock/#squarelet-integration), except:
   - when creating the OpenID as set out in those instructions, also add `Redirect URIs`: `http://api.dev.documentcloud.org/accounts/complete/squarelet` and `http://minio.documentcloud.org/accounts/complete/squarelet`. 
   - Set Post-logout Redirect UI: `http://dev.documentcloud.org`
   - Scopes (one per line): 
      ```
      read_user
      read_organization
      read_auth_token
      ```
   - Add a Client profile and set the `Webhook URL`: `http://api.dev.documentcloud.org/squarelet/webhook/`. The `Source` can remain "MuckRock" in the dropdown.
   - You will have to look up **three** security-related configuration lines from your Squarelet instance to DocumentCloud (as if it was MuckRock). 
   - Write their values into the `./.envs/.local/.django` file of the DocumentCloud repository, which should already be initialized from above.
   - `Client ID` goes into `SQUARELET_KEY`
   - `Client Secret` goes into `SQUARELET_SECRET`
   - Additionally, get the value for `JWT_VERIFYING_KEY` by opening the Squarelet Django shell using `inv shell` and copying the `settings.SIMPLE_JWT['VERIFYING_KEY']` (remove the leading `b'` and the trailing `'`, leave the `\n` portions as-is)
9. Set `SIDEKICK_PROCESSING_URL=mock://sidekick.dev.documentcloud.org`
10. Set `SQUARELET_WHITELIST_VERIFIED_JOURNALISTS=false` to allow you to login.
11. You may need to provide valid testing values for `STRIPE_PUB_KEYS`, `STRIPE_SECRET_KEYS` and set `STRIPE_WEBHOOK_SECRETS=None` from the MuckRock team (multiple values are comma separated only, no square braces) 
12. Stop and start the docker compose sessions for DocumentCloud (Ctrl-C, or `docker-compose down`) and Squarelet (`docker-compose down` in Squarelet folder. Then `docker-compose up` for DocumentCloud, and `inv up` in squarelet folder to begin using the new dotfiles.
14. Log in using the Squarelet staff superuser on the locally-running Documentcloud frontend at http://dev.documentcloud.org
15. If you can login successfully, go to [Django admin for DocumentCloud](http://dev.api.documentcloud.org/admin) and add a static page


[docker-install]: https://docs.docker.com/install/
[docker-compose-install]: https://docs.docker.com/compose/install/
[invoke-install]: http://www.pyinvoke.org/installing.html
[python-install]: https://www.python.org/downloads/
