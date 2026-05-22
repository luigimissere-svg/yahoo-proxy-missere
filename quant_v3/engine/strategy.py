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
from engine.sizing import PositionSizer

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
        # ── Pre-screening fundamentals (Strategia B) ──
        # I moduli value/quality non entrano nel composite (weight=0) ma
        # filtrano i candidati BUY: scartati solo se ENTRAMBI sotto floor (junk).
        # Se almeno uno score è 0 (fundamentals mancanti) → benefit of doubt, NON scarta.
        ('quality_filter_enabled', True),
        ('value_floor', -0.5),      # value_score >= -0.5 per passare (o NaN/0)
        ('quality_floor', -0.5),    # quality_score >= -0.5 per passare (o NaN/0)
        # ── Position sizing (Fase 3.1) ──
        ('sizing_method', 'vol_target'),   # 'equal' (legacy) | 'vol_target'
        ('target_risk_pct', 0.01),         # 1% NAV per trade (vol-target)
        ('min_position_pct', 0.005),       # 0.5% NAV: sotto skip
        ('vol_floor_pct', 0.005),          # vol floor = 0.5% prezzo
        ('vol_proxy', 'atr'),              # 'atr' | 'realized'
        ('vol_lookback', 14),              # ATR period (o realized vol window)
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

        # Position sizer (Fase 3.1)
        # NB: usiamo nome `_position_sizer` per evitare collisione con bt.Strategy.sizer
        self._position_sizer = PositionSizer(
            method=self.p.sizing_method,
            target_risk_pct=self.p.target_risk_pct,
            per_ticker_cap=self.p.per_ticker_cap,
            min_position_pct=self.p.min_position_pct,
            vol_floor_pct=self.p.vol_floor_pct,
            vol_proxy=self.p.vol_proxy,
        )

        # Istanzio i moduli per OGNI feed (data) → dict[data] = dict[mod_name → AlphaModule]
        self._modules: Dict[bt.feeds.PandasData, Dict[str, object]] = {}
        # ATR(period) indicator per ogni feed — usato per vol_target sizing
        self._atr: Dict[bt.feeds.PandasData, bt.indicators.ATR] = {}
        for d in self.datas:
            mods = {}
            for mod_name, mod_cls in module_classes.items():
                m = mod_cls()
                m.prepare(d)
                mods[mod_name] = m
            self._modules[d] = mods
            # ATR built-in Backtrader (high/low/close required)
            try:
                self._atr[d] = bt.indicators.ATR(d, period=self.p.vol_lookback)
            except Exception:
                self._atr[d] = None

        # Tracking
        self.entry_price: Dict[str, float] = {}
        self.entry_bar: Dict[str, int] = {}
        self.peak_price: Dict[str, float] = {}   # per trailing stop
        self.trade_log: List[dict] = []
        self.bar_count = 0
        # Counter pre-screening (diagnostica)
        self.n_filtered_by_quality = 0

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
        # Includo gli score grezzi (anche dei moduli weight=0) per il pre-screening
        diag['raw_scores'] = scores
        return diag['composite_after_gating'], diag

    def _passes_quality_filter(self, diag: dict) -> bool:
        """
        Pre-screening Strategia B: scarta candidato BUY solo se ENTRAMBI
        value e quality score sono sotto i floor configurati (junk stock).

        Logica permissiva (benefit of doubt):
        - score == 0 o NaN  → fundamentals mancanti, NON usare per filtrare
        - score > floor     → passa
        - solo se ENTRAMBI strict < floor → scarta
        """
        if not self.p.quality_filter_enabled:
            return True
        scores = diag.get('raw_scores', {})
        v = scores.get('value', 0.0)
        q = scores.get('quality', 0.0)
        # NaN / mancante → tratta come 0 (neutro)
        try:
            import math as _math
            if v is None or _math.isnan(v):
                v = 0.0
            if q is None or _math.isnan(q):
                q = 0.0
        except Exception:
            pass
        # Scarta solo se ENTRAMBI strict sotto floor
        if v < self.p.value_floor and q < self.p.quality_floor:
            return False
        return True

    def _open_positions_count(self) -> int:
        return sum(1 for d in self.datas if self.getposition(d).size > 0)

    def _pending_buys_count(self) -> int:
        """Conta ordini BUY pending (non ancora eseguiti)."""
        try:
            return sum(1 for o in self.broker.get_orders_open() if o.isbuy())
        except Exception:
            return 0

    def _can_open_new(self) -> bool:
        # Include posizioni aperte + ordini buy pending nello stesso bar
        total = self._open_positions_count() + self._pending_buys_count()
        return total < self.p.max_positions

    def _vol_eur(self, data) -> float | None:
        """
        Stima vol_proxy in valuta per il feed:
        - 'atr':       ATR(N) corrente (in valuta, già corretto)
        - 'realized':  std(returns_N) × close
        Ritorna None se non disponibile (warmup, dati insufficienti).
        """
        if self.p.vol_proxy == 'atr':
            atr = self._atr.get(data)
            if atr is None:
                return None
            try:
                v = float(atr[0])
                if not math.isfinite(v) or v <= 0:
                    return None
                return v
            except (IndexError, ValueError):
                return None
        elif self.p.vol_proxy == 'realized':
            # Calcola realized vol N-day da close history del feed
            n = self.p.vol_lookback
            try:
                if len(data) < n + 1:
                    return None
                # Estrai close history (backtrader: data.close[-i])
                closes = [float(data.close[-i]) for i in range(n + 1)]
                closes.reverse()  # cronologico
                rets = [(closes[i] / closes[i-1] - 1.0) for i in range(1, len(closes))]
                if len(rets) < 5:
                    return None
                arr = [r for r in rets if math.isfinite(r)]
                if len(arr) < 5:
                    return None
                mean = sum(arr) / len(arr)
                var = sum((r - mean) ** 2 for r in arr) / (len(arr) - 1)
                sigma = var ** 0.5
                return sigma * float(data.close[0])
            except (IndexError, ValueError):
                return None
        return None

    def _size_for(self, data) -> int:
        """Position sizing tramite PositionSizer (Fase 3.1)."""
        nav = self.broker.get_value()
        cash = self.broker.get_cash()
        price = float(data.close[0])
        vol_eur = self._vol_eur(data) if self.p.sizing_method == 'vol_target' else None
        return self._position_sizer.size(nav=nav, cash=cash, price=price, vol_eur=vol_eur)

    # ── Main loop ────────────────────────────────────────────────────────

    def next(self):
        self.bar_count += 1

        # Warmup
        if self.bar_count < self.p.warmup_bars:
            return

        # PASS 1: calcola score, gestisci EXIT, raccogli candidati BUY
        candidates = []  # (score, data, ticker, diag)
        for d in self.datas:
            tk = self._ticker(d)
            pos = self.getposition(d)
            score, diag = self._composite_score(d)

            # Aggiorna peak per trailing
            if pos.size > 0 and tk in self.entry_price:
                self.peak_price[tk] = max(self.peak_price.get(tk, 0.0), d.close[0])

            # EXIT logic (priorità)
            if pos.size > 0:
                exit_reason = self._check_exit(d, tk, score)
                if exit_reason:
                    self.close(data=d)
                    if self.p.verbose:
                        self.log(f"EXIT {tk} reason={exit_reason} composite={score:.3f}")
                    self._record_trade(tk, d, 'EXIT', score, diag, exit_reason)
                continue

            # Candidato BUY
            if pos.size == 0 and score > 0:
                # Pre-screening fundamentals (Strategia B)
                if not self._passes_quality_filter(diag):
                    self.n_filtered_by_quality += 1
                    if self.p.verbose:
                        v = diag.get('raw_scores', {}).get('value', 0.0)
                        q = diag.get('raw_scores', {}).get('quality', 0.0)
                        self.log(f"SKIP {tk} quality_filter value={v:.2f} quality={q:.2f}")
                    continue
                candidates.append((score, d, tk, diag))

        # PASS 2: ranking per score, top-N rispettando max_positions
        candidates.sort(key=lambda x: -x[0])
        slots_available = self.p.max_positions - self._open_positions_count()
        for score, d, tk, diag in candidates[:slots_available]:
            size = self._size_for(d)
            if size > 0:
                self.buy(data=d, size=size)
                self.entry_price[tk] = d.close[0]
                self.entry_bar[tk] = self.bar_count
                self.peak_price[tk] = d.close[0]
                if self.p.verbose:
                    vol_eur = self._vol_eur(d) if self.p.sizing_method == 'vol_target' else None
                    vol_str = f" vol_eur={vol_eur:.3f}" if vol_eur else ""
                    self.log(
                        f"BUY {tk} size={size} px={d.close[0]:.2f} "
                        f"notional={size * d.close[0]:.0f} composite={score:.3f}{vol_str}"
                    )
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
            f"filtered_by_quality={self.n_filtered_by_quality}  "
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
