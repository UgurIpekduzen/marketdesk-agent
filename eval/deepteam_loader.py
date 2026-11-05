"""DeepTeam, imported with its telemetry locked out.

The red team scan (eval/red_team.py) is the only place that uses DeepTeam. It
imports DeepTeam's names from here, so that the switches and the stand-ins below
are in place before DeepTeam is imported and the scan's own imports can stay at
the top of its file.
"""

import os
import sys
import types
from contextlib import contextmanager


class TelemetryBlockedError(RuntimeError):
    """A library that would report usage was asked to work."""


def blocked(*args, **kwargs):
    """Stand-in for the telemetry call: always raises."""
    raise TelemetryBlockedError("telemetry is switched off in this project")


def switch_telemetry_off() -> None:
    """The switches DeepTeam and DeepEval read when they are imported."""
    os.environ["DEEPTEAM_TELEMETRY_OPT_OUT"] = "YES"
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
    os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")


@contextmanager
def telemetry_locked_out():
    """Make DeepTeam's telemetry unable to run, whatever the switch says.

    DeepTeam imports sentry_sdk and posthog whether or not telemetry is on,
    without listing them as dependencies. While DeepTeam is imported,
    stand-ins take their place: they can be imported, and every use of them
    raises. DeepTeam keeps its references to them; afterwards they are taken
    out again, so other libraries (Chroma has a posthog telemetry of its own)
    still find no such library and leave their telemetry off.
    """
    sentry = types.ModuleType("sentry_sdk")
    sentry.__getattr__ = lambda name: blocked
    posthog = types.ModuleType("posthog")
    posthog.Posthog = type("Posthog", (), {"__init__": blocked})
    posthog.__getattr__ = lambda name: blocked
    stand_ins = {"sentry_sdk": sentry, "posthog": posthog}
    for name, module in stand_ins.items():
        if name in sys.modules:
            raise RuntimeError(f"{name} is loaded already: telemetry could run")
        sys.modules[name] = module
    try:
        yield
    finally:
        for name, module in stand_ins.items():
            if sys.modules.get(name) is module:
                del sys.modules[name]


switch_telemetry_off()
with telemetry_locked_out():
    from deepteam.attacks.multi_turn import CrescendoJailbreaking, LinearJailbreaking
    from deepteam.attacks.multi_turn.crescendo_jailbreaking.template import (
        JailBreakingCrescendoTemplate,
    )
    from deepteam.attacks.single_turn import (
        ROT13,
        Base64,
        Leetspeak,
        Multilingual,
        PermissionEscalation,
        PromptInjection,
        Roleplay,
    )
    from deepteam.red_teamer import RedTeamer
    from deepteam.test_case import RTTurn
    from deepteam.vulnerabilities import (
        BFLA,
        BOLA,
        RBAC,
        ExcessiveAgency,
        IndirectInstruction,
        PIILeakage,
        PromptLeakage,
        SQLInjection,
        SystemReconnaissance,
    )


__all__ = [
    "BFLA",
    "BOLA",
    "RBAC",
    "ROT13",
    "Base64",
    "CrescendoJailbreaking",
    "ExcessiveAgency",
    "IndirectInstruction",
    "JailBreakingCrescendoTemplate",
    "Leetspeak",
    "LinearJailbreaking",
    "Multilingual",
    "PIILeakage",
    "PermissionEscalation",
    "PromptInjection",
    "PromptLeakage",
    "RTTurn",
    "RedTeamer",
    "Roleplay",
    "SQLInjection",
    "SystemReconnaissance",
    "TelemetryBlockedError",
    "blocked",
    "switch_telemetry_off",
    "telemetry_locked_out",
]
