#!/bin/bash

cd "$(dirname "$(which $0)")" > /dev/null 2>&1

LOG_FILE="shell2restapi.log"
PID_FILE="shell2restapi.pid"

if [ ! -f "$PID_FILE" ]; then
    python -u shell2restapi.py -p 80 -c file://shell2restapi.json > $LOG_FILE 2>&1 &
    sleep 0.5
    if [ $(ps -p $! | wc -l) -ne 2 ]; then
        cat $LOG_FILE
        #echo "Error: process died. see logfile '$LOG_FILE' for details ..."
    else
        echo $! > $PID_FILE
    fi
else
    echo "PID=$(cat $PID_FILE) looks like it's still running ..."
fi

cd - > /dev/null 2>&1

