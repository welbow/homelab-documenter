FROM python:3-alpine

WORKDIR /app
COPY . .

RUN apk update &&\
    apk add --virtual build-deps --no-cache wget unzip gcc musl-dev libffi-dev &&\
    apk add -U --no-cache bash nmap libc6-compat gcompat &&\
    pip3 install -r requirements.txt --no-cache-dir &&\
    apk del build-deps

ENTRYPOINT ["/usr/local/bin/python3", "/app/homelab-documenter.py"]
