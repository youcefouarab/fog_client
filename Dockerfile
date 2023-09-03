FROM python:3.10-slim-bookworm
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y libpcap0.8 iperf3
WORKDIR /fog_client
COPY . .
RUN pip install -r requirements.txt
ENV IS_CONTAINER yes
