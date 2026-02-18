ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:latest
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

# Copy application files
COPY app/ /app/
COPY run.sh /
RUN chmod a+x /run.sh

WORKDIR /app

CMD [ "/run.sh" ]
