# Journal — S1.5 diagnostica leggera BUY pre-cap (F2 OOS)

**Timestamp**: 2026-05-24 10:30 CEST
**Branch**: `feature/v8-s1-refactor`
**Parent commit**: `e5d29eb` (S1.5 esec 3 chiusura)
**Scope**: diagnostica prevista dal decision tree §9 (a) del messaggio `messaggio_consulente_s15_exec3_chiusura.md`
**Autorizzazione utente**: messaggio Luigi del 24/05 09:53 CEST con istruzione esplicita "Procedi (a)"

---

## 1. Obiettivo

Verificare empiricamente l'ipotesi diagnostica formulata nel journal di chiusura esec 3: **la degenerazione 100% di H1 è causata da saturazione del cap `max_positions=10`**, non da limite del modello o della grid.

Test: contare i candidati BUY pre-cap a ogni bar OOS F2 per mc=2 e mc=3 a thr=0.05 (massima permissività).

---

## 2. Setup

| Parametro | Valore |
|---|---|
| Universo | portfolio (35 ticker) |
| Fold target | F2 |
| Finestra OOS | 2025-11-01 → 2026-02-01 (65 bar trading) |
| Finestra feed totale | 2023-11-01 → 2026-02-01 (warmup 365 gg + IS 12m + OOS 3m) |
| thr | 0.05 (permissività massima della grid esec 3) |
| max_positions | 10 (cap da diagnosticare) |
| per_ticker_cap | 0.10 (invariato) |
| warmup_bars | 50 (coerente con `wf_runner`) |
| regime_mode | off (coerente con grid esec 3) |
| mc list | {2, 3} |

Approccio implementativo: subclass `DiagStrategy(PatrimonioStrategy)` con override di `next()` che, prima di delegare al `super().next()`, conta i candidati replicando esattamente la logica PASS 1 (composite>0, regime not blocking, quality filter ok), escludendo posizioni già aperte. Il troncamento `max_positions` e `_apply_constraints` vengono applicati solo nel `super().next()` successivo e non influenzano il conteggio.

**Niente patch al sorgente principale**. Lo script vive in `quant_v3/s1_outputs/s15_diag_buy_pre_cap.py` come strumento diagnostico isolato.

---

## 3. Esecuzione

Run sincrono in foreground, due passaggi separati per mc=2 e mc=3 (ciascuno ~3 min walltime, 35 feed × ~575 bar totali per backtest cerebro).

Output:

| File | SHA256 |
|---|---|
| `s15_diag_buy_pre_cap.py` | `0da770b255c2952e341de4d2cab39752645263cf3548d07c0b7e30d3bce79f46` |
| `s15_diag_buy_pre_cap_report.json` (merged mc=2+mc=3) | `a82c8c1e2f633118db8a86214c0a3aa8c50160ddcbd3ec36b54c29ff0fe7d588` |
| `s15_diag_buy_pre_cap_daily.csv` (130 righe = 65 bar × 2 mc) | `7e5bd6eb47bc34c2d974801b9b2ab4d1ec69fb2a3779380e7178cac9ce4da9ed` |
| `s15_diag_buy_pre_cap.log` | `0c60e164daa27f9ad766a596ff2fc88a35312a628f7a3de70c47d4636b235107` |

---

## 4. Risultati

### mc=2

| Statistica | Valore |
|---|---|
| n bar OOS | 65 |
| mean candidati pre-cap | 11.12 |
| median | 11 |
| p25 / p75 | 10 / 12 |
| p90 | 14 |
| min / max | 7 / 16 |
| std | 2.29 |
| n bar con candidati > 10 | 37 / 65 = 56.9% |
| n bar con zero candidati | 0 / 65 = 0% |
| slots_available median (cap=10) | 0 |

### mc=3

| Statistica | Valore |
|---|---|
| n bar OOS | 65 |
| mean candidati pre-cap | 0.32 |
| median | 0 |
| p25 / p75 | 0 / 0 |
| p90 | 1 |
| min / max | 0 / 6 |
| std | 0.85 |
| n bar con candidati > 10 | 0 / 65 = 0% |
| n bar con zero candidati | 50 / 65 = 76.9% |
| slots_available median | 0 |

---

## 5. Interpretazione

### Caso 1 del decision tree (BUY mc=2 >> 10): applicabile

Saturazione strutturale confermata. Con cap=10, l'ordinamento dei top-10 candidati per composite score è dominato dal segno e magnitudine del composite (continuo) e non dal thr. I 6-14 candidati marginali oltre il cap sono filtrati a valle del thr, non da esso: thr varia da 0.05 a 0.30 senza riordinare nulla perché tutti i top-10 hanno score molto superiore a 0.30. Saturazione completa nei 37/65 giorni in cui i candidati eccedono il cap; nei rimanenti 28 giorni i candidati restano comunque 7-10 con `slots_available` quasi sempre 0 (portafoglio mantenuto pieno per inerzia delle posizioni aperte).

