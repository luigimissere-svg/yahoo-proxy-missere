"""
Regime detection — Fase 3.2.

Trasforma il livello VIX corrente in un "regime" di volatilità del mercato,
da cui derivano due azioni:

    1. Deleveraging dei NEW BUY (riduce target_risk_pct via fattore moltiplicativo).
    2. Trailing stop adattivo (mult ATR più stretto nei regimi alti).

Regimi (default, ispirati a quantili storici VIX 1990-2024):

    LOW       VIX < 15        → size×1.0    trailing 2.5×ATR
    NORMAL    15 ≤ VIX < 20   → size×1.0    trailing 2.5×ATR
    ELEVATED  20 ≤ VIX < 25   → size×0.7    trailing 2.0×ATR
    HIGH      25 ≤ VIX < 35   → size×0.4    trailing 1.5×ATR
    EXTREME   VIX ≥ 35        → size×0.0 (NO new BUY)  trailing 1.0×ATR

Note di design:
- Stateless: una sola chiamata `detect(vix)` ritorna regime + parametri.
- Soglie e azioni sono iniettabili (per walk-forward in Fase 4).
- Modalità 'off' bypassa: regime sempre NORMAL, fattori = 1.0, trailing default.
- Se VIX non disponibile (None/NaN), regime = NORMAL (fallback sicuro).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional


RegimeName = Literal['LOW', 'NORMAL', 'ELEVATED', 'HIGH', 'EXTREME']
RegimeMode = Literal['off', 'deleveraging', 'full']


# Default soglie VIX (ascendenti, esclusive a destra)
DEFAULT_VIX_THRESHOLDS: Dict[RegimeName, float] = {
    'LOW':      15.0,   # VIX < 15
    'NORMAL':   20.0,   # 15 ≤ VIX < 20
    'ELEVATED': 25.0,   # 20 ≤ VIX < 25
    'HIGH':     35.0,   # 25 ≤ VIX < 35
    'EXTREME':  math.inf,  # VIX ≥ 35
}

# Fattori deleveraging applicati a target_risk_pct sui nuovi BUY
DEFAULT_DELEVERAGING: Dict[RegimeName, float] = {
    'LOW':      1.0,
    'NORMAL':   1.0,
    'ELEVATED': 0.7,
    'HIGH':     0.4,
    'EXTREME':  0.0,  # blocca nuovi BUY
}

# Trailing stop mult (× ATR) per regime
DEFAULT_TRAILING_ATR_MULT: Dict[RegimeName, float] = {
    'LOW':      2.5,
    'NORMAL':   2.5,
    'ELEVATED': 2.0,
    'HIGH':     1.5,
    'EXTREME':  1.0,
}


@dataclass
class RegimeState:
    """Snapshot di un regime detection."""
    name: RegimeName
    vix: Optional[float]
    deleveraging_factor: float
    trailing_atr_mult: float
    block_new_buys: bool


@dataclass
class RegimeDetector:
    """
    Stateless detector: data una lettura VIX, ritorna regime + parametri.

    Attributes:
        mode: 'off' (bypass, ritorna sempre NORMAL puro), 'deleveraging'
              (applica solo size deleveraging), 'full' (size + trailing).
        thresholds: dict regime → soglia superiore (esclusiva).
        deleveraging: dict regime → fattore size (1.0 = nessuna riduzione).
        trailing_atr_mult: dict regime → mult ATR per trailing stop.
        fallback_regime: usato quando VIX None/NaN/non-finito.
    """
    mode: RegimeMode = 'off'
    thresholds: Dict[RegimeName, float] = field(
        default_factory=lambda: dict(DEFAULT_VIX_THRESHOLDS)
    )
    deleveraging: Dict[RegimeName, float] = field(
        default_factory=lambda: dict(DEFAULT_DELEVERAGING)
    )
    trailing_atr_mult: Dict[RegimeName, float] = field(
        default_factory=lambda: dict(DEFAULT_TRAILING_ATR_MULT)
    )
    fallback_regime: RegimeName = 'NORMAL'

    # Ordine ascendente per lookup
    _ORDER = ('LOW', 'NORMAL', 'ELEVATED', 'HIGH', 'EXTREME')

    def __post_init__(self):
        if self.mode not in ('off', 'deleveraging', 'full'):
            raise ValueError(
                f"mode must be 'off' | 'deleveraging' | 'full', got {self.mode}"
            )
        # Sanity: tutte le regime keys presenti in ogni dict
        for d, name in (
            (self.thresholds, 'thresholds'),
            (self.deleveraging, 'deleveraging'),
            (self.trailing_atr_mult, 'trailing_atr_mult'),
        ):
            missing = [r for r in self._ORDER if r not in d]
            if missing:
                raise ValueError(f"{name} missing regimes: {missing}")
        # Sanity: soglie ascendenti
        prev = -math.inf
        for r in self._ORDER:
            t = self.thresholds[r]
            if t < prev:
                raise ValueError(
                    f"thresholds non monotone: {r}={t} < precedente={prev}"
                )
            prev = t
        # Sanity: deleveraging in [0, 1+] (può anche essere >1 ma flagghiamo solo <0)
        for r, v in self.deleveraging.items():
            if v < 0:
                raise ValueError(f"deleveraging[{r}]={v} deve essere >= 0")
        if self.fallback_regime not in self._ORDER:
            raise ValueError(f"fallback_regime invalido: {self.fallback_regime}")

    # ── Public API ───────────────────────────────────────────────────────

    def detect(self, vix: Optional[float]) -> RegimeState:
        """
        Ritorna lo stato di regime corrente.

        Args:
            vix: livello VIX corrente (o None/NaN se non disponibile).

        Returns:
            RegimeState con name, deleveraging_factor, trailing_atr_mult, block_new_buys.
        """
        # mode='off' → bypass totale (regime neutro)
        if self.mode == 'off':
            return RegimeState(
                name='NORMAL',
                vix=vix,
                deleveraging_factor=1.0,
                trailing_atr_mult=DEFAULT_TRAILING_ATR_MULT['NORMAL'],
                block_new_buys=False,
            )

        # VIX non disponibile → fallback
        if vix is None or not math.isfinite(float(vix)):
            name = self.fallback_regime
        else:
            name = self._classify(float(vix))

        delev = self.deleveraging[name]
        # In modalità 'deleveraging' usiamo trailing default (NORMAL), non regime-aware
        if self.mode == 'deleveraging':
            trail = DEFAULT_TRAILING_ATR_MULT['NORMAL']
        else:
            trail = self.trailing_atr_mult[name]
        block = (delev <= 0.0)
        return RegimeState(
            name=name,
            vix=float(vix) if (vix is not None and math.isfinite(float(vix))) else None,
            deleveraging_factor=delev,
            trailing_atr_mult=trail,
            block_new_buys=block,
        )

    # ── Internal ─────────────────────────────────────────────────────────

    def _classify(self, vix: float) -> RegimeName:
        """Mappa VIX → RegimeName usando le soglie superiori esclusive."""
        for r in self._ORDER:
            t = self.thresholds[r]
            if vix < t:
                return r
        return 'EXTREME'  # safety net


def make_default_detector(mode: RegimeMode = 'off') -> RegimeDetector:
    """Factory: detector con parametri di default."""
    return RegimeDetector(mode=mode)
