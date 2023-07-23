#!/bin/bash
sudo docker build --no-cache --tag fog_client:latest .
sudo docker build --no-cache --tag fog_client:containernet --file Dockerfile-containernet . 
sudo docker build --no-cache --tag fog_client:script --file Dockerfile-script .
sudo docker build --no-cache --tag fog_client:containernet-script --file Dockerfile-containernet-script . 