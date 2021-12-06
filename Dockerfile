FROM python:3-alpine

WORKDIR /app
COPY . .

RUN apk update &&\
    apk add --virtual build-deps --no-cache wget unzip gcc musl-dev libffi-dev &&\
    apk add -U --no-cache bash nmap libc6-compat gcompat &&\
    pip3 install -r requirements.txt --no-cache-dir &&\
    cd /app &&\
    mkdir -p /app/bin &&\
    wget -qO bw.zip 'https://vault.bitwarden.com/download/?app=cli&platform=linux' &&\
    unzip -o bw.zip &&\
    chmod 755 bw &&\
    mv bw /app/bin/ &&\
    apk del build-deps

ENTRYPOINT ["/app/entrypoint.sh"]
