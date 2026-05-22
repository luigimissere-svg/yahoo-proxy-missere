"""Alpha modules registry."""
from .base import AlphaModule
from .trend import TrendModule
from .momentum import MomentumModule
from .mean_reversion import MeanReversionModule
from .value import ValueModule
from .quality import QualityModule
from .event_driven import EventDrivenModule

# Default module set per PatrimonioStrategy
DEFAULT_MODULES = {
    'trend':          TrendModule,
    'momentum':       MomentumModule,
    'mean_reversion': MeanReversionModule,
    'value':          ValueModule,
    'quality':        QualityModule,
    'event_driven':   EventDrivenModule,
}

__all__ = [
    'AlphaModule', 'TrendModule', 'MomentumModule',
    'MeanReversionModule', 'ValueModule', 'QualityModule',
    'EventDrivenModule', 'DEFAULT_MODULES',
]
