#!/bin/bash

# Shutdown nicely on exit signals 
function finally {
	exit 0
}
trap finally SIGINT SIGHUP SIGTERM

# Run Python script in subprocess to make sure that [defunct] processes are reaped 
# properly by bash. Google "docker PID 1 zombie reaping problem" for more info.
python /usr/lib/python/proxymatic/main.py $@
