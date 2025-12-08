FROM python:3.9-alpine
ENV TZ="Asia/Shanghai"

WORKDIR /tmp

RUN apk add --no-cache git \
    && git config --global --add safe.directory "*" \
    && git clone https://github.com/Liu-cloud136/fans-medal-helper /app/fans-medal-helper \
    && pip install --no-cache-dir -r /app/fans-medal-helper/requirements.txt \
    && rm -rf /tmp/*

WORKDIR /app/fans-medal-helper

ENTRYPOINT ["/bin/sh","/app/fans-medal-helper/entrypoint.sh"]