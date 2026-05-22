"""
Portfolio Constraints — Fase 3.3.

Vincoli pre-trade applicati ai candidati BUY:
    1. Sector cap: max X% NAV per settore GICS.
    2. Portfolio beta cap: max Σ(weight_i × beta_i).

Design:
    - Stateless: una sola chiamata `would_violate(candidate)` per ciascun BUY.
    - Lo stato (posizioni esistenti) è passato esplicitamente, niente side effects.
    - Strategia su violazione: 'block_new' (skip) o 'scale_down' (riduce size).
    - Mapping ticker → (sector, beta) caricato una sola volta da parquet.

Edge cases gestiti:
    - Ticker non in mapping: sector='Unknown' (pool catch-all), beta=1.0 (neutro).
    - Beta NaN nel mapping: trattato come 1.0.
    - max_sector_pct=0 o None: disabilita sector cap.
    - max_portfolio_beta=0 o None: disabilita beta cap.

Formule:
    sector_exposure(s) = Σ_{t in s} (notional_t / NAV)
    portfolio_beta     = Σ_t (notional_t / NAV) × beta_t

Non viene ridistribuito il cash residuo: il vincolo si applica al singolo BUY
candidate, non ribilancia posizioni esistenti.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


ViolationPolicy = Literal['block_new', 'scale_down']

DEFAULT_BETA = 1.0
DEFAULT_SECTOR = 'Unknown'


# ─── Helpers I/O ─────────────────────────────────────────────────────────────

def load_metadata(path: str | Path) -> Tuple[Dict[str, str], Dict[str, float]]:
    """
    Carica mapping ticker→sector e ticker→beta da parquet.

    Returns:
        (sector_map, beta_map). beta_map ha float; ticker senza beta → DEFAULT_BETA.
    """
    p = Path(path)
    if not p.exists():
        logger.warning(f"Metadata file non trovato: {p}")
        return {}, {}
    df = pd.read_parquet(p)
    sector_map: Dict[str, str] = {}
    beta_map: Dict[str, float] = {}
    for _, row in df.iterrows():
        tk = str(row['ticker'])
        sector_map[tk] = str(row.get('sector') or DEFAULT_SECTOR)
        b = row.get('beta')
        if b is not None and not pd.isna(b) and math.isfinite(float(b)):
            beta_map[tk] = float(b)
        else:
            beta_map[tk] = DEFAULT_BETA
    return sector_map, beta_map


# ─── Core ────────────────────────────────────────────────────────────────────

@dataclass
class PortfolioConstraints:
    """
    Engine di constraint check per nuovi BUY candidate.

    Attributes:
        sector_map: ticker → sector. Default: vuoto (tutti Unknown).
        beta_map: ticker → beta. Default: vuoto (tutti DEFAULT_BETA=1.0).
        max_sector_pct: cap % NAV per settore (None/0 = disabilitato).
        max_portfolio_beta: cap portfolio beta (None/0 = disabilitato).
        violation_policy: 'block_new' o 'scale_down'.
        unknown_pool: se True, ticker Unknown formano un pool unico
                      (somma esposizione). Se False, ogni Unknown è ignorato
                      (no cap su Unknown).
    """
    sector_map: Dict[str, str] = field(default_factory=dict)
    beta_map: Dict[str, float] = field(default_factory=dict)
    max_sector_pct: Optional[float] = 0.30
    max_portfolio_beta: Optional[float] = 1.3
    violation_policy: ViolationPolicy = 'block_new'
    unknown_pool: bool = True

    def __post_init__(self):
        if self.violation_policy not in ('block_new', 'scale_down'):
            raise ValueError(
                f"violation_policy must be 'block_new' or 'scale_down', "
                f"got {self.violation_policy}"
            )
        if self.max_sector_pct is not None and self.max_sector_pct < 0:
            raise ValueError(f"max_sector_pct must be >= 0, got {self.max_sector_pct}")
        if self.max_portfolio_beta is not None and self.max_portfolio_beta < 0:
            raise ValueError(f"max_portfolio_beta must be >= 0, got {self.max_portfolio_beta}")

    # ── Lookups ──────────────────────────────────────────────────────────

    def sector_of(self, ticker: str) -> str:
        return self.sector_map.get(ticker, DEFAULT_SECTOR)

    def beta_of(self, ticker: str) -> float:
        b = self.beta_map.get(ticker, DEFAULT_BETA)
        return b if (b is not None and math.isfinite(b)) else DEFAULT_BETA

    @property
    def sector_cap_enabled(self) -> bool:
        return self.max_sector_pct is not None and self.max_sector_pct > 0

    @property
    def beta_cap_enabled(self) -> bool:
        return self.max_portfolio_beta is not None and self.max_portfolio_beta > 0

    # ── Exposure ─────────────────────────────────────────────────────────

    def sector_exposure(
        self,
        positions: Dict[str, float],
        nav: float,
    ) -> Dict[str, float]:
        """
        Ritorna esposizione % NAV per settore.

        Args:
            positions: dict ticker → notional_eur (size × price corrente).
            nav: NAV totale portfolio.

        Returns:
            dict sector → exposure_pct (0..1). Solo settori con esposizione > 0.
        """
        if nav <= 0:
            return {}
        out: Dict[str, float] = {}
        for tk, notional in positions.items():
            if notional <= 0:
                continue
            s = self.sector_of(tk)
            if s == DEFAULT_SECTOR and not self.unknown_pool:
                continue  # ignora Unknown se non in pool
            out[s] = out.get(s, 0.0) + notional / nav
        return out

    def portfolio_beta(
        self,
        positions: Dict[str, float],
        nav: float,
    ) -> float:
        """
        Beta-weighted del portfolio. Posizioni con weight = notional/NAV.

        Cash non-invested contribuisce 0 al beta (assumiamo cash beta=0).
        """
        if nav <= 0:
            return 0.0
        b = 0.0
        for tk, notional in positions.items():
            if notional <= 0:
                continue
            b += (notional / nav) * self.beta_of(tk)
        return b

    # ── Constraint check ─────────────────────────────────────────────────

    def would_violate(
        self,
        candidate_ticker: str,
        candidate_notional: float,
        positions: Dict[str, float],
        nav: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifica se aggiungere candidate_notional al ticker candidato violerebbe i cap.

        Returns:
            (violates, reason). reason è None se ok, altrimenti stringa diagnostica.
        """
        if nav <= 0 or candidate_notional <= 0:
            return (False, None)

        # Sector cap
        if self.sector_cap_enabled:
            s = self.sector_of(candidate_ticker)
            if not (s == DEFAULT_SECTOR and not self.unknown_pool):
                exp = self.sector_exposure(positions, nav)
                current = exp.get(s, 0.0)
                new_exp = current + candidate_notional / nav
                if new_exp > self.max_sector_pct:
                    return (True, f"sector_cap({s}:{new_exp:.1%}>{self.max_sector_pct:.0%})")

        # Beta cap
        if self.beta_cap_enabled:
            current_beta = self.portfolio_beta(positions, nav)
            cand_beta = self.beta_of(candidate_ticker)
            new_beta = current_beta + (candidate_notional / nav) * cand_beta
            if new_beta > self.max_portfolio_beta:
                return (True, f"beta_cap({new_beta:.2f}>{self.max_portfolio_beta:.2f})")

        return (False, None)

    def max_notional_allowed(
        self,
        candidate_ticker: str,
        positions: Dict[str, float],
        nav: float,
    ) -> float:
        """
        Massimo notional consentito dai cap residui (usato in scale_down).

        Ritorna 0 se non c'è spazio. Ritorna +inf se nessun cap è binding.
        """
        if nav <= 0:
            return 0.0
        caps = [float('inf')]

        # Sector cap residuo
        if self.sector_cap_enabled:
            s = self.sector_of(candidate_ticker)
            if not (s == DEFAULT_SECTOR and not self.unknown_pool):
                exp = self.sector_exposure(positions, nav)
                current_pct = exp.get(s, 0.0)
                residual_pct = max(0.0, self.max_sector_pct - current_pct)
                caps.append(residual_pct * nav)

        # Beta cap residuo (tiene conto del beta del candidato)
        if self.beta_cap_enabled:
            current_beta = self.portfolio_beta(positions, nav)
            cand_beta = self.beta_of(candidate_ticker)
            if cand_beta > 0:
                residual_beta = max(0.0, self.max_portfolio_beta - current_beta)
                # residual_beta = (extra_notional / nav) × cand_beta
                # → extra_notional = residual_beta × nav / cand_beta
                caps.append(residual_beta * nav / cand_beta)
            # se cand_beta <= 0 → ridurre il beta del portfolio, no cap su questo trade

        return float(min(caps))

    # ── Diagnostica ──────────────────────────────────────────────────────

    def diagnose(self, positions: Dict[str, float], nav: float) -> dict:
        """Snapshot completo per logging."""
        return {
            'nav': nav,
            'sector_exposure': self.sector_exposure(positions, nav),
            'portfolio_beta': self.portfolio_beta(positions, nav),
            'max_sector_pct': self.max_sector_pct,
            'max_portfolio_beta': self.max_portfolio_beta,
            'sector_cap_enabled': self.sector_cap_enabled,
            'beta_cap_enabled': self.beta_cap_enabled,
            'n_positions': sum(1 for n in positions.values() if n > 0),
        }


def make_default_constraints(
    metadata_path: Optional[str | Path] = None,
    max_sector_pct: Optional[float] = 0.30,
    max_portfolio_beta: Optional[float] = 1.3,
    violation_policy: ViolationPolicy = 'block_new',
) -> PortfolioConstraints:
    """Factory: costruisce PortfolioConstraints caricando metadata se path fornito."""
    sector_map, beta_map = ({}, {})
    if metadata_path:
        sector_map, beta_map = load_metadata(metadata_path)
    return PortfolioConstraints(
        sector_map=sector_map,
        beta_map=beta_map,
        max_sector_pct=max_sector_pct,
        max_portfolio_beta=max_portfolio_beta,
        violation_policy=violation_policy,
    )
