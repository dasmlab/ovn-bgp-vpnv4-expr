# Dockerfile for ovn-bgp-agent with VPNv4 driver
# This image includes the upstream ovn-bgp-agent service plus our VPNv4 driver

FROM registry.fedoraproject.org/fedora:40

# Install system dependencies
RUN dnf install -y python3 python3-pip iproute iputils && \
    dnf clean all && rm -rf /var/cache/dnf

# Install upstream ovn-bgp-agent package
# This provides the main service and AgentDriverBase interface
RUN pip3 install --no-cache-dir ovn-bgp-agent

# Install our VPNv4 driver package
# This registers the stevedore entry point and provides the driver code
WORKDIR /app
COPY . /app
RUN pip3 install --no-cache-dir /app

# The upstream agent runs as 'ovn-bgp-agent' command
# Configure via environment variables or config file
ENTRYPOINT ["ovn-bgp-agent"]

