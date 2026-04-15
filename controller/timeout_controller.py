import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import packet
from ryu.ofproto import ofproto_v1_3


class TimeoutController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    IDLE_TIMEOUT = 10
    HARD_TIMEOUT = 30
    FLOW_PRIORITY = 10

    def __init__(self, *args, **kwargs):
        super(TimeoutController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.active_flows = {}
        self.flow_index = {}
        self.cookie_counter = 1

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.mac_to_port.setdefault(datapath.id, {})
        self.install_table_miss_flow(datapath)

    def install_table_miss_flow(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=0,
            match=match,
            instructions=instructions,
        )
        datapath.send_msg(mod)

        self.logger.info(
            "Installed permanent table-miss rule on switch %s",
            datapath.id,
        )

    def add_timed_flow(self, datapath, match, actions, flow_key):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]

        previous_cookie = self.flow_index.pop(flow_key, None)
        if previous_cookie is not None:
            self.active_flows.pop(previous_cookie, None)
            self.logger.info(
                "Refreshing timed flow on switch %s for %s",
                datapath.id,
                self.describe_flow_key(flow_key),
            )

        cookie = self.cookie_counter
        self.cookie_counter += 1

        mod = parser.OFPFlowMod(
            datapath=datapath,
            cookie=cookie,
            priority=self.FLOW_PRIORITY,
            match=match,
            instructions=instructions,
            idle_timeout=self.IDLE_TIMEOUT,
            hard_timeout=self.HARD_TIMEOUT,
            flags=ofproto.OFPFF_SEND_FLOW_REM,
        )
        datapath.send_msg(mod)

        self.active_flows[cookie] = {
            "flow_key": flow_key,
            "installed_at": time.time(),
        }
        self.flow_index[flow_key] = cookie

        self.logger.info(
            "Installed timed flow on switch %s for %s with idle_timeout=%ss hard_timeout=%ss",
            datapath.id,
            self.describe_flow_key(flow_key),
            self.IDLE_TIMEOUT,
            self.HARD_TIMEOUT,
        )

    def describe_flow_key(self, flow_key):
        dpid, in_port, src, dst = flow_key
        return "dpid=%s in_port=%s src=%s dst=%s" % (dpid, in_port, src, dst)

    def flow_removed_reason(self, msg):
        ofproto = msg.datapath.ofproto
        reasons = {
            ofproto.OFPRR_IDLE_TIMEOUT: "idle timeout",
            ofproto.OFPRR_HARD_TIMEOUT: "hard timeout",
            getattr(ofproto, "OFPRR_DELETE", None): "controller delete",
            getattr(ofproto, "OFPRR_GROUP_DELETE", None): "group delete",
        }
        return reasons.get(msg.reason, "unknown reason")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][eth.src] = in_port

        out_port = self.mac_to_port[dpid].get(eth.dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_src=eth.src,
                eth_dst=eth.dst,
            )
            flow_key = (dpid, in_port, eth.src, eth.dst)
            self.add_timed_flow(datapath, match, actions, flow_key)

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data,
        )
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed_handler(self, ev):
        msg = ev.msg
        flow_state = self.active_flows.pop(msg.cookie, None)
        reason = self.flow_removed_reason(msg)

        if flow_state is None:
            self.logger.info(
                "Observed expired flow on switch %s with cookie=%s (%s), but it was not tracked",
                msg.datapath.id,
                msg.cookie,
                reason,
            )
            return

        flow_key = flow_state["flow_key"]
        self.flow_index.pop(flow_key, None)
        lifetime = time.time() - flow_state["installed_at"]

        self.logger.info(
            "Flow lifecycle complete on switch %s for %s: removed due to %s after %.2fs, packets=%s, bytes=%s",
            msg.datapath.id,
            self.describe_flow_key(flow_key),
            reason,
            lifetime,
            msg.packet_count,
            msg.byte_count,
        )
