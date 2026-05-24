# Preregistrazione S1.5 esec 4 — cap 20 / per-ticker-cap 0.05

**Timestamp**: 2026-05-24 10:35 CEST
**Branch**: `feature/v8-s1-refactor`
**Parent commit**: `170e7b2` (diagnostica BUY pre-cap)
**Autorizzazione utente**: messaggio Luigi 24/05 10:30 CEST ("Autorizzo esec 4 con (20, 0.05) … Non serve mia ulteriore conferma prima del run")

---

## 1. Disclosure post-hoc dei parametri

I parametri `max_positions=20` e `per_ticker_cap=0.05` **non sono frutto di selezione casuale né di esplorazione pre-registrata in esec 3**. Sono derivati post-hoc dalla diagnostica `s15_diag_buy_pre_cap_report.json` (SHA `a82c8c1e2f633118db8a86214c0a3aa8c50160ddcbd3ec36b54c29ff0fe7d588`) eseguita dopo il FAIL di H1 esec 3, per rispondere alla domanda diagnostica "il cap=10 è binding e satura il ranking?".

Razionale meccanico:

- mc=2 thr=0.05 su F2 OOS produce mean 11.12 candidati pre-cap, p90 14, max 16
- 56.9% dei bar OOS eccedono il cap=10 → thr non discriminante a valle del troncamento
- (20, 0.05) raddoppia capacità e dimezza concentrazione mantenendo esposizione totale invariata (20 × 0.05 = 10 × 0.10 = 1.00 NAV). Niente leverage implicito.
- Headroom atteso: ~6 slot al p90 mc=2, 4 slot al max mc=2 → thr torna discriminante

Riconoscimento epistemico: questa è una **modifica del setup operativo**, non un fix del modello. Bug 8 (sealed `f51ed7e`) resta valido indipendentemente. H1 FAIL esec 3 è artefatto del cap (diagnostica conferma), non controesempio al meccanismo `ρ_AR(1) = f(min_concordant)`.

Il consulente ha autorizzato esplicitamente questa modifica con disclosure post-hoc esplicita in messaggio 24/05 10:30 CEST.

---

## 2. Ipotesi falsificabili (invariate da esec 3)

Le 4 ipotesi H1-H4 e le rispettive soglie sono **identiche** a `preregistration_s15_exec3_grid_ampliato.md` (SHA `a2790d3c7ee73b355314e9699c9d7e2194312e3b50d3d7f0bb6ae3a091e00ecc`). Le riporto qui per leggibilità.

### H1 — Grid non degenere

- **Statement**: la grid produce variabilità sufficiente nei risultati. La proporzione di trial degenerati (definiti come trial validi non-NaN che coincidono bit-a-bit con almeno un altro trial validato sullo stesso fold) non eccede il 25%.
- **Misura**: `pct_degenerate = n_degenerate / n_trials_valid * 100` su fold F2 OOS
- **Soglia PASS**: `pct_degenerate ≤ 25%`
- **Trial invalidi (NaN)**: contati separatamente come `n_trials_invalid_nan`, non concorrono al denominatore di H1

### H2 — ρ_AR(1) monotono crescente in mc

- **Statement**: la regressione lineare ρ_AR(1) ~ mc sui trial validi (non-NaN) ha pendenza positiva statisticamente significativa.
- **Misura**: `scipy.stats.linregress` su (mc, ρ_AR(1)) per i 24+ trial validi
- **Soglia PASS**: `slope > 0` AND `p_value < 0.10`

### H3 — Convergenza selettori sul miglior (mc, thr, msp)

- **Statement**: almeno 3 dei 4 selettori indipendenti convergono sulla stessa signature `(mc, thr, msp)`.
- **Selettori**:
  - A: argmax Sharpe BT OOS
  - B: argmax DSR
  - C: argmin |ρ_AR(1)|
  - D: argmax Sharpe BT condizionato a |ρ_AR(1)| < 0.10
- **Soglia PASS**: `n_converging ≥ 3 / 4`
- **Signature**: stringa normalizzata `"mc=X|thr=Y|msp=Z|NA"` per gestire NaN msp

### H4 — Sharpe BT OOS rispetta soglia operativa

- **Statement**: il trial selezionato da H3 ha Sharpe BT OOS ≥ 1.5
- **Misura**: `oos_sharpe_bt` dal CSV `s15_exec4_f2_results.csv` per il best param
- **Soglia PASS**: `sharpe_bt_oos ≥ 1.5`

---

## 3. Decision tree esito (autorizzato Luigi 24/05 10:30)

