from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List


@dataclass
class LaneState:
    tray: int
    bport: int
    lane: int
    connected: bool = False
    ber: float = 0.0
    status: str = "not_connected"


class CB2TSimulator:
    def __init__(self) -> None:
        self.connected = False

    def discover(self, trays: int, bports_per_tray: int, lanes_per_bport: int) -> List[LaneState]:
        lanes: List[LaneState] = []
        for t in range(1, trays + 1):
            for p in range(1, bports_per_tray + 1):
                for l in range(1, lanes_per_bport + 1):
                    is_connected = random.random() > 0.02
                    lanes.append(
                        LaneState(
                            tray=t,
                            bport=p,
                            lane=l,
                            connected=is_connected,
                            status="connected" if is_connected else "error",
                        )
                    )
        self.connected = True
        return lanes

    def run_prbs(self, lanes: List[LaneState], ber_threshold: float) -> List[LaneState]:
        for lane in lanes:
            if not lane.connected:
                lane.status = "error"
                lane.ber = 1.0
                continue
            lane.ber = 10 ** random.uniform(-14, -6)
            lane.status = "pass" if lane.ber <= ber_threshold else "fail"
        return lanes
