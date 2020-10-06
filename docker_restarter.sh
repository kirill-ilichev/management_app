#!/bin/bash

while true
do
 inotifywait --exclude .swp -e create -e modify -e delete -e move nginx/nginx.conf
 docker-compose run nginx nginx -t
 if [ $? -eq 0 ]
 then
  echo "Detected Nginx Configuration Change"
  echo "Executing: docker-compose restart"
  docker-compose restart
 fi
done
