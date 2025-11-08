# Kernel building environment;
FROM gcr.io/syzkaller/syzbot@sha256:3f571049d7d230f8414ea4f65ef6f7c04e71368e216008d3f56fea627d228583 AS kbuilder-base
WORKDIR /
RUN mkdir /KBDr

# Install pip;
RUN apt update && apt install python3-pip python3-venv tar gzip zstd pigz cscope libdwarf-dev libdw-dev -y -q
RUN python3 -m venv venv

# Install kcore & kbuilder;
WORKDIR /KBDr
COPY ./kcore /KBDr/kcore
COPY ./kclient /KBDr/kclient
COPY ./kbuilder /KBDr/kbuilder
WORKDIR /KBDr/kcore
RUN /venv/bin/pip install .
WORKDIR /KBDr/kclient
RUN /venv/bin/pip install .
WORKDIR /KBDr/kbuilder
RUN /venv/bin/pip install .
WORKDIR /root

ENV KBUILDER_KERNEL_REPO_PATH=/mnt/repo

# Target: release
FROM kbuilder-base AS release
ENTRYPOINT ["/venv/bin/python3", "-m", "KBDr.kbuilder"]

# Target: debug
FROM kbuilder-base AS debug
RUN /venv/bin/pip install debugpy
ENTRYPOINT ["/venv/bin/python3", "-Xfrozen_modules=off", "-m", "debugpy", "--listen", "0.0.0.0:5678", "--wait-for-client", "-m", "KBDr.kbuilder"]