| Esito | Azione |
|---|---|
| PASS H1 ∧ H2 ∧ H3 ∧ H4 | Leverage analysis sblocca su parametro selezionato. Procede Step 7 originale del piano S1.5 |
| FAIL su qualsiasi H_i | Opzione (d): chiusura S1.5 accettando H1/H_i FAIL come limite noto del setup portfolio 35 ticker. Dichiarazione esplicita nel paper v8: "H1 limit on portfolio setup with 35 ticker, deferred to S3 with extended universe". **Niente (e) o (f) post-hoc inventati**. |

---

## 4. Vincoli sealed (irriducibili)

1. Universo: `portfolio` (35 ticker) — invariato da esec 3
2. Grid: `GRID_S1_5_EXEC3` (6 thr × 3 mc × 2 msp = 36 combo) — invariata
3. Walk-forward: `--is-months 12 --oos-months 3 --step-months 3` — invariato
4. Stable threshold: 3 — invariato
5. `--max-positions 20` (era 10) — **modifica unica autorizzata**
6. `--per-ticker-cap 0.05` (era 0.10) — **modifica unica autorizzata**
7. Quality filter: invariato (`--value-floor -0.5 --quality-floor -0.5`)
8. Regime mode: invariato (off)
9. Sizing: invariato (vol_target, target_risk_pct=0.01)
10. Falsification script: `s15_exec3_falsification.py` (SHA `edac44ecf…`) riusato as-is con path swap a `s15_exec4_*.csv`
11. mc=4 dichiarato a priori "non testabile su portfolio, deferred S3 con universo esteso" — l'esito numerico non lo riabilita
12. Annotazione separata richiesta dal consulente: se mc=3 con cap=20 mostra ρ_AR(1) significativamente diverso dal valore sealed v7.4 (+0.1883), apre questione separata, **NON riapertura Bug 8**

---

## 5. Comando autoritativo previsto

```bash
cd /home/user/workspace/yahoo-proxy-missere/quant_v3
python -u -m engine.wf_runner --grid s1_5_exec3 --universe portfolio \
  --output-csv s1_outputs/s15_exec4_f2_results.csv \
  --stability-json s1_outputs/s15_exec4_f2_stability.json \
  --save-equity-csv s1_outputs/s15_exec4_f2_equity.csv \
  --save-trades-csv s1_outputs/s15_exec4_f2_trades.csv \
  --is-months 12 --oos-months 3 --step-months 3 \
  --max-positions 20 --per-ticker-cap 0.05 \
  --stable-threshold 3 --verbose
```

Walltime atteso: ~30 min (3 fold × 36 combo + 3 OOS = 111 backtest cerebro su 35 feed con warmup 365 gg).

---

## 6. Output attesi

| File | Descrizione |
|---|---|
| `s15_exec4_f2_results.csv` | Tabella best param per fold + metriche IS/OOS |
| `s15_exec4_f2_stability.json` | Stability counter (atteso analogo esec 3) |
| `s15_exec4_f2_equity.csv` | Equity daily per fold × phase |
| `s15_exec4_f2_trades.csv` | Trade log per fold |
| `s15_exec4_logs/run.log` | Log completo |
| `s15_exec4_falsification.py` | Copia/riferimento allo script esec 3 (riusato) |
| `s15_exec4_falsification_report.json` | Esito 4 ipotesi |
| `s15_exec4_falsification_report.md` | Report leggibile |
| `journal_s15_exec4_chiusura.md` | Journal con verdetto |

---

## 7. Append-only e SHA256

Tutti i file output saranno append-only (no modifica retroattiva). SHA256 di ciascun file calcolato e committato nel journal di chiusura esec 4.

Questa preregistrazione viene committata **prima** del run autoritativo. SHA256 sarà calcolato al momento del commit. Eventuali addendum successivi necessari (es. chiarimento di interpretazione) saranno append-only come fatto per esec 3 (vedi addendum_01).

---

## 8. Tracciabilità ascendente

- Bug 8 SUPERATO da v8: sealed `f51ed7e`
- S1.5 esec 3 grid ampliato: preregistrazione SHA `a2790d3c7ee73b355314e9699c9d7e2194312e3b50d3d7f0bb6ae3a091e00ecc`
- S1.5 esec 3 chiusura (FAIL H1): commit `e5d29eb`
- Diagnostica BUY pre-cap: commit `170e7b2`, report SHA `a82c8c1e2f633118db8a86214c0a3aa8c50160ddcbd3ec36b54c29ff0fe7d588`
- Autorizzazione esec 4: messaggio utente 24/05 10:30 CEST (registrato nel commit message di chiusura esec 4)