### Conferma indipendente teoria Bug 8 (mc=3)

Pattern opposto e coerente. mc=3 elimina la maggior parte dei segnali a monte tramite `min_concordant`. 76.9% dei giorni a zero candidati: in queste giornate nessun ticker raggiunge 3 moduli concordi. Il raro candidato che emerge (max 6 a singolo giorno, p90=1) entra nel portafoglio appena uno slot si libera. mc=3 non è limitato dal cap ma dal flusso scarso di segnali. Coerente con il modello sealed di Bug 8: ρ_AR(1) cresce monotono in `min_concordant` perché la selettività maggiore produce ritorni più persistenti.

---

## 6. Decisione operativa

Procedo opzione (b) del decision tree esec 3:

- `--max-positions 20 --per-ticker-cap 0.05`
- Stessa grid `s1_5_exec3` (6 × 3 × 2 = 36 combo)
- Stesso universo portfolio
- Stesse 4 ipotesi falsificabili H1-H4, stesse soglie

Razionale matematico: esposizione totale invariata (20 × 0.05 = 10 × 0.10 = 1.00 NAV). Niente leverage implicito. Headroom rispetto a candidati pre-cap mc=2: ~6 slot al p90 (14), 4 slot al max (16). Thr torna discriminante perché candidati marginali entrano nel ranking sopra il cap originale e possono essere filtrati dal thr.

Atteso per mc=3: impatto modesto (la grid resta sparsa, il vincolo non era saturazione segnale ma scarsità). Annotazione del consulente Luigi nel messaggio 24/05 10:30 CEST: tracciare in journal esec 4 eventuale ρ_AR(1) mc=3 diverso da +0.1883 sealed v7.4 come questione separata, **NON riaprire Bug 8**.

Atteso per mc=4: invalido strutturalmente (35 ticker insufficienti per richiedere 4 moduli concordi su universo portfolio). Dichiarazione esplicita "non testabile, deferred S3 con universo esteso" indipendentemente dall'esito numerico esec 4.

---

## 7. Vincoli sealed per esec 4

Da preservare nella preregistrazione e nel run:

1. Disclosure esplicita: parametri (20, 0.05) sono **post-hoc** derivati dalla diagnostica `s15_diag_buy_pre_cap_report.json` SHA `a82c8c1e…`. Non confondere con cherry-picking: la diagnostica è strumento di interpretazione del FAIL esec 3, non selezione di parametri vincenti.
2. Niente modifica allo script di falsificazione `s15_exec3_falsification.py` (fix NaN-aware già applicato). Riutilizzo as-is per esec 4.
3. Niente modifica al quality filter (soglie value/quality invariate).
4. Niente modifica alla grid (6 thr × 3 mc × 2 msp = 36 combo invariati).
5. Stesse soglie H1-H4 (degenerazione ≤25%, slope ρ~mc p<0.10, convergenza ≥3/4 selettori, Sharpe BT ≥ 1.5).
6. Decision tree esito esec 4 (autorizzato Luigi 24/05 10:30):
   - PASS H1+H2+H3+H4 → leverage analysis sblocca
   - FAIL → opzione (d) chiusura S1.5; **niente** (e) o (f) inventati post-hoc; dichiarazione nel paper v8: "H1 limit on portfolio setup with 35 ticker, deferred to S3 with extended universe"

---

## 8. Sigillo Bug 8 — invariato

`f51ed7e` (Bug 8 SUPERATO da v8) resta valido. La diagnostica conferma:

- H1 FAIL esec 3 è artefatto del cap troppo basso, non controesempio al modello
- H2 (slope ρ~mc +0.333, p=5.4e-24) conferma teoria sealed in modo indipendente
- mc=3 con 76.9% zero candidati è coerente con il meccanismo ρ_AR(1) = f(mc) monotono crescente

---

## 9. Prossimi step

1. Commit + push diagnostica (file `s15_diag_buy_pre_cap.{py,json,csv,log}` + questo journal).
2. Preregistrazione `preregistration_s15_exec4_cap_20_005.md` con disclosure post-hoc.
3. Commit + push preregistrazione.
4. Run autoritativo `wf_runner --grid s1_5_exec3 --universe portfolio --max-positions 20 --per-ticker-cap 0.05` (~30 min walltime).
5. Falsificazione H1-H4.
6. Journal chiusura esec 4 + commit.
7. Messaggio consulente con verdetto finale esec 4.

Autorizzazione Luigi 24/05 10:30 CEST: "Non serve mia ulteriore conferma prima del run. Riferisci a esito."
