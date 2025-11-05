# syntax=docker/dockerfile:1

FROM registry.fedoraproject.org/fedora:40

RUN dnf install -y python3 python3-pip iproute && \
    dnf clean all && rm -rf /var/cache/dnf

WORKDIR /app
COPY . /app

RUN pip3 install --no-cache-dir .

ENTRYPOINT ["vpnv4-agent"]
CMD ["--config", "/etc/ovn-bgp-agent/vpnv4.yaml"]


