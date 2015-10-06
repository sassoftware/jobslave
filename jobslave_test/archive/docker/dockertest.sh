#!/bin/bash

set -e

# Naming convention:
# base-<tag1>-child-<tag1>
# where:
#   tag1 can be e, c, ec or empty
#   tag2 can be e, c, e2, c2, e2c2 or empty
# e2 or c2 mean different values in the child, compared to the parent

function write {
    cmd=$1
    shift

    $cmd ${@} 2>&1 | tee -a docker_run.log
}

function cleanup {
    docker rm -fv $(docker ps -aq)
    docker rmi -f $(docker images -qa) 2>/dev/null
}

trap cleanup SIGINT SIGTERM

truncate -s 0 docker_run.log
NAMES=$(ls | grep ^base | sort)

for name in ${NAMES}; do
    write echo "Build ${name} --->"
    write docker build -t test/${name} ${name}/
    write echo "<--- Done Build ${name}"
    docker inspect test/${name} | python -c "import sys, json; cfg = json.load(sys.stdin)[0]['Config']; print((cfg.get('Entrypoint'), cfg.get('Cmd')))" > result-${name}
done

write echo "<--- Done building --->"

for name in $NAMES; do
    write echo "Run ${name} --->"
    write docker run --rm test/${name}
    write echo "<--- Done Run ${name}"
done
