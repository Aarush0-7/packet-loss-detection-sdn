import json
import os
import socket

PORT = 5005
WINDOW = 50
THRESHOLD = 10.0
ALERT_FILE = '/tmp/loss_alert'
STATS_FILE = '/tmp/sdn_stats.json'

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', PORT))
sock.settimeout(120)
print(f'listening on UDP {PORT}', flush=True)

received = 0
expected = 0
win_start = 0
win_recv = 0
total = None
windows = []
recent_missing = []


def check_window(start, got, size=WINDOW):
    loss = (size - got) * 100.0 / size
    print(f'window {start}-{start + size - 1}: received {got}/{size}, loss {loss:.1f}%', flush=True)
    if loss > THRESHOLD:
        print('ALERT: loss above 10%, notifying controller', flush=True)
        with open(ALERT_FILE, 'w') as f:
            f.write(f'loss {loss:.1f}% in window {start}-{start + size - 1}\n')
    windows.append(round(loss, 1))
    write_stats(start + size)


def write_stats(sent):
    lost = sent - received
    stats = {
        'received': received,
        'lost': lost,
        'loss_pct': round(lost * 100.0 / sent, 2) if sent else 0,
        'windows': windows[-30:],
        'missing': recent_missing[-20:],
    }
    with open(STATS_FILE + '.tmp', 'w') as f:
        json.dump(stats, f)
    os.replace(STATS_FILE + '.tmp', STATS_FILE)


while True:
    try:
        data, addr = sock.recvfrom(1024)
    except socket.timeout:
        print('timeout, no more packets', flush=True)
        break
    fields = data.decode().split(',')
    if fields[0] == 'END':
        total = int(fields[1])
        break
    seq = int(fields[0])
    if seq < expected:
        continue
    if seq > expected:
        missing = list(range(expected, seq))
        print(f'missing seq: {missing}', flush=True)
        recent_missing[:] = (recent_missing + missing)[-20:]
    while seq >= win_start + WINDOW:
        check_window(win_start, win_recv)
        win_start += WINDOW
        win_recv = 0
    win_recv += 1
    received += 1
    expected = seq + 1

if total is None:
    total = expected
if total > expected:
    print(f'missing seq: {list(range(expected, total))}', flush=True)
while win_start < total:
    check_window(win_start, win_recv, min(WINDOW, total - win_start))
    win_start += WINDOW
    win_recv = 0

lost = total - received
print('----- summary -----')
print(f'received: {received}')
print(f'lost: {lost}')
print(f'overall loss: {lost * 100.0 / total if total else 0:.2f}%', flush=True)
