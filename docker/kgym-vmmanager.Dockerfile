FROM golang:1.24.6-bookworm AS syzkaller

WORKDIR /
RUN apt update && apt install git -y && git clone https://github.com/google/syzkaller.git
WORKDIR /syzkaller
RUN make all crush -j$(nproc)

FROM python:3.11-bookworm AS kvmmanager-base

RUN apt update && apt install git make texinfo bison flex zlib1g-dev git make qemu-system -y

WORKDIR /root

COPY --from=syzkaller /syzkaller/bin/syz-crush /usr/local/bin/syz-crush

# Install Golang toolchain;
RUN wget "https://dl.google.com/go/go1.24.6.linux-amd64.tar.gz" -O go.tar.gz && tar -C /usr/local -xzf go.tar.gz
ENV GOROOT=/usr/local/go
ENV PATH=$GOROOT/bin:$PATH

# Prepare a base syzkaller repo;
RUN git clone https://github.com/google/syzkaller.git

WORKDIR /root

# kvmmanager;
COPY ./kcore /KBDr/kcore
COPY ./kclient /KBDr/kclient
COPY ./kvmmanager /KBDr/kvmmanager

WORKDIR /KBDr/kcore
RUN pip install .
WORKDIR /KBDr/kclient
RUN pip install .
WORKDIR /KBDr/kvmmanager
RUN pip install .

WORKDIR /root

ENV KVMMANAGER_SYZKALLER_PATH=/root/syzkaller
ENV KVMMANAGER_WORK_DIR=/root/work_dir

FROM kvmmanager-base AS release
ENTRYPOINT ["/usr/local/bin/python3", "-m", "KBDr.kvmmanager"]

FROM kvmmanager-base AS debug
RUN pip install debugpy
ENTRYPOINT ["/usr/local/bin/python3", "-Xfrozen_modules=off", "-m", "debugpy", "--listen", "0.0.0.0:5678", "--wait-for-client", "-m", "KBDr.kvmmanager"]
