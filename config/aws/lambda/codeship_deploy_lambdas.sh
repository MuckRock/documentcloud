#!/bin/bash

set -e

PROCESSING_FOLDERS='(^config\/)|(^documentcloud\/documents\/processing\/)|(^documentcloud\/common\/)'
TAG=$1
DEPLOY_CONTEXT=$2
deploy_lambdas=0
tag_exists=0
echo "got tag $1 and deploy context $2"
# ensure we have the tags locally
git fetch --tags --all
if git rev-parse $TAG >/dev/null 2>&1
then
    # The tag exists. Check diffed files and deploy if needed
    echo "tag exists" $TAG
    tag_exists=1
    changed_files=$(git diff --name-only $TAG $CI_COMMIT_ID)
    for file in $changed_files
    do
        if [[ $file =~ $PROCESSING_FOLDERS ]]
        then
            echo "changed file" $file "matches"
            deploy_lambdas=1
            break
        fi
    done
else
    # The tag doesn't exist. Deploy
    echo "tag does not exist" $TAG
    deploy_lambdas=1
fi

if [[ $deploy_lambdas == 1 ]]
then
    echo "deploying to lambda"
    # deploy to lambda
    # sam requires python 3.7, app is currently using python 3.6
    OLD_PYENV_VERSION=$PYENV_VERSION
    OLD_PATH=$PATH
    PYENV_VERSION=3.7
    PATH=/home/rof/.pyenv/versions/3.8/bin/:$PATH
    pip install awscli
    pip install aws-sam-cli
    pip install invoke
    inv deploy-lambdas $DEPLOY_CONTEXT
    PYENV_VERSION=$OLD_PYENV_VERSION
    PATH=$OLD_PATH
    # Set the tag in Git
    echo "pushing tag"
    if [[ $tag_exists == 1 ]]
    then
        # delete the tag locally
        git tag -d $TAG
        # delete the tag on origin
        git push origin :refs/tags/$TAG
    fi
    # add the new tag
    git tag $TAG $CI_COMMIT_ID
    # push the tag explicitly
    git push origin $TAG
fi
