FROM python:3.10-slim-bookworm
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y nano vim libpcap0.8 xterm iputils-ping net-tools curl wget
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
