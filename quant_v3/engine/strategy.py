"""
PatrimonioStrategy — strategia Backtrader v3.0 base.

Architettura:
    - Per ogni feed (ticker), istanzia 6 moduli alpha (trend, momentum, ...).
    - Ad ogni barra, ogni modulo produce uno score ∈ [-1, +1].
    - CompositeSignal aggrega gli score in un composite con gating (Hybrid A+C).
    - Logic decisionale:
        - composite > 0 e nessuna position → BUY (long entry)
        - composite < 0 e position aperta  → SELL (close long)
    - Sizing base: equal-weight, max N posizioni, cap per-ticker.
    - Stop loss / take profit / trailing (configurabili).

Logging:
    - Ogni trade scrive un record in self.trade_log (lista di dict).
    - A fine run, dump in CSV via self.dump_log(path).

NOTA: questa è la versione 2.2 (BASE).
Fase 2.3 arricchirà i moduli, Fase 3 aggiungerà risk management avanzato.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import backtrader as bt

from engine.signals import CompositeSignal, DEFAULT_WEIGHTS
from engine.modules import DEFAULT_MODULES

logger = logging.getLogger(__name__)


class PatrimonioStrategy(bt.Strategy):
    """
    Strategy base v3.0 — long-only, multi-asset.

    Params:
        weights: dict modulo→peso per CompositeSignal (default DEFAULT_WEIGHTS)
        threshold: composite threshold per emettere segnale (default 0.20)
        min_concordant: moduli concordi minimi (default 3)
        max_positions: numero max ticker in portafoglio (default 10)
        per_ticker_cap: max % cash per singolo ticker (default 0.10 = 10%)
        stop_loss: stop loss % dal prezzo entry (default None = off)
        take_profit: take profit % dal prezzo entry (default None = off)
        trailing_pct: trailing stop % dal massimo (default None = off)
        warmup_bars: bars di warmup prima di emettere segnali (default 200)
        verbose: log trade details
    """

    params = (
        ('weights', None),          # popolato in __init__
        ('threshold', 0.20),
        ('min_concordant', 3),
        ('max_positions', 10),
        ('per_ticker_cap', 0.10),
        ('stop_loss', None),
        ('take_profit', None),
        ('trailing_pct', None),
        ('warmup_bars', 200),
        ('verbose', False),
        ('module_classes', None),   # popolato in __init__
    )

    # ── Init ─────────────────────────────────────────────────────────────

    def __init__(self):
        # Default weights/modules
        weights = self.p.weights or DEFAULT_WEIGHTS
        module_classes = self.p.module_classes or DEFAULT_MODULES

        self.composite = CompositeSignal(
            weights=weights,
            threshold=self.p.threshold,
            min_concordant=self.p.min_concordant,
        )

        # Istanzio i moduli per OGNI feed (data) → dict[data] = dict[mod_name → AlphaModule]
        self._modules: Dict[bt.feeds.PandasData, Dict[str, object]] = {}
        for d in self.datas:
            mods = {}
            for mod_name, mod_cls in module_classes.items():
                m = mod_cls()
                m.prepare(d)
                mods[mod_name] = m
            self._modules[d] = mods

        # Tracking
        self.entry_price: Dict[str, float] = {}
        self.entry_bar: Dict[str, int] = {}
        self.peak_price: Dict[str, float] = {}   # per trailing stop
        self.trade_log: List[dict] = []
        self.bar_count = 0

    # ── Helpers ──────────────────────────────────────────────────────────

    def _ticker(self, data) -> str:
        """Ritorna nome del feed (settato via cerebro.adddata(name=...))."""
        return data._name or str(data)

    def _composite_score(self, data) -> tuple[float, dict]:
        """Calcola composite score per un feed. Ritorna (score, diagnostic)."""
        scores = {}
        for mod_name, mod in self._modules[data].items():
            scores[mod_name] = mod.score()
        diag = self.composite.diagnose(scores)
        return diag['composite_after_gating'], diag

    def _open_positions_count(self) -> int:
        return sum(1 for d in self.datas if self.getposition(d).size > 0)

    def _can_open_new(self) -> bool:
        return self._open_positions_count() < self.p.max_positions

    def _size_for(self, data) -> int:
        """Sizing equal-weight rispettando per_ticker_cap."""
        cash = self.broker.get_cash()
        portfolio_value = self.broker.get_value()
        # Available cash budget = min(cash, cap × portfolio_value)
        budget = min(cash, self.p.per_ticker_cap * portfolio_value)
        price = data.close[0]
        if price <= 0 or budget <= 0:
            return 0
        size = int(budget / price)
        return max(0, size)

    # ── Main loop ────────────────────────────────────────────────────────

    def next(self):
        self.bar_count += 1

        # Warmup
        if self.bar_count < self.p.warmup_bars:
            return

        for d in self.datas:
            tk = self._ticker(d)
            pos = self.getposition(d)
            score, diag = self._composite_score(d)

            # Aggiorna peak per trailing
            if pos.size > 0 and tk in self.entry_price:
                self.peak_price[tk] = max(self.peak_price.get(tk, 0.0), d.close[0])

            # ── EXIT logic (priorità su entry) ────────────────────────
            if pos.size > 0:
                exit_reason = self._check_exit(d, tk, score)
                if exit_reason:
                    self.close(data=d)
                    if self.p.verbose:
                        self.log(f"EXIT {tk} reason={exit_reason} composite={score:.3f}")
                    self._record_trade(tk, d, 'EXIT', score, diag, exit_reason)
                    continue

            # ── ENTRY logic ───────────────────────────────────────────
            if pos.size == 0 and score > 0 and self._can_open_new():
                size = self._size_for(d)
                if size > 0:
                    self.buy(data=d, size=size)
                    self.entry_price[tk] = d.close[0]
                    self.entry_bar[tk] = self.bar_count
                    self.peak_price[tk] = d.close[0]
                    if self.p.verbose:
                        self.log(f"BUY {tk} size={size} px={d.close[0]:.2f} composite={score:.3f}")
                    self._record_trade(tk, d, 'BUY', score, diag, 'composite_signal')

    # ── Exit logic ───────────────────────────────────────────────────────

    def _check_exit(self, data, ticker: str, score: float) -> Optional[str]:
        """Ritorna reason string se occorre uscire, None altrimenti."""
        # 1. Composite reversal
        if score < 0:
            return 'composite_reversal'

        entry = self.entry_price.get(ticker)
        if entry is None:
            return None

        px = data.close[0]

        # 2. Stop loss
        if self.p.stop_loss is not None:
            if px <= entry * (1.0 - self.p.stop_loss):
                return f'stop_loss({self.p.stop_loss:.2%})'

        # 3. Take profit
        if self.p.take_profit is not None:
            if px >= entry * (1.0 + self.p.take_profit):
                return f'take_profit({self.p.take_profit:.2%})'

        # 4. Trailing stop
        if self.p.trailing_pct is not None:
            peak = self.peak_price.get(ticker, entry)
            if px <= peak * (1.0 - self.p.trailing_pct):
                return f'trailing({self.p.trailing_pct:.2%})'

        return None

    # ── Logging ──────────────────────────────────────────────────────────

    def log(self, msg: str):
        dt = self.datas[0].datetime.date(0)
        logger.info(f"[{dt}] {msg}")

    def _record_trade(self, ticker: str, data, action: str, score: float, diag: dict, reason: str):
        self.trade_log.append({
            'date': data.datetime.date(0).isoformat(),
            'ticker': ticker,
            'action': action,
            'price': float(data.close[0]),
            'composite': float(score),
            'sign': diag.get('sign'),
            'n_concordant': diag.get('n_concordant'),
            'reason': reason,
            'cash_after': float(self.broker.get_cash()),
            'portfolio_value': float(self.broker.get_value()),
        })

    def stop(self):
        n_buys = sum(1 for t in self.trade_log if t['action'] == 'BUY')
        n_exits = sum(1 for t in self.trade_log if t['action'] == 'EXIT')
        logger.info(
            f"Strategy ended. Bars={self.bar_count}  "
            f"BUY={n_buys}  EXIT={n_exits}  "
            f"final_value={self.broker.get_value():,.2f}"
        )

    # ── Public API ───────────────────────────────────────────────────────

    def dump_log(self, path: str):
        """Dump trade log to CSV."""
        import csv
        if not self.trade_log:
            return
        keys = list(self.trade_log[0].keys())
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(self.trade_log)
        logger.info(f"Trade log → {path} ({len(self.trade_log)} rows)")
