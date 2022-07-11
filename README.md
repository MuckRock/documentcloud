# DocumentCloud

Analyze, Annotate, Publish. Turn documents into data.

### Prerequisites
You must first have these set up and ready to go: 
- [Squarelet](https://github.com/muckrock/squarelet). DocumentCloud depends on Squarelet for user authentication. As the services need to communicate directly, the development environment for DocumentCloud depends on the development environment for Squarelet - the DocumentCloud docker containers will join Squarelet's docker network. Please install Squarelet and set up its development environment first.
- [DocumentCloud frontend](https://github.com/muckrock/documentcloud-frontend)

*Note the front end will not be functional until you complete the current install.

### Squarelet Integration
The Squarelet setup provides as an authentication system for the following projects. Therefore, there must be certain things set up for each of them within Squarelet before you can begin accessing them individually. 

 1. With the Squarelet containers running, in your terminal within the Squarelet folder, open up the bash shell with `inv sh`
 2. Within the bash shell, utilize this command to create your RSA key `./manage.py creatersakey`
 3. Then create a superuser utilizing the following command: `./manage.py createsuperuser`. 
 4. Exit the bash shell with the command `exit`
 5. Enter the Django shell with the command `inv shell`
 6. Grab the user you have just created with the following command
```python
tempUser = User.objects.all()[0]
```  
*If you created multiple users you will have to use Django queries to grab the exact user you want.*

 7. Then set the `tempUser` variable's `is_staff` value equal to true, and save the user. 
 ```python
tempUser.is_staff = True
```  
8. Exit the Django shell with the command `exit`
9. In a browser navigate to the admin portal. You can find this portal by using the base Squarelet URL, and appending /admin to the end of it.
10. Using the credentials you just created, login. *If you find yourself being redirected to the login page on successful credentials, change the browser you are using.* 
11. Navigate to [Clients](https://dev.squarelet.com/admin/oidc_provider/client/)
12. Create a client called `MuckRock Dev`
13. Make sure the fields have the following values:

|Field| Value |
|--|--|
| Owner | blank/your user account |
|Client Type|Confidential|
|Response Types|code (Authorization Code Flow)|
|Redirect URIs (on separate lines)|http://api.dev.documentcloud.org/accounts/complete/squarelet http://minio.documentcloud.org/accounts/complete/squarelet|
|JWT Algorithm|RS256|
|Require Consent?|Unchecked|
|Reuse Consent|Checked|
|Client ID|This will be filled in automatically upon saving|
|Client SECRET|This will be filled in automatically upon saving|
|Scopes (on separate lines)|read_user read_organization read_auth_token|
|Post Logout Redirect URIs|http://dev.documentcloud.org|
|Webhook URL (To make this field appear, Add a client profile)|http://api.dev.documentcloud.org/squarelet/webhook/|

14. Make sure in your **Squarelet project** `.envs/.local/.django` file, there exist values for: `STRIPE_PUB_KEYS`, `STRIPE_SECRET_KEYS`, and set `STRIPE_WEBHOOK_SECRETS=None`. Multiple values for any of the above should be comma delimited.

- You must always fully `docker-compose down` or Ctrl-C each time you change a `.django` file of a docker-compose session for it to take effect.

- Avoid changing Squarelet's `.django` file frequently to prevent Docker network problems from `docker-compose down`.

Be sure to stop (if needed) both the docker compose sessions DocumentCloud (Ctrl-C, or `docker-compose down`) and Squarelet (`docker-compose down` in Squarelet folder). Then run the Squarelet session using `inv up` in the squarelet folder. **Finally, run `docker-compose up` in this DocumentCloud folder to begin using the new dotfiles.**
-   This will build and start all of the DocumentCloud docker images using docker-compose. It will attach to the Squarelet network which must be already running. You can connect to Squarelet nginx on port 80 and it will serve the appropriate dependent http service, such as DocumentCloud, based on domain as a virtual host. The `local.yml` configuration file has the docker-compose details.
- If you do `docker-compose down` on Squarelet when none of the other dependent docker-compose sessions (such as DocumentCloud) are running, `docker-compose down` will delete the Squarelet network. You will have to explicitly bring the whole squarelet docker-compose session back up to recreate it and nginx before being able to start a dependent docker-compose session (such as DocumentCloud).
- Using `docker-compose up -d` rather than `docker-compose up` will make a daemon for DocumentCloud as Squarelet defaults to.

15. Click save and continue editing. Note down the `Client ID` and `Client SECRET` values. You will need these later.


## Install

### Software required

1. [docker][docker-install]
2. [docker-compose][docker-compose-install]
3. [python][python-install]
4. [invoke][invoke-install]
5. [git][git-install]

### Installation of DocumentCloud and its Authentication System

1. Install software above and Git Large File support [using these instructions](https://docs.github.com/en/repositories/working-with-files/managing-large-files/installing-git-large-file-storage). 
   - Ensure you have at least an additional 11 gigabytes of hard disk space allocated to Docker for these purposes.
   - Ensure your Docker host application has at least 7gb of memory allocated, 10gb preferred. 
   - These instructions create 3 distinct docker-compose sessions, with the Squarelet session hosting the shared central network. 
2. Check out the git repository - `git clone git@github.com:MuckRock/documentcloud.git`
3. Enter the directory - `cd documentcloud`
4. Run the dotenv initialization script - `python initialize_dotenvs.py`
   This will create files with the environment variables needed to run the development environment.
5. Set `api.dev.documentcloud.org` and `minio.documentcloud.org` to point to localhost - `echo "127.0.0.1 api.dev.documentcloud.org minio.documentcloud.org" | sudo tee -a /etc/hosts`
6. Run `export COMPOSE_FILE=local.yml;` in any of your command line sessions so that docker-compose finds the configuration.
7. Run `docker-compose up`.
8. Enter `api.dev.documentcloud.org/` into your browser - you should see the Django API root page. **Note that `api` is before `dev` in this service URL.**
10. Log in using the Squarelet superuser on the locally-running [Documentcloud-frontend](https://github.com/muckrock/documentcloud-frontend) that you installed earlier at http://dev.documentcloud.org
    - `SQUARELET_WHITELIST_VERIFIED_JOURNALISTS=True` environment variable makes it so only verified journalists can *log into* DocumentCloud.
    - Use the squarelet admin [Organization page](http://dev.squarelet.local/admin/organizations/organization/) to mark your organization as a verified journalist to allow upload to DocumentCloud.
    - **Make your Squarelet superuser also a superuser on DocumentCloud Django:** Run `inv shell` in the DocumentCloud folder and use these commands (no indent):
      ```
      tempUser = User.objects.all()[0]
      tempUser.is_superuser = True
      tempUser.save()
      tempUser.is_staff = True
      tempUser.save()
      ```
11. Go to [Django admin for DocumentCloud](http://api.dev.documentcloud.org/admin) and add the required static [flat page](http://api.dev.documentcloud.org/admin/flatpages/flatpage/) called `/tipofday/`. It can be blank. Do not prefix the URL with `/pages/`. Specifying the `Site` as `example.com` is alright.
12. Create an initial Minio bucket to simulate AWS S3 locally: 
      - Reference your DocumentCloud `.django` file for these variables: 
      - Visit the `MINIO_URL` with a browser, likely at [this address](http://minio.documentcloud.org:9000), and login with the minio `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`
      - At the bottom right corner click the round plus button and then click the first circle that appears above it to "create bucket".
      - Create a bucket called `documents`
13. Upload a document:
      - **Check your memory allocation on Docker is at least 7gb.** A sign that you do not have enough memory allocated is if containers are randomly failing or if your system is swapping heavily, especially when uploading documents.
      - The "upload" button should not be grayed out (if it is, check your user organization Verified Journalist status above)
      - If you get an error on your console about signatures, fix minio as above.
      - If you get an error on your console about tipofday not found, add the static page as above.
14. Develop DocumentCloud and its frontend!

   

[docker-install]: https://docs.docker.com/install/
[docker-compose-install]: https://docs.docker.com/compose/install/
[invoke-install]: http://www.pyinvoke.org/installing.html
[python-install]: https://www.python.org/downloads/
[git-install]: https://git-scm.com/downloads
