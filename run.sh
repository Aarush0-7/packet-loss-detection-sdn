#!/bin/bash
# Starts controller, dashboard and Mininet (with receiver + sender). Type "exit" in Mininet to stop.
if [ "$EUID" -ne 0 ]; then exec sudo "$0" "$@"; fi
cd "$(dirname "$0")"
mkdir -p logs

pkill -f "[o]sken-manager"
pkill -f "[d]ashboard.py"
mn -c > /dev/null 2>&1
rm -f /tmp/sdn_state.json /tmp/sdn_stats.json

./venv/bin/osken-manager --ofp-tcp-listen-port 6653 controller.py > logs/controller.log 2>&1 &
CTRL=$!
python3 dashboard.py > logs/dashboard.log 2>&1 &
DASH=$!
sleep 3

echo "Dashboard: http://localhost:5000"
python3 topo.py --auto

kill $CTRL $DASH 2> /dev/null
mn -c > /dev/null 2>&1
