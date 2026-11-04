# Packet Loss Detection and Recovery

**Team 8, Section A** – Computer Networks Lab, Project 7

## Problem Statement

Create a UDP application that detects packet loss using sequence numbers and works with an SDN controller to switch traffic to an alternate path.

## Topology

```
                 (primary)
            2 +----+ 2
         +----| s2 |----+
         |  1 +----+ 1  |
 +--+  1 +----+      +----+ 3  +--+
 |h1|----| s1 |      | s4 |----|h2|
 +--+    +----+      +----+    +--+
         |  3 +----+ 2  |
         +----| s3 |----+
            1 +----+ 2
                 (backup)

h1 = 10.0.0.1     h2 = 10.0.0.2
Primary path: h1 - s1 - s2 - s4 - h2
Backup path:  h1 - s1 - s3 - s4 - h2
(numbers are OpenFlow port numbers)
```

## How It Works

- **topo.py** builds the topology in Mininet with Open vSwitch (OpenFlow 1.3) and a remote controller at 127.0.0.1:6653.
- **controller.py** (OS-Ken app) installs `in_port -> out_port` flows for the primary path when the switches connect (no flooding, since the topology has a loop). It switches to the backup path by changing the flows on s1 (`in_port=1 -> output:3`) and s4 (`in_port=3 -> output:2`) when:
  1. the receiver writes a loss alert to `/tmp/loss_alert`, or
  2. a port on the primary path goes down (OpenFlow port-status event).
- **sender.py** sends UDP packets `"seq,timestamp"` to port 5005 every 50 ms, then sends `END,<count>`.
- **dashboard.py** (Flask) serves a live web dashboard on port 5000 and has buttons to break/restore the primary link, inject/remove loss, and reset to the primary path.
- **receiver.py** checks for gaps in sequence numbers, prints missing seqs, prints the loss % for every window of 50 packets, and writes the alert file when a window has more than 10% loss. At the end it prints received / lost / overall loss %.

Loss is injected with `tc netem` on s1-eth2 (s1's port towards s2), so only the primary path is lossy.

## Setup

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch python3-pip python3-venv git python3-flask
sudo service openvswitch-switch start
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install "os-ken==2.11.2"
mkdir -p logs
```

os-ken is pinned to 2.11.2 because newer versions (4.x) no longer include `osken-manager`.

## Live Dashboard (quick start)

One command starts everything (controller, dashboard, Mininet, receiver and a long-running sender):

```bash
cd ~/pld
./run.sh
```

Then open **http://localhost:5000** in a browser on Windows (WSL2 forwards localhost).

The dashboard updates every second and shows:

- the topology, with the active path in green and a broken link as a red dashed line
- packets received, packets lost, overall loss %, current path and number of reroutes
- a live chart of loss % per window of 50 packets, plus recent missing sequence numbers
- live flow tables of s1 and s4 (in_port -> output, packet count)
- the reroute event log (time, reason, old path -> new path)

Buttons:

| Button | What it does |
|---|---|
| Break primary link | `ip link set s1-eth2 down` and `s2-eth1 down` |
| Restore link | brings both interfaces back up |
| Inject 30% loss | `tc qdisc replace dev s1-eth2 root netem loss 30%` |
| Remove loss | `tc qdisc del dev s1-eth2 root` |
| Reset to primary | writes `/tmp/sdn_reset`; the controller moves back to the primary path |

Demo with the dashboard:

1. **Link failure:** click *Break primary link*. The controller reroutes at once, the path turns green on s1-s3-s4, s1-s2 turns red dashed, and the s1 flow `in_port 1` changes to `output:3`. Click *Restore link*, then *Reset to primary*.
2. **Packet loss:** click *Inject 30% loss*. Within a few seconds a window goes above 10% loss, the receiver alerts the controller, traffic moves to the backup path, and the loss chart goes back to 0. Click *Remove loss*, then *Reset to primary*.

To stop, type `exit` in the Mininet CLI (`run.sh` then stops the controller and dashboard too). Logs are in `logs/`. Live state is written to `/tmp/sdn_state.json` (controller) and `/tmp/sdn_stats.json` (receiver).

### Taking screenshots for the report

1. Run `./run.sh` and open http://localhost:5000 in your browser.
2. Wait about 10 seconds so the chart has some points, and take a screenshot (Win + Shift + S).
3. Click *Break primary link*, wait 3 seconds, and take a screenshot (backup path in green, red dashed link, event in the log).
4. Click *Restore link*, *Reset to primary*, then *Inject 30% loss*. Wait about 10 seconds and take a screenshot (loss spike in the chart, reroute event).
5. Save the screenshots in a `screenshots/` folder and add them to this README with `![Dashboard](screenshots/dashboard.png)`.

## Manual Demo (Mininet CLI only)

Terminal 1 – controller:

```bash
cd ~/pld
./venv/bin/osken-manager --ofp-tcp-listen-port 6653 controller.py
```

Terminal 2 – topology:

```bash
cd ~/pld
sudo mn -c
sudo python3 topo.py
```

Restart the controller before each demo so it starts on the primary path again.

### Demo 1 – packet loss on the primary path

In the Mininet CLI:

```
mininet> h1 ping -c 2 h2
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
mininet> h2 python3 receiver.py > logs/receiver.log &
mininet> h1 python3 sender.py 10.0.0.2 600 > logs/sender.log &
mininet> sh tc qdisc add dev s1-eth2 root netem loss 30%
```

Wait about 30 seconds, then:

```
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
mininet> sh cat logs/receiver.log
mininet> exit
```

### Demo 2 – link failure on the primary path

In the Mininet CLI:

```
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
mininet> h2 python3 receiver.py > logs/receiver.log &
mininet> h1 python3 sender.py 10.0.0.2 600 > logs/sender.log &
mininet> link s1 s2 down
```

Wait about 30 seconds, then:

```
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
mininet> sh cat logs/receiver.log
mininet> exit
```

## Expected Output

Flows on s1 before the reroute:

```
priority=10,in_port=2 actions=output:1
priority=10,in_port=3 actions=output:1
priority=10,in_port=1 actions=output:2
```

After the reroute (`output:2` becomes `output:3`):

```
priority=10,in_port=2 actions=output:1
priority=10,in_port=3 actions=output:1
priority=10,in_port=1 actions=output:3
```

Receiver (Demo 1):

```
window 100-149: received 50/50, loss 0.0%
missing seq: [160]
missing seq: [164, 165]
...
window 150-199: received 42/50, loss 16.0%
ALERT: loss above 10%, notifying controller
window 200-249: received 45/50, loss 10.0%
window 250-299: received 50/50, loss 0.0%
...
----- summary -----
received: 587
lost: 13
overall loss: 2.17%
```

Controller (Demo 1):

```
s1 connected, flows installed (primary path)
...
Loss alert from receiver: loss 16.0% in window 150-199
*** REROUTE: packet loss alert -> switching to backup path s1-s3-s4 ***
*** s1: in_port=1 -> output:3, s4: in_port=3 -> output:2 ***
```

Controller (Demo 2):

```
Port down: s1 port 2
*** REROUTE: link down on primary path -> switching to backup path s1-s3-s4 ***
*** s1: in_port=1 -> output:3, s4: in_port=3 -> output:2 ***
```

In Demo 2 the receiver shows 0% (or almost 0%) loss because the controller reroutes as soon as the port goes down.
