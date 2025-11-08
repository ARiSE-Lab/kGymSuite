FROM python:3.11-bookworm

RUN apt update && apt install -y build-essential git

COPY ./kcore /KBDr/kcore
RUN pip install /KBDr/kcore

COPY ./kclient /KBDr/kclient
RUN pip install /KBDr/kclient
