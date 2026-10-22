"""Each league's Odds API key and its spare: ODDS_API_KEY / ODDS_API_KEY_NFL_SECONDARY and ODDS_API_KEY_NBA /
ODDS_API_KEY_NBA_SECONDARY.

A sync spends the first key down to the credit floor, then switches to the spare and notes that the first one needs
rotating. Nothing is stored: every sync starts from the first key, so once it's replaced with a fresh one it's used again."""
from typing import Callable, Optional

import requests

from . import config
from .engine import odds


class KeyRing:
    def __init__(self, league: str, floor: Optional[int], log: Callable[[str], None]):
        self.keys = config.odds_keys(league)   # [(env var, key)], first key first, unset ones left out
        self.floor, self.log = floor, log
        self.left = {name: None for name, _ in self.keys}   # credits left on each key, once known
        self.i = 0
        self.rotate: list[str] = []   # keys this sync switched away from at the floor

    def __bool__(self):
        return bool(self.keys)

    @property
    def name(self) -> str:
        return self.keys[self.i][0]

    @property
    def key(self) -> str:
        return self.keys[self.i][1]

    @property
    def remaining(self) -> Optional[int]:
        return self.left[self.name]

    def total(self) -> Optional[int]:
        known = [v for v in self.left.values() if v is not None]
        return sum(known) if known else None

    def check(self) -> None:
        """Read every key's balance (free calls)."""
        for name, key in self.keys:
            try:
                self.left[name] = odds.credits_remaining(key)
                self.log(f"{name} has {self.left[name]} credits left (floor {self.floor})")
            except requests.RequestException as e:
                # every paid response reports the balance too, so the floor still applies from the first one
                self.log(f"  couldn't check the balance of {name} ({e}); going ahead, the floor applies from the first response")

    def afford(self, cost: int) -> bool:
        """Whether the key in use can spend cost credits without going under the floor, switching to the spare if not."""
        while self.floor is not None and self.remaining is not None and self.remaining - cost < self.floor:
            if self.i + 1 >= len(self.keys):
                return False
            nxt = self.keys[self.i + 1][0]
            self.log(f"  {self.name} is at the floor ({self.remaining} left): switching to {nxt}. Rotate {self.name}")
            self.rotate.append(self.name)
            self.i += 1
        return True

    def spent(self, left) -> None:
        """Record the balance a paid response reported."""
        if left is not None:
            self.left[self.name] = int(float(left))
