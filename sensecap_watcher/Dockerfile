ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip jq bash

COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

COPY run.sh /run.sh
COPY watcher_bridge.py /watcher_bridge.py
RUN chmod a+x /run.sh

CMD ["/run.sh"]
