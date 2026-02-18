ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    ffmpeg \
    opus-dev \
    opus-tools \
    gcc \
    musl-dev \
    python3-dev \
    bash

# Copy requirements file
COPY requirements.txt /tmp/

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Copy root filesystem
COPY rootfs /
RUN chmod a+x /run.sh

WORKDIR /app

CMD ["/run.sh"]
