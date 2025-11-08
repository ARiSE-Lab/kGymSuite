FROM python:3.11-bookworm AS kscheduler-base

RUN apt update && apt install -y build-essential

COPY ./kcore /KBDr/kcore
COPY ./kclient /KBDr/kclient
COPY ./kscheduler /KBDr/kscheduler
WORKDIR /KBDr/kcore
RUN pip install .
WORKDIR /KBDr/kclient
RUN pip install .
WORKDIR /KBDr/kscheduler
RUN pip install .
WORKDIR /root

ENV KSCHEDULER_DB_STR=/root/scheduler-db/scheduler.db
ENV KSCHEDULER_CONFIG=/root/config.json

# Target: release
FROM kscheduler-base AS release
ENTRYPOINT ["/usr/local/bin/python3", "-m", "KBDr.kscheduler"]
