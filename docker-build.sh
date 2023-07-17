sudo docker build --tag fog_client:latest .
sudo docker build --tag fog_client:containernet --file Dockerfile-containernet . 
sudo docker build --tag fog_client:script --file Dockerfile-script .
sudo docker build --tag fog_client:containernet-script --file Dockerfile-containernet-script . 