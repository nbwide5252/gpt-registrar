"""Result dataclass for registration outcomes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Result:
    """Registration result."""
    ok: bool
    status: str = ""
    reason: str = ""
    email: str = ""
    password: str = ""
    phone: str = ""
    account: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "reason": self.reason,
            "email": self.email,
            "password": self.password,
            "phone": self.phone,
            "account": self.account,
            "artifacts": self.artifacts,
            "debug": self.debug,
        }
