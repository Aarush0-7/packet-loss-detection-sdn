import socket
import sys
import time

PORT = 5005
INTERVAL = 0.05

if len(sys.argv) < 3:
    print('usage: python3 sender.py <dest_ip> <count>')
    sys.exit(1)

dest = sys.argv[1]
count = int(sys.argv[2])
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

for seq in range(count):
    sock.sendto(f'{seq},{time.time()}'.encode(), (dest, PORT))
    if seq % 50 == 0:
        print(f'sent seq {seq}', flush=True)
    time.sleep(INTERVAL)

for _ in range(5):
    sock.sendto(f'END,{count}'.encode(), (dest, PORT))
    time.sleep(0.1)
print(f'done, sent {count} packets', flush=True)
