# Kernel building environment;
FROM gcr.io/syzkaller/syzbot:latest AS kprebuilder-base
WORKDIR /
RUN mkdir /KBDr

# Install pip;
RUN apt update && apt install python3-pip python3-venv tar gzip zstd pigz cscope libdwarf-dev libdw-dev -y -q
RUN python3 -m venv venv

# Install kcore & kprebuilder;
WORKDIR /KBDr
COPY ./kcore /KBDr/kcore
COPY ./kclient /KBDr/kclient
COPY ./kprebuilder /KBDr/kprebuilder
WORKDIR /KBDr/kcore
RUN /venv/bin/pip install .
WORKDIR /KBDr/kclient
RUN /venv/bin/pip install .
WORKDIR /KBDr/kprebuilder
RUN /venv/bin/pip install .
WORKDIR /root

# Target: release
FROM kprebuilder-base AS release
ENTRYPOINT ["/venv/bin/python3", "-m", "KBDr.kprebuilder"]

# Target: debug
FROM kprebuilder-base AS debug
RUN /venv/bin/pip install debugpy
ENTRYPOINT ["/venv/bin/python3", "-Xfrozen_modules=off", "-m", "debugpy", "--listen", "0.0.0.0:5678", "--wait-for-client", "-m", "KBDr.kprebuilder"]
