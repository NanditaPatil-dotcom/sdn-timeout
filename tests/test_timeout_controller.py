import unittest
from types import SimpleNamespace
from unittest import mock

import eventlet.wsgi

if not hasattr(eventlet.wsgi, "ALREADY_HANDLED"):
    eventlet.wsgi.ALREADY_HANDLED = object()

from controller.timeout_controller import TimeoutController


class FakeOfproto:
    OFPP_CONTROLLER = 0xFFFFFFFD
    OFPP_FLOOD = 0xFFFFFFFB
    OFPIT_APPLY_ACTIONS = 4
    OFPFF_SEND_FLOW_REM = 1
    OFPRR_IDLE_TIMEOUT = 0
    OFPRR_HARD_TIMEOUT = 1


class FakeParser:
    def OFPMatch(self, **kwargs):
        return SimpleNamespace(**kwargs)

    def OFPActionOutput(self, port):
        return SimpleNamespace(port=port)

    def OFPInstructionActions(self, instruction_type, actions):
        return SimpleNamespace(
            instruction_type=instruction_type,
            actions=actions,
        )

    def OFPFlowMod(self, **kwargs):
        return SimpleNamespace(**kwargs)

    def OFPPacketOut(self, **kwargs):
        return SimpleNamespace(**kwargs)


class FakeDatapath:
    def __init__(self, dpid=1):
        self.id = dpid
        self.ofproto = FakeOfproto()
        self.ofproto_parser = FakeParser()
        self.sent_msgs = []

    def send_msg(self, msg):
        self.sent_msgs.append(msg)


class TimeoutControllerTest(unittest.TestCase):
    def setUp(self):
        self.controller = TimeoutController()
        self.datapath = FakeDatapath()

    def test_switch_features_installs_permanent_table_miss_rule(self):
        event = SimpleNamespace(msg=SimpleNamespace(datapath=self.datapath))

        self.controller.switch_features_handler(event)

        self.assertEqual(len(self.datapath.sent_msgs), 1)
        flow_mod = self.datapath.sent_msgs[0]
        self.assertEqual(flow_mod.priority, 0)
        self.assertFalse(hasattr(flow_mod, "idle_timeout"))
        self.assertFalse(hasattr(flow_mod, "hard_timeout"))
        self.assertEqual(flow_mod.instructions[0].actions[0].port, FakeOfproto.OFPP_CONTROLLER)

    def test_packet_in_installs_timed_rule_for_known_destination(self):
        self.controller.mac_to_port[1] = {"00:00:00:00:00:02": 2}
        ethernet_frame = SimpleNamespace(
            src="00:00:00:00:00:01",
            dst="00:00:00:00:00:02",
            ethertype=0x0800,
        )
        packet_in = SimpleNamespace(
            datapath=self.datapath,
            match={"in_port": 1},
            buffer_id=7,
            data=b"frame-bytes",
        )
        event = SimpleNamespace(msg=packet_in)

        with mock.patch("controller.timeout_controller.packet.Packet") as packet_cls:
            packet_cls.return_value.get_protocol.return_value = ethernet_frame
            self.controller.packet_in_handler(event)

        self.assertEqual(len(self.datapath.sent_msgs), 2)
        flow_mod = self.datapath.sent_msgs[0]
        packet_out = self.datapath.sent_msgs[1]

        self.assertEqual(flow_mod.idle_timeout, self.controller.IDLE_TIMEOUT)
        self.assertEqual(flow_mod.hard_timeout, self.controller.HARD_TIMEOUT)
        self.assertEqual(flow_mod.flags, FakeOfproto.OFPFF_SEND_FLOW_REM)
        self.assertEqual(flow_mod.match.in_port, 1)
        self.assertEqual(flow_mod.match.eth_src, ethernet_frame.src)
        self.assertEqual(flow_mod.match.eth_dst, ethernet_frame.dst)
        self.assertEqual(packet_out.actions[0].port, 2)
        self.assertEqual(len(self.controller.active_flows), 1)

    def test_flow_removed_cleans_tracked_state(self):
        flow_key = (1, 1, "00:00:00:00:00:01", "00:00:00:00:00:02")
        match = self.datapath.ofproto_parser.OFPMatch(
            in_port=1,
            eth_src=flow_key[2],
            eth_dst=flow_key[3],
        )
        actions = [self.datapath.ofproto_parser.OFPActionOutput(2)]

        self.controller.add_timed_flow(self.datapath, match, actions, flow_key)
        cookie = next(iter(self.controller.active_flows))

        removal_event = SimpleNamespace(
            msg=SimpleNamespace(
                datapath=self.datapath,
                cookie=cookie,
                reason=FakeOfproto.OFPRR_IDLE_TIMEOUT,
                packet_count=3,
                byte_count=210,
            )
        )

        self.controller.flow_removed_handler(removal_event)

        self.assertNotIn(cookie, self.controller.active_flows)
        self.assertNotIn(flow_key, self.controller.flow_index)


if __name__ == "__main__":
    unittest.main()
