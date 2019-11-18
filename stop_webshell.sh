#!/bin/bash

cd "$(dirname "$(which $0)")" > /dev/null 2>&1

PID_FILE="shell2restapi.pid"

if [ -f "$PID_FILE" ]; then
    kill $([ "$1" == "-f" ] && echo "-9")  $(cat $PID_FILE) > /dev/null 2>&1
    sleep 0.5
    if [ $(ps -p $(cat $PID_FILE) | wc -l ) -ne 2 ]; then
        echo "shell2restapi is stopped ..."
        rm -f "$PID_FILE"
    else
        echo "Can't stop shell2restapi PID=$(cat $PID_FILE) ..."
    fi
else
    echo "Couldn't find PID_FILE '$PID_FILE' ..."
fi

cd - > /dev/null 2>&1

