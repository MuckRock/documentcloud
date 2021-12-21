# DocumentCloud

Analyze, Annotate, Publish. Turn documents into data.

## Install

### Software required

1. [docker][docker-install]
2. [docker-compose][docker-compose-install]
3. [python][python-install]
4. [invoke][invoke-install]

### Installation Steps

1. Install Git Large File support [using these instructions](https://docs.github.com/en/repositories/working-with-files/managing-large-files/installing-git-large-file-storage).
2. Check out the git repository - `git clone git@github.com:MuckRock/documentcloud.git`
3. Enter the directory - `cd documentcloud`
4. Run the dotenv initialization script - `python initialize_dotenvs.py`
   This will create files with the environment variables needed to run the development environment.
5. You do not need to immediately start the docker-compose session for DocumentCloud until the Squarelet configuration below is complete.
6. Set `api.dev.documentcloud.org` and `minio.documentcloud.org` to point to localhost - `sudo echo "127.0.0.1 api.dev.documentcloud.org minio.documentcloud.org" >> /etc/hosts`
7. Enter `api.dev.documentcloud.org/` into your browser - you should see the Django API root page. Note that `api` is before `dev` in this URL.
8. Install and run [Squarelet](https://github.com/muckrock/squarelet) and the [DocumentCloud frontend](https://github.com/muckrock/documentcloud-frontend) following the instructions in their repos to view the full-stack application. 
    - `inv sh` (not shell) then `./manage.py createsuperuser` in Squarelet (not DocumentCloud).
    - Login using `inv shell` (not sh) in Squarelet
    - Set your user as `is_staff`: (remove indentation after copying, if needed)
   ```
   tempUser = User.objects.all()[0]
   tempUser.is_staff = True
   tempUser.save()
   ```
   - `make install` and `make dev` on the [DocumentCloud frontend](https://github.com/muckrock/documentcloud-frontend) to start the frontend (used at end).
9. Visit the Squarelet Django [admin page](http://dev.squarelet.local) with the `is_staff` user you created. Follow the instructions as for the ["Squarelet Integration" on MuckRock](https://github.com/muckrock/muckrock/#squarelet-integration), except:
   - When creating the OpenID as set out in those instructions, also add `Redirect URIs`: `http://api.dev.documentcloud.org/accounts/complete/squarelet` and `http://minio.documentcloud.org/accounts/complete/squarelet`. 
   - Set Post-logout Redirect UI: `http://dev.documentcloud.org`
   - Scopes (one per line): 
      ```
      read_user
      read_organization
      read_auth_token
      ```
   - Add a Client profile and set the `Webhook URL`: `http://api.dev.documentcloud.org/squarelet/webhook/`. The `Source` can remain "MuckRock" in the dropdown.
   - You will have to look up **three** authentication-related configuration lines from your Squarelet instance to insert into DocumentCloud `.django` file (as if it was MuckRock). 
   - Write their values into the `./.envs/.local/.django` file of the DocumentCloud repository, which should already be initialized from above.
   - `Client ID` goes into `SQUARELET_KEY`
   - `Client Secret` goes into `SQUARELET_SECRET`
   - Additionally, get the value for `JWT_VERIFYING_KEY` by opening the Squarelet Django shell using `inv shell` and copying the `settings.SIMPLE_JWT['VERIFYING_KEY']` (remove the leading `b'` and the trailing `'`, leave the `\n` portions as-is)
   - (If `JWT_VERIFYING_KEY` is blank, don't forget to `inv sh` on Squarelet and then run `./manage.py creatersakey` as the instructions linked above explained)
10. In Squarelet, you may need to provide valid testing values for `STRIPE_PUB_KEYS`, `STRIPE_SECRET_KEYS` and set `STRIPE_WEBHOOK_SECRETS=None` from the MuckRock team (multiple values are comma separated only, no square braces)
11. Run `export COMPOSE_FILE=local.yml;` in any of your command line sessions so that docker-compose finds the configuration.
12. Be sure to stop (if needed) both the docker compose sessions DocumentCloud (Ctrl-C, or `docker-compose down`) and Squarelet (`docker-compose down` in Squarelet folder). Then run the Squarelet session using `inv up` in the squarelet folder. **Finally, run `docker-compose up` in this DocumentCloud folder to begin using the new dotfiles.**
    -   This will build and start all of the DocumentCloud docker images using docker-compose. It will attach to the Squarelet network which must be already running. You can connect to Squarelet nginx on port 80 and it will serve the appropriate dependent http service, such as DocumentCloud, based on domain as a virtual host. The `local.yml` configuration file has the docker-compose details.
    - If you do `docker-compose down` on Squarelet when none of the other dependent docker-compose sessions (such as DocumentCloud) are running, `docker-compose down` will delete the Squarelet network. You will have to explicitly bring the whole squarelet docker-compose session back up to recreate it and nginx before being able to start a dependent docker-compose session (such as DocumentCloud).
    - Using `docker-compose up -d` rather than `docker-compose up` will make a daemon for DocumentCloud as Squarelet defaults to.
13. Log in using the Squarelet staff superuser on the locally-running Documentcloud frontend at http://dev.documentcloud.org
14. If you can login successfully, go to [Django admin for DocumentCloud](http://dev.api.documentcloud.org/admin) and add a static page


[docker-install]: https://docs.docker.com/install/
[docker-compose-install]: https://docs.docker.com/compose/install/
[invoke-install]: http://www.pyinvoke.org/installing.html
[python-install]: https://www.python.org/downloads/
