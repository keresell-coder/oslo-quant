"""Analytical frameworks package."""

from oslo_quant.frameworks.dupont import DuPontFramework
from oslo_quant.frameworks.piotroski import PiotroskiFramework
from oslo_quant.frameworks.sloan import SloanFramework
from oslo_quant.frameworks.ohlson import OhlsonFramework
from oslo_quant.frameworks.altman import AltmanFramework

FRAMEWORK_REGISTRY = {
    "dupont": DuPontFramework,
    "piotroski": PiotroskiFramework,
    "sloan": SloanFramework,
    "ohlson": OhlsonFramework,
    "altman": AltmanFramework,
}

__all__ = list(FRAMEWORK_REGISTRY.keys()) + ["FRAMEWORK_REGISTRY"]
