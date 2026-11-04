#!/usr/bin/env python3
# h1 - s1 - s2 - s4 - h2  (primary)
#        \- s3 -/         (backup)
import os
import sys
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


class PathTopo(Topo):
    def build(self):
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        s1 = self.addSwitch('s1', dpid='1')
        s2 = self.addSwitch('s2', dpid='2')
        s3 = self.addSwitch('s3', dpid='3')
        s4 = self.addSwitch('s4', dpid='4')

        self.addLink(h1, s1, port2=1)
        self.addLink(s1, s2, port1=2, port2=1)
        self.addLink(s1, s3, port1=3, port2=1)
        self.addLink(s2, s4, port1=2, port2=1)
        self.addLink(s3, s4, port1=2, port2=2)
        self.addLink(h2, s4, port2=3)


def make_net():
    switch = lambda name, **kw: OVSSwitch(name, protocols='OpenFlow13', **kw)
    net = Mininet(topo=PathTopo(), switch=switch, link=TCLink,
                  controller=None, autoSetMacs=False)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    return net


if __name__ == '__main__':
    setLogLevel('info')
    net = make_net()
    net.start()
    if '--auto' in sys.argv:
        d = os.path.dirname(os.path.abspath(__file__))
        h1, h2 = net.get('h1', 'h2')
        h2.cmd(f'python3 {d}/receiver.py > {d}/logs/receiver.log 2>&1 &')
        h1.cmd(f'sleep 1; python3 {d}/sender.py 10.0.0.2 100000 > {d}/logs/sender.log 2>&1 &')
        print('*** receiver and sender started (logs/receiver.log, logs/sender.log)')
    CLI(net)
    net.stop()
