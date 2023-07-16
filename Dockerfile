FROM python:3.10-slim-bookworm
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y \
        nano vim \
        libpcap0.8 \
        xterm \
        iputils-ping net-tools iproute2 ethtool iw wireless-tools \
        curl wget
WORKDIR /fog_client
COPY . .
RUN pip install -r requirements.txt
