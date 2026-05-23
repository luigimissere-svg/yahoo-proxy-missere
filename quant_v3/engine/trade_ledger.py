"""
TradeLedger — analyzer Backtrader custom per esporre il ledger dei singoli trade.

Cattura per ogni trade chiuso:
- ticker, data apertura, data chiusura, durata barre
- prezzo medio apertura, prezzo medio chiusura
- size, valore nominale, PnL in valuta, PnL %
- commissioni totali

Output: lista di dict accessibile via analyzer.get_analysis()['trades'].

Uso tipico:
    cerebro.addanalyzer(TradeLedger, _name='ledger')
    ...
    ledger = strat.analyzers.ledger.get_analysis()
    for t in ledger['trades']:
        print(t)

Aggiunto in maggio 2026 per soddisfare l'item del consulente: "implementa
--save-trades-csv prima del rerun v8". Senza ledger, l'ipotesi di
concentrazione su few-winners di F2 non è falsificabile.
"""
from __future__ import annotations

import backtrader as bt


class TradeLedger(bt.Analyzer):
    """Cattura il ledger dei singoli trade chiusi (e snapshot di quelli aperti).

    L'analyzer raccoglie un record per ogni trade che si chiude durante il run,
    più, a fine run, uno snapshot dei trade ancora aperti (utile per WF dove
    le posizioni possono restare aperte oltre la finestra OOS).
    """

    def __init__(self):
        self._closed = []
        self._open_snapshot = []
        # Mappa trade.ref → dict con dati "vivi" all'apertura. Backtrader
        # azzera trade.size e trade.value al momento della chiusura, quindi
        # se non li catturiamo all'evento justopened li perdiamo (rimane solo
        # trade.price = prezzo medio entry, che da solo non basta a calcolare
        # il notional).
        self._open_state = {}
        # Bug 4 fix (B2 patch 23/05/2026): mappa data._name → date di apertura
        # del primo BUY ancora open. Popolata in notify_order su Completed BUY
        # quando la posizione passa da 0 → size>0. Resettata su Completed SELL
        # che porta size a 0. Garantisce dt_open valorizzato per le posizioni
        # ancora aperte a fine fold (snapshot in stop()).
        self._dt_open_by_data: dict = {}

    def notify_order(self, order):
        """Cattura dt_open per ogni posizione aperta.

        Bug 4 fix (B2 patch 23/05/2026): notify_trade arriva quando trade.justopened
        è True ma non espone in modo affidabile la data sul `trade.data`; per gli
        open_at_end l'apertura veniva persa (dt_open NaT). Usiamo notify_order su
        order.Completed: quando la posizione raggiunge size != 0 dopo un BUY, la
        data corrente del feed è dt_open.

        Resettiamo l'entry su Completed che porta la posizione a 0 (chiusura
        completa). Trade scaling (non previsto nella strategy attuale ma
        robustezza) viene gestito: se size cambia segno o passa per 0 ed esce,
        consideriamo nuova apertura.
        """
        if order.status != order.Completed:
            return
        try:
            data = order.data
            name = data._name
        except Exception:
            return
        # Posizione corrente DOPO il completamento dell'ordine.
        try:
            pos_size = float(self.strategy.broker.getposition(data).size)
        except Exception:
            return
        if pos_size == 0:
            # Chiusura completa: rimuovi dt_open cached.
            self._dt_open_by_data.pop(name, None)
            return
        # Posizione open dopo l'esecuzione. Se non avevamo ancora dt_open,
        # è una nuova apertura: salva la data corrente del feed.
        if name not in self._dt_open_by_data:
            try:
                dt_open = data.datetime.date(0)
            except Exception:
                dt_open = None
            if dt_open is not None:
                self._dt_open_by_data[name] = dt_open

    def notify_trade(self, trade):
        # Cattura lo stato all'apertura del trade. justopened è True solo
        # all'evento di apertura iniziale; lo usiamo per memorizzare size
        # e notional che verranno azzerati alla chiusura.
        if getattr(trade, 'justopened', False):
            self._open_state[trade.ref] = {
                'size_open': float(getattr(trade, 'size', 0) or 0),
                'price_open': float(getattr(trade, 'price', 0.0) or 0.0),
                'value_open': float(getattr(trade, 'value', 0.0) or 0.0),
            }

        # Tutto il resto si applica solo alla chiusura definitiva.
        if not trade.isclosed:
            return

        # Ricava ticker dalla data del trade.
        try:
            ticker = trade.data._name
        except Exception:
            ticker = "UNKNOWN"

        # Datetime di apertura/chiusura del trade.
        try:
            dt_open = bt.num2date(trade.dtopen)
            dt_close = bt.num2date(trade.dtclose)
        except Exception:
            dt_open = None
            dt_close = None

        # Recupera lo stato di apertura cached (size e notional originali).
        open_state = self._open_state.pop(trade.ref, None)
        if open_state is not None:
            size_open = open_state['size_open']
            price_open = open_state['price_open']
            # value_open di Backtrader può essere size*price (long) o negativo
            # (short). Usiamo il modulo del notional.
            value_open_raw = open_state['value_open']
            notional_open = abs(value_open_raw) if value_open_raw else abs(size_open * price_open)
        else:
            # Fallback: trade.price è il prezzo medio entry; la size originale
            # è persa, approssimiamo via pnl/price-delta se possibile.
            size_open = 0.0
            price_open = float(getattr(trade, 'price', 0.0) or 0.0)
            notional_open = 0.0

        pnl = float(getattr(trade, 'pnl', 0.0))
        pnl_comm = float(getattr(trade, 'pnlcomm', 0.0))  # PnL netto da commissioni
        commission = pnl - pnl_comm  # commissioni totali

        bars_held = int(getattr(trade, 'barlen', 0))

        # PnL % rispetto al notional di apertura.
        pnl_pct = (pnl_comm / notional_open * 100.0) if notional_open > 0 else 0.0

        self._closed.append({
            'ticker': ticker,
            'dt_open': dt_open.isoformat() if dt_open else '',
            'dt_close': dt_close.isoformat() if dt_close else '',
            'bars_held': bars_held,
            'size': float(size_open),
            'entry_price': float(price_open),
            'notional_open': round(notional_open, 2),
            'pnl_gross': round(pnl, 2),
            'pnl_net': round(pnl_comm, 2),
            'pnl_pct': round(pnl_pct, 3),
            'commission': round(commission, 2),
            'status': 'closed',
        })

    def stop(self):
        """A fine run: snapshot dei trade ancora aperti (Strategy.broker)."""
        try:
            broker = self.strategy.broker
        except Exception:
            return
        try:
            data_iter = list(self.strategy.datas)
        except Exception:
            data_iter = []

        for d in data_iter:
            pos = broker.getposition(d)
            if pos.size == 0:
                continue
            try:
                ticker = d._name
            except Exception:
                ticker = "UNKNOWN"
            try:
                # Prezzo corrente alla fine del run
                price_now = float(d.close[0])
            except Exception:
                price_now = 0.0
            notional_open = float(pos.size) * float(pos.price)
            notional_now = float(pos.size) * price_now
            pnl_unreal = notional_now - notional_open
            pnl_pct = (pnl_unreal / notional_open * 100.0) if notional_open != 0 else 0.0

            # Bug 4 fix: dt_open recuperato dalla cache notify_order; fallback ''.
            dt_open_cached = self._dt_open_by_data.get(ticker)
            dt_open_iso = dt_open_cached.isoformat() if dt_open_cached is not None else ''

            self._open_snapshot.append({
                'ticker': ticker,
                'dt_open': dt_open_iso,
                'dt_close': '',
                'bars_held': 0,
                'size': float(pos.size),
                'entry_price': float(pos.price),
                'notional_open': round(notional_open, 2),
                'pnl_gross': round(pnl_unreal, 2),
                'pnl_net': round(pnl_unreal, 2),
                'pnl_pct': round(pnl_pct, 3),
                'commission': 0.0,
                'status': 'open_at_end',
            })

    def get_analysis(self):
        return {
            'trades': self._closed + self._open_snapshot,
            'n_closed': len(self._closed),
            'n_open_at_end': len(self._open_snapshot),
        }
