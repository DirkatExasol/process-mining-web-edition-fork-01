"""Per-source-IP sign-in throttle, shared by the app and admin login flows.

Account lockout (``max_failed_logins``) stops password-guessing against ONE
account, but not username-rotation from a single host — and it deliberately does
NOT apply to the break-glass built-in Administrator, nor to the TOTP *code* step
(a mistyped code must never disable an account). This time-based, self-recovering
cooldown covers those gaps: after a few failures from one IP the host waits out a
short cooldown, unlike the account lock a legitimate fat-fingered user isn't
stranded. In-memory per process (resets on restart, which is fine for brute-force).
"""

from __future__ import annotations

import threading
import time


class LoginThrottle:
    def __init__(
        self,
        *,
        max_fails: int = 3,       # failures within the window before throttling
        window: float = 900.0,    # 15-min sliding window over recent failures
        cooldown: float = 300.0,  # once tripped, wait this long from the last failure
        max_tracked: int = 4096,  # bound the map so a distributed flood can't grow it
    ) -> None:
        self.max_fails = max_fails
        self.window = window
        self.cooldown = cooldown
        self.max_tracked = max_tracked
        self.fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def client_ip(request) -> str:
        # Deliberately NOT trusting X-Forwarded-For: honouring a client-supplied
        # header would let an attacker rotate fake IPs to evade the throttle. The
        # socket peer address can't be spoofed.
        client = getattr(request, "client", None)
        return client.host if client else "unknown"

    def retry_after(self, ip: str) -> float:
        """Seconds this IP must wait before another attempt (0 = allowed now)."""
        now = time.monotonic()
        with self._lock:
            fails = [t for t in self.fails.get(ip, []) if now - t < self.window]
            if fails:
                self.fails[ip] = fails
            else:
                self.fails.pop(ip, None)
            if len(fails) >= self.max_fails:
                return max(0.0, self.cooldown - (now - fails[-1]))
            return 0.0

    def record_failure(self, ip: str) -> None:
        now = time.monotonic()
        with self._lock:
            self.fails.setdefault(ip, []).append(now)
            # Keep the map bounded: an entry is only pruned when its own IP retries,
            # so a botnet of one-shot IPs would otherwise leak memory. Over the cap,
            # first drop hosts whose failures have all aged out; if a real distributed
            # flood keeps us over, drop the least-recently-active hosts.
            if len(self.fails) > self.max_tracked:
                for k in [
                    k
                    for k, ts in self.fails.items()
                    if not ts or now - ts[-1] >= self.window
                ]:
                    self.fails.pop(k, None)
                while len(self.fails) > self.max_tracked:
                    oldest = min(self.fails, key=lambda k: self.fails[k][-1])
                    self.fails.pop(oldest, None)

    def clear(self, ip: str) -> None:
        """Forget an IP's failures — called on a fully successful sign-in."""
        with self._lock:
            self.fails.pop(ip, None)
