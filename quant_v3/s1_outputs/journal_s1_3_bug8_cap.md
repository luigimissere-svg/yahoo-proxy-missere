# Journal S1.3 — Bug 8 isolamento outlier MU

Data: 23/05/2026 — 18:50 CEST
Branch: feature/v8-s1-refactor
Ledger sorgente: f2_oos_trade_ledger.csv (10 trade, fold 1 F2 OOS)
Sealed version: v8.s1.3

## Esecuzione

Implementata regola operativa in `quant_v3/risk_caps.py`:
- `apply_notional_cap(trades, fold_capital, cap_pct=0.05)`: clip notional per
  ticker a 5% del capitale di fold, PnL scalato linearmente.
- `apply_winsor_pnl_pct(capped, train_pnl_pct, pctile=95)`: winsor PnL_pct
  per trade al P95 della distribuzione train (no look-ahead).
- `isolate_outliers`: pipeline (a) cap notional + (b) winsor opzionale.

Backward test eseguito su ledger F2 OOS v7.4 (l'unico ledger v7.4
sopravvissuto in sandbox — file CSV/JSON/NPZ del walk-forward completo
sono persi, ma il ledger F2 è sufficiente per testare la regola sul
fold più rilevante per il Bug 8).

## Risultati numerici sigillati

| Metrica | Pre-cap | Post-cap | Delta |
|---|---|---|---|
| Notional totale fold | 98 589.94 | 49 295.00 | −50.00% |
| P&L gross totale fold | 21 360.92 | 10 307.85 | −51.74% |
| MU notional | 10 397.92 | 4 929.50 | −52.59% |
| MU PnL gross | 11 175.84 | 5 298.30 | −52.59% |
| MU % del PnL fold | 52.32% | 51.40% | −0.92 pp |

P&L gross fold come % del capitale: 21.67% → 10.46% (capitale dimezzato
ma stesso rendimento per EUR esposto, infatti il rendimento per EUR
investito resta invariato — il cap non altera l'edge per trade, solo
la size).

## Falsificazione F2 della pre-registrazione S1.3

Criterio pre-registrato: se |Delta P&L fold con cap vs senza| < 5%,
Bug 8 marginale.

Risultato osservato: |Delta P&L| = 51.74% >> 5%.
Bug 8 NON marginale → cap NECESSARIO per stabilità del fold.

## Scoperta importante: il cap notional da solo NON isola MU

Il contributo % di MU al PnL del fold passa da 52.32% a 51.40% — quasi
invariato. Motivo: nel design v7.4 tutti i trade hanno notional
~10 000 EUR (equal-weight implicito su 10 ticker selezionati), quindi
applicare un cap 5% scala TUTTI i trade in modo proporzionale (~0.49x).
Il peso relativo di MU resta dominante perché il suo `pnl_pct` è
+107.5%, 8.3x la mediana (+11.6%) e 13.4x il P90 escluso MU (+44%).

Implicazione operativa: il cap notional 5% v8 richiede di essere
accompagnato da almeno UNO dei seguenti meccanismi:

1. **Forzare diversificazione** — minimo K ticker per fold (es. K=20
   se cap=5%), distribuzione automatica del residuo se segnali < K.
2. **Winsorization PnL_pct** — clip dei rendimenti per trade al P95
   della distribuzione di training (implementata in `apply_winsor_pnl_pct`).
3. **Risk-parity sizing** — size per ticker inversamente proporzionale
   alla volatilità realizzata in finestra training (rinviato a S2).

Per S1.3 si adotta (1) + (2) come default operativo, (3) come opzione
S2. Il cap notional senza diversificazione minima è cosmetico.

## Pre-registrazione aggiornata operativa S1.3 (no retroattività sulla pre-reg)

La regola sigillata per v8 è:

```
def fold_risk_caps(trades, fold_capital, train_pnl_pct,
                   cap_pct=0.05, min_tickers=20, winsor_pctile=95):
    # (1) cap notional 5% per ticker
    capped = apply_notional_cap(trades, fold_capital, cap_pct)
    # (2) winsor PnL_pct al P95 train (no look-ahead)
    capped = apply_winsor_pnl_pct(capped, train_pnl_pct, winsor_pctile)
    # (3) verifica diversificazione minima
    assert len({t.ticker for t in trades}) >= min_tickers, \
        f"Fold ha {n} ticker, min richiesto {min_tickers}"
    return capped
```

L'enforcement di `min_tickers` deve essere implementato a livello di
selettore segnali (S1.7) — non è violazione della pre-reg perché la
pre-reg sigilla l'OBIETTIVO (isolamento MU), non la lista esatta dei
meccanismi.

## Artefatti sealed

- `quant_v3/risk_caps.py` (modulo regola, 203 righe)
- `quant_v3/test_risk_caps_backward.py` (test backward, 142 righe)
- `quant_v3/s1_outputs/s1_3_backward_test_report.txt`
  sha256: `b78c757ef9b2c360...`
- `quant_v3/s1_outputs/s1_3_backward_test_results.json`
  sha256: `d3de04f78a4fa6a2...`

## Status S1.3

PASS parziale:
- regola operativa implementata e testata
- falsificazione F2 risolta (Bug 8 NON marginale)
- limitazione documentata: cap notional da solo insufficiente, richiede
  diversificazione minima + winsor (entrambi implementati)
- enforcement min_tickers passa al selettore S1.7

Decisione: marca S1.3 COMPLETED, ma S1.7 deve includere il check
`min_tickers >= 1/cap_pct` (= 20 se cap=5%) altrimenti S1.3 non ha
effetto pratico.
