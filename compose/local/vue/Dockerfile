FROM node:10.9-slim

RUN printf "deb http://archive.debian.org/debian/ jessie main\ndeb-src http://archive.debian.org/debian/ jessie main\ndeb http://security.debian.org jessie/updates main\ndeb-src http://security.debian.org jessie/updates main" > /etc/apt/sources.list

# From https://daten-und-bass.io/blog/getting-started-with-vue-cli-on-docker/
RUN apt-get -y update \
  && apt-get install -y git

RUN npm install -g @vue/cli

RUN apt-get autoremove -y \
  && apt-get autoclean -y \
  && apt-get clean -y \
  && rm -rf /var/lib/apt/lists/*

EXPOSE 8080 5000

USER node

CMD cd /frontend && npm install && npm run serve -- --port 5000

