#!/bin/sh

buildpkgs="`cat /app/apk-build-pkgs.txt | sed ':a;N;$!ba;s/\r\n/ /g'`"
pkgs="`cat /app/apk-pkgs.txt | sed ':a;N;$!ba;s/\r\n/ /g'`"

apk add --virtual build-deps --no-cache $buildpkgs
apk add -U --no-cache $pkgs