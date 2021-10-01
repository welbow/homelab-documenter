FROM python:3-alpine

WORKDIR /app
COPY . .

RUN apk add -U bash &&\
    pip3 install dominate

ENTRYPOINT ["/usr/local/bin/python3", "/app/homelab-documenter.py"]
