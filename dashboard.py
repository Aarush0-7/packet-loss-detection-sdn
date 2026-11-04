import json
import os
import re
import subprocess
import time
from flask import Flask, jsonify, render_template

STATE_FILE = '/tmp/sdn_state.json'
STATS_FILE = '/tmp/sdn_stats.json'
RESET_FILE = '/tmp/sdn_reset'
LINK = ['s1-eth2', 's2-eth1']

app = Flask(__name__)


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def read_json(name):
    try:
        with open(name) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def link_up():
    try:
        with open('/sys/class/net/s1-eth2/operstate') as f:
            return f.read().strip() == 'up'
    except OSError:
        return False


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/state')
def state():
    s = read_json(STATE_FILE)
    s['controller_alive'] = time.time() - s.get('time', 0) < 3
    s['link_up'] = link_up()
    s['loss_on'] = 'netem' in run('tc qdisc show dev s1-eth2')
    return jsonify(s)


@app.route('/api/stats')
def stats():
    return jsonify(read_json(STATS_FILE))


@app.route('/api/flows')
def flows():
    result = {}
    for sw in ['s1', 's2', 's3', 's4']:
        rows = []
        for line in run(f'ovs-ofctl -O OpenFlow13 --no-names dump-flows {sw}').splitlines():
            m = re.search(r'n_packets=(\d+).*in_port=(\d+).*actions=output:(\d+)', line)
            if m:
                rows.append({'in_port': int(m.group(2)), 'output': int(m.group(3)),
                             'packets': int(m.group(1))})
        result[sw] = sorted(rows, key=lambda r: r['in_port'])
    return jsonify(result)


@app.route('/api/link_down', methods=['POST'])
def link_down():
    for intf in LINK:
        run(f'ip link set {intf} down')
    return jsonify(ok=True)


@app.route('/api/link_up', methods=['POST'])
def link_restore():
    for intf in LINK:
        run(f'ip link set {intf} up')
    return jsonify(ok=True)


@app.route('/api/loss_on', methods=['POST'])
def loss_on():
    run('tc qdisc replace dev s1-eth2 root netem loss 30%')
    return jsonify(ok=True)


@app.route('/api/loss_off', methods=['POST'])
def loss_off():
    run('tc qdisc del dev s1-eth2 root')
    return jsonify(ok=True)


@app.route('/api/reset', methods=['POST'])
def reset():
    with open(RESET_FILE, 'w') as f:
        f.write(str(time.time()))
    return jsonify(ok=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
