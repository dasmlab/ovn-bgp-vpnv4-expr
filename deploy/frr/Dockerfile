FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
    && curl -s https://deb.frrouting.org/frr/keys.asc | gpg --dearmor > /usr/share/keyrings/frr-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/frr-archive-keyring.gpg] https://deb.frrouting.org/frr $(lsb_release -sc) frr-stable" > /etc/apt/sources.list.d/frr.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends frr frr-pythontools \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/lib/frr:${PATH}" \
    FRR_RUNAS=frr \
    FRR_GROUP=frr \
    FRR_USER=frr

RUN mkdir -p /var/log/frr /var/run/frr \
    && chown -R frr:frr /var/log/frr /var/run/frr

COPY frr/daemons /etc/frr/daemons
COPY frr/vtysh.conf /etc/frr/vtysh.conf

CMD ["/usr/lib/frr/watchfrr", "zebra", "bgpd"]

