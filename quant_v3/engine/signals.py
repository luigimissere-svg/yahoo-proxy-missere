"""
Composite signal scoring framework — Hybrid A+C.

Architettura:
    - Ogni modulo alpha (trend, momentum, mean_reversion, value, quality, event_driven)
      produce uno score in [-1, +1] per ogni ticker e ogni giorno.
    - Il composite score è weighted average dei moduli (A).
    - Filtro gating (C): trade solo se |composite| >= threshold E
      almeno min_concordant moduli concordano col segno del composite.
    - Pesi e soglie sono parametri ottimizzabili in Fase 4 (walk-forward).

Score normalization:
    Ogni modulo deve ritornare uno score già normalizzato in [-1, +1].
    L'aggregator NON ri-normalizza per non distruggere informazione di scala.

Uso:
    from engine.signals import CompositeSignal, DEFAULT_WEIGHTS

    sig = CompositeSignal(weights=DEFAULT_WEIGHTS, threshold=0.20, min_concordant=3)
    composite = sig.combine({
        'trend': 0.6,
        'momentum': 0.4,
        'mean_reversion': -0.1,
        'value': 0.3,
        'quality': 0.2,
        'event_driven': 0.0,
    })
    # → composite (float) o 0.0 se filtri non passati
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

# ─── Default config ──────────────────────────────────────────────────────────

# Pesi default — sommano a 1.0
# Questi sono il PUNTO DI PARTENZA: in Fase 4 saranno ottimizzati via walk-forward.
#
# Strategia B (pre-screening): value e quality sono ESCLUSI dal composite
# (weight=0) e usati solo come quality_filter pre-screening in strategy.py.
# Motivo: snapshot fundamentals statici introducevano bias value-tilt EU
# (banche/utilities) escludendo tech US (NVDA/AMZN/LLY/MU). Backtest 2024-08→2026-05:
#   - con fund nel composite: P&L -1.32%, Sharpe -0.054, DD 8.32%
#   - senza fund nel composite: P&L +12.29%, Sharpe +1.17, DD 4.06%
DEFAULT_WEIGHTS: Dict[str, float] = {
    'trend':          0.30,
    'momentum':       0.30,
    'mean_reversion': 0.20,
    'value':          0.00,   # filtro pre-screening, non composite
    'quality':        0.00,   # filtro pre-screening, non composite
    'event_driven':   0.20,
}

# Modulo names ammessi (lock per evitare typo silenziosi)
ALLOWED_MODULES = {'trend', 'momentum', 'mean_reversion', 'value', 'quality', 'event_driven'}


# ─── Composite combiner ──────────────────────────────────────────────────────

@dataclass
class CompositeSignal:
    """
    Combina N score modulo in un composite score con filtri gating.

    Attributes:
        weights: dict modulo → peso (deve sommare a 1.0)
        threshold: soglia minima |composite| per emettere segnale (default 0.20)
        min_concordant: numero minimo moduli concordi col segno del composite (default 3 / 6)
        concordance_eps: soglia oltre la quale un modulo è "concorde" (|score| > eps)
    """
    weights: Dict[str, float] = field(default_factory=lambda: DEFAULT_WEIGHTS.copy())
    threshold: float = 0.20
    min_concordant: int = 3
    concordance_eps: float = 0.10

    def __post_init__(self):
        # Validazioni
        unknown = set(self.weights) - ALLOWED_MODULES
        if unknown:
            raise ValueError(f"Unknown module(s) in weights: {unknown}. Allowed: {ALLOWED_MODULES}")
        # Pesi negativi vietati
        neg = [m for m, w in self.weights.items() if w < 0]
        if neg:
            raise ValueError(f"Negative weights not allowed: {neg}")
        s = sum(self.weights.values())
        if not 0.99 <= s <= 1.01:
            raise ValueError(f"Weights must sum to ~1.0, got {s:.4f}")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"threshold must be in [0,1], got {self.threshold}")
        # Moduli ATTIVI (peso > 0): usati per concordance count
        self._active_modules = [m for m, w in self.weights.items() if w > 0]
        max_concordant = len(self._active_modules)
        if not 0 <= self.min_concordant <= max_concordant:
            raise ValueError(
                f"min_concordant must be in [0, {max_concordant}] "
                f"(only {max_concordant} modules have weight>0), got {self.min_concordant}"
            )

    # ── Single-bar combine ────────────────────────────────────────────────

    def combine(self, scores: Dict[str, float]) -> float:
        """
        Combine module scores → composite (con gating).

        Args:
            scores: dict modulo → score in [-1, +1]. Moduli mancanti sono trattati come 0.

        Returns:
            composite score in [-1, +1], oppure 0.0 se gating non passa.

        NOTA: moduli con weight=0 vengono ignorati sia nel weighted average
        sia nel concordance count (per ridurre rumore).
        """
        # Weighted average (A) — solo moduli attivi (weight > 0)
        weighted_sum = 0.0
        for mod in self._active_modules:
            w = self.weights[mod]
            s = scores.get(mod, 0.0)
            if s is None or np.isnan(s):
                s = 0.0
            s = float(np.clip(s, -1.0, 1.0))
            weighted_sum += w * s

        # Threshold filter
        if abs(weighted_sum) < self.threshold:
            return 0.0

        # Concordance filter (C): conta quanti moduli ATTIVI concordano col segno
        sign = np.sign(weighted_sum)
        concordant = 0
        for mod in self._active_modules:
            s = scores.get(mod, 0.0)
            if s is None or np.isnan(s):
                continue
            if np.sign(s) == sign and abs(s) > self.concordance_eps:
                concordant += 1
        if concordant < self.min_concordant:
            return 0.0

        return float(np.clip(weighted_sum, -1.0, 1.0))

    # ── Diagnostic ────────────────────────────────────────────────────────

    def diagnose(self, scores: Dict[str, float]) -> dict:
        """
        Ritorna dict con composite, contributo di ogni modulo, n_concordant, decisione.
        Utile per logging e debug strategy.

        I moduli con weight=0 sono comunque inclusi in 'contributions' (per
        visibilità del loro score grezzo) ma non contano nel weighted_sum né
        nel concordance count.
        """
        contribs = {}
        weighted_sum = 0.0
        for mod, w in self.weights.items():
            s = float(scores.get(mod, 0.0) or 0.0)
            s_clip = float(np.clip(s, -1.0, 1.0))
            c = w * s_clip
            contribs[mod] = {'score': s_clip, 'weight': w, 'contribution': c}
            weighted_sum += c

        sign = np.sign(weighted_sum)
        # Concordance solo su moduli attivi
        concordant = sum(
            1 for mod in self._active_modules
            if np.sign(scores.get(mod, 0.0) or 0.0) == sign
            and abs(scores.get(mod, 0.0) or 0.0) > self.concordance_eps
        )

        emit = (abs(weighted_sum) >= self.threshold) and (concordant >= self.min_concordant)

        return {
            'composite': float(weighted_sum),
            'composite_after_gating': float(weighted_sum) if emit else 0.0,
            'sign': int(sign) if emit else 0,
            'n_concordant': int(concordant),
            'min_concordant_required': self.min_concordant,
            'n_active_modules': len(self._active_modules),
            'threshold': self.threshold,
            'contributions': contribs,
            'emitted': emit,
        }


# ─── Helpers per moduli (utility comuni) ─────────────────────────────────────

def normalize_score(value: float, lo: float, hi: float, invert: bool = False) -> float:
    """
    Mappa value ∈ [lo, hi] → [-1, +1] linearmente.
    Se invert=True, valore alto diventa score negativo (es. RSI alto = overbought = sell).

    Esempi:
        normalize_score(70, 30, 70, invert=True)  → -1.0  (RSI overbought)
        normalize_score(30, 30, 70, invert=True)  → +1.0  (RSI oversold)
        normalize_score(50, 30, 70, invert=True)  →  0.0
    """
    if hi == lo:
        return 0.0
    norm = 2.0 * (value - lo) / (hi - lo) - 1.0
    norm = float(np.clip(norm, -1.0, 1.0))
    return -norm if invert else norm


def zscore_to_score(z: float, cap: float = 3.0) -> float:
    """
    Mappa uno z-score → [-1, +1] usando tanh-like.
    Default cap=3σ → score=±0.995.
    """
    if cap <= 0:
        return 0.0
    return float(np.clip(z / cap, -1.0, 1.0))
