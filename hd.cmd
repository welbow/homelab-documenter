@echo off
rem homelab-documenter's everyday commands (#29), so nobody has to remember
rem the docker compose flags. Run from anywhere: hd help
rem Every command rebuilds the image first if something changed.
setlocal
rem Before shift, which moves %0 too
set "here=%~dp0"
set "command=%~1"
if "%command%"=="" set "command=help"

rem The options after the command, passed on as they are
set "options="
shift
:collect
if "%~1"=="" goto dispatch
set options=%options% %1
shift
goto collect

:dispatch
pushd "%here%"
if /i "%command%"=="preview" goto preview
if /i "%command%"=="build" goto build
if /i "%command%"=="secret" goto secret
if /i "%command%"=="secrets" goto secret
if /i "%command%"=="test" goto test
if /i "%command%"=="help" goto help
if /i "%command%"=="-h" goto help
if /i "%command%"=="--help" goto help
echo Unknown command: %command% 1>&2
call :usage 1>&2
set "status=1"
goto done

:preview
call :refresh preview
docker compose run --rm --service-ports preview%options%
set "status=%ERRORLEVEL%"
goto done

:build
call :refresh build
docker compose run --rm build%options%
set "status=%ERRORLEVEL%"
goto done

:secret
call :refresh secrets
docker compose run --rm secrets%options%
set "status=%ERRORLEVEL%"
goto done

:test
call :refresh test
docker compose run --rm test%options%
set "status=%ERRORLEVEL%"
goto done

:help
call :usage
set "status=0"
goto done

:usage
echo Usage: hd ^<command^> [options]
echo.
echo   preview              Generate the packet and serve it on
echo                        http://127.0.0.1:8000 until Ctrl-C
echo   build                Generate the packet and export it (to /export, see
echo                        docker-compose.override.yml.example)
echo   secret set NAME      Store a credential (prompts; nothing is echoed)
echo   secret list          List the stored credentials (names only)
echo   secret check         Check each can be decrypted
echo   secret remove NAME   Remove a credential
echo                        (secrets works too: hd secrets list)
echo   test                 Run the test suite (extra options go to pytest)
echo   help                 This list
echo.
echo Extra options go to the command, e.g. hd preview --skip 500
exit /b 0

:refresh
rem Rebuild the image if something changed (quietly; a no-op when nothing
rem did). If that fails, e.g. offline, carry on with the image there is.
rem Docker Desktop on Windows prints a harmless "http2: ... error reading
rem preface from client" line now and then; that line is left out, any
rem other output is shown.
set "log=%TEMP%\hd-build-%RANDOM%.log"
docker compose build -q %1 >"%log%" 2>&1
set "built=%ERRORLEVEL%"
findstr /v /c:"error reading preface from client" "%log%"
del "%log%" 2>nul
if not "%built%"=="0" echo hd: couldn't rebuild the image (offline?); using the current one 1>&2
exit /b 0

:done
popd
exit /b %status%
