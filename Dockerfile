FROM python:3.11.0a3-alpine3.15

WORKDIR /app
COPY . .

RUN apk update &&\
    chmod 755 /app/install-apk-pkgs.sh &&\
    /app/install-apk-pkgs.sh &&\
    pip3 install -r requirements.txt --no-cache-dir &&\
    cd /app &&\
    mkdir -p /app/bin &&\
    wget -qO bw.zip 'https://vault.bitwarden.com/download/?app=cli&platform=linux' &&\
    unzip -o bw.zip &&\
    chmod 755 bw &&\
    mv bw /app/bin/ &&\
    apk del build-deps

ENTRYPOINT ["/app/entrypoint.sh"]
