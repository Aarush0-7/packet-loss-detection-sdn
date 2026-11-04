import json
import os
import time
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib import hub

ALERT_FILE = '/tmp/loss_alert'
RESET_FILE = '/tmp/sdn_reset'
STATE_FILE = '/tmp/sdn_state.json'

# dpid -> list of (in_port, out_port)
COMMON = {
    1: [(2, 1), (3, 1)],
    2: [(1, 2), (2, 1)],
    3: [(1, 2), (2, 1)],
    4: [(1, 3), (2, 3)],
}
PRIMARY = {1: [(1, 2)], 4: [(3, 1)]}
BACKUP = {1: [(1, 3)], 4: [(3, 2)]}

# ports on the primary path: (dpid, port)
PRIMARY_PORTS = [(1, 2), (2, 1), (2, 2), (4, 1)]

PRIMARY_PATH = ['h1', 's1', 's2', 's4', 'h2']
BACKUP_PATH = ['h1', 's1', 's3', 's4', 'h2']


class LossReroute(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}
        self.on_backup = False
        self.reroute_events = []
        self.last_alert = self.file_time(ALERT_FILE)
        self.last_reset = self.file_time(RESET_FILE)
        hub.spawn(self.watch_alerts)
        hub.spawn(self.write_state)

    def add_flow(self, dp, in_port, out_port):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        match = parser.OFPMatch(in_port=in_port)
        actions = [parser.OFPActionOutput(out_port)]
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=10, match=match, instructions=inst))

    def install(self, dp, table):
        for in_port, out_port in table.get(dp.id, []):
            self.add_flow(dp, in_port, out_port)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        self.install(dp, COMMON)
        self.install(dp, BACKUP if self.on_backup else PRIMARY)
        self.logger.info('s%d connected, flows installed (%s path)',
                         dp.id, 'backup' if self.on_backup else 'primary')

    def add_event(self, reason, old, new):
        self.reroute_events.append({'time': time.strftime('%H:%M:%S'), 'reason': reason,
                            'old': '-'.join(old), 'new': '-'.join(new)})

    def reroute(self, reason):
        if self.on_backup:
            return
        self.on_backup = True
        self.add_event(reason, PRIMARY_PATH, BACKUP_PATH)
        self.logger.info('*** REROUTE: %s -> switching to backup path s1-s3-s4 ***', reason)
        for dpid in BACKUP:
            if dpid in self.datapaths:
                self.install(self.datapaths[dpid], BACKUP)
        self.logger.info('*** s1: in_port=1 -> output:3, s4: in_port=3 -> output:2 ***')

    def reset(self):
        if not self.on_backup:
            return
        self.on_backup = False
        self.add_event('manual reset', BACKUP_PATH, PRIMARY_PATH)
        self.logger.info('*** RESET: switching back to primary path s1-s2-s4 ***')
        for dpid in PRIMARY:
            if dpid in self.datapaths:
                self.install(self.datapaths[dpid], PRIMARY)

    def file_time(self, name):
        return os.path.getmtime(name) if os.path.exists(name) else 0

    def watch_alerts(self):
        while True:
            t = self.file_time(ALERT_FILE)
            if t > self.last_alert:
                self.last_alert = t
                with open(ALERT_FILE) as f:
                    msg = f.read().strip()
                self.logger.info('Loss alert from receiver: %s', msg)
                self.reroute(msg.split(' in ')[0])
            t = self.file_time(RESET_FILE)
            if t > self.last_reset:
                self.last_reset = t
                self.reset()
            hub.sleep(1)

    def write_state(self):
        warned = False
        while True:
            state = {
                'switches': ['s%d' % d for d in sorted(self.datapaths)],
                'path': BACKUP_PATH if self.on_backup else PRIMARY_PATH,
                'path_name': 'backup' if self.on_backup else 'primary',
                'events': self.reroute_events,
                'time': time.time(),
            }
            try:
                with open(STATE_FILE + '.tmp', 'w') as f:
                    json.dump(state, f)
                os.replace(STATE_FILE + '.tmp', STATE_FILE)
            except OSError as e:
                if not warned:
                    self.logger.info('cannot write state file: %s', e)
                    warned = True
            hub.sleep(1)

    @set_ev_cls(ofp_event.EventOFPStateChange, DEAD_DISPATCHER)
    def switch_left(self, ev):
        dp = ev.datapath
        if dp.id in self.datapaths:
            del self.datapaths[dp.id]
            self.logger.info('s%d disconnected', dp.id)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status(self, ev):
        msg = ev.msg
        dp = msg.datapath
        port = msg.desc.port_no
        down = msg.desc.state & dp.ofproto.OFPPS_LINK_DOWN
        if down and (dp.id, port) in PRIMARY_PORTS:
            self.logger.info('Port down: s%d port %d', dp.id, port)
            self.reroute('link down (s%d port %d)' % (dp.id, port))
