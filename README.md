# DocumentCloud
**DocumentCloud** &middot; [Squarelet][squarelet] &middot; [MuckRock][muckrock] &middot; [DocumentCloud-Frontend][documentcloudfrontend]

Analyze, Annotate, Publish. Turn documents into data.

### Prerequisites
You must first have these set up and ready to go: 
- [Squarelet][squarelet]. DocumentCloud depends on Squarelet for user authentication. As the services need to communicate directly, the development environment for DocumentCloud depends on the development environment for Squarelet - the DocumentCloud docker containers will join Squarelet's docker network. Please install Squarelet and set up its development environment first.
- [DocumentCloud frontend][documentcloudfrontend]

*Note the front end will not be functional until you complete the current install.

## Install

### Software required

1. [docker][docker-install]
3. [python][python-install]
4. [invoke][invoke-install]
5. [git][git-install]

### Installation of DocumentCloud and its Authentication System

1. Install software above and Git Large File support [using these instructions](https://docs.github.com/en/repositories/working-with-files/managing-large-files/installing-git-large-file-storage). 
   - Ensure you have at least an additional 11 gigabytes of hard disk space allocated to Docker for these purposes.
   - Ensure your Docker host application has at least 7gb of memory allocated, 10gb preferred. 
   - These instructions create 3 distinct docker compose sessions, with the Squarelet session hosting the shared central network. 
2. Check out the git repository - `git clone git@github.com:MuckRock/documentcloud.git`
3. Enter the directory - `cd documentcloud`
4. Run the dotenv initialization script - `python initialize_dotenvs.py`
   This will create files with the environment variables needed to run the development environment.
5. Set `api.dev.documentcloud.org` and `minio.documentcloud.org` to point to localhost - `echo "127.0.0.1 api.dev.documentcloud.org minio.documentcloud.org" | sudo tee -a /etc/hosts`
6. Run `export COMPOSE_FILE=local.yml;` in any of your command line sessions so that docker compose finds the configuration.
7. Run `docker compose up`.
8. Enter `api.dev.documentcloud.org/` into your browser - you should see the Django API root page. **Note that `api` is before `dev` in this service URL.**
9. In  `.envs/.local/.django` set the following environment variables:

-   `SQUARELET_KEY`  to the value of Client ID from the Squarelet Client
-   `SQUARELET_SECRET`  to the value of Client SECRET from the Squarelet Client
- Additionally, get the value for `JWT_VERIFYING_KEY` by opening the Squarelet Django shell using `inv shell` and copying the `settings.SIMPLE_JWT['VERIFYING_KEY']` (remove the leading `b'` and the trailing `'`, leave the `\n` portions as-is)
10. You must restart the Docker Compose session (via the command `docker compose down` followed by `docker compose up`) each time you change a `.django` file for it to take effect.
11. Log in using the Squarelet superuser on the locally-running [Documentcloud-frontend](https://github.com/muckrock/documentcloud-frontend) that you installed earlier at https://dev.documentcloud.org
    - `SQUARELET_WHITELIST_VERIFIED_JOURNALISTS=True` environment variable makes it so only verified journalists can *log into* DocumentCloud.
    - Use the squarelet admin [Organization page](https://dev.squarelet.com/admin/organizations/organization/) to mark your organization as a verified journalist to allow upload to DocumentCloud.
    - **Make your Squarelet superuser also a superuser on DocumentCloud Django:** Run `inv shell` in the DocumentCloud folder and use these commands (no indent):
      ```
      tempUser = User.objects.all()[0]
      tempUser.is_superuser = True
      tempUser.save()
      tempUser.is_staff = True
      tempUser.save()
      ```
12. Go to [Django admin for DocumentCloud](https://api.dev.documentcloud.org/admin) and add the required static [flat page](https://api.dev.documentcloud.org/admin/flatpages/flatpage/) called `/tipofday/`. It can be blank. Do not prefix the URL with `/pages/`. Specifying the `Site` as `example.com` is alright.
13. Create an initial Minio bucket to simulate AWS S3 locally: 
      - Reference your DocumentCloud `.django` file for these variables: 
      - Visit the `MINIO_URL` with a browser, likely at [this address](https://minio.documentcloud.org:9000), and login with the minio `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`
      - At the bottom right corner click the round plus button and then click the first circle that appears above it to "create bucket".
      - Create a bucket called `documents`
14. Upload a document:
      - **Check your memory allocation on Docker is at least 7gb.** A sign that you do not have enough memory allocated is if containers are randomly failing or if your system is swapping heavily, especially when uploading documents.
      - The "upload" button should not be grayed out (if it is, check your user organization Verified Journalist status above)
      - If you get an error on your console about signatures, fix minio as above.
      - If you get an error on your console about tipofday not found, add the static page as above.
15. Develop DocumentCloud and its frontend!

   

[docker-install]: https://docs.docker.com/install/
[invoke-install]: http://www.pyinvoke.org/installing.html
[python-install]: https://www.python.org/downloads/
[git-install]: https://git-scm.com/downloads
[muckrock]: https://github.com/MuckRock/muckrock
[documentcloudfrontend]: https://github.com/MuckRock/documentcloud-frontend
[squarelet]: https://github.com/muckrock/squarelet
