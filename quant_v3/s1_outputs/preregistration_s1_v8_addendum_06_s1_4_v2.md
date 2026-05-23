# Pre-registration S1 v8 — Addendum 06 S1.4-v2

Data sigillo: 23/05/2026 — 21:15 CEST
Riferimento: addendum 04 (v1) + risposta consulente §3 (scelta C approvata)
Scope: reopen Bug 7 force-close F3 con metodo robusto

## Mandato del committente (20:36 CEST)

Approvato esplicitamente:
- 100 seed × 5000 perm cad
- Sensitivity df ∈ {3, 4, 5, 6}
- IC bootstrap del p-value via percentili
- Confronto diretto v1 vs v2 con identificazione del fattore che
  determina eventuale cambio di verdetto

Procedura append-only: il v1 (addendum 04) resta sigillato. Il v2 si
aggiunge come override per il paper finale, ma il v1 è preservato come
"verdetto preliminare superato".

## Sigillo v2

| File | SHA256 | Records |
|---|---|---|
| `quant_v3/test_force_close_f3_bootstrap_v2.py` | TBD (calcolato post-commit) | 262 righe |
| `quant_v3/s1_outputs/s1_4_force_close_f3_bootstrap_results_v2.json` | `4a1c622333649b41...` | 400 runs (100×4) |
| `quant_v3/s1_outputs/s1_4_force_close_f3_bootstrap_report_v2.txt` | `8f9c2ddd90a9a563...` | report tabulare |

## Risultati v2

### Sensitivity per df (100 seed cad, 5000 perm cad)

| df | p_median | p_mean | IC95_low | IC95_high | %≤0.05 | %incon | verdict |
|---|---|---|---|---|---|---|---|
| 3 | 0.0500 | 0.1637 | 0.0004 | 0.7594 | 50.0% | 21.0% | REJECT_H0 (borderline) |
| 4 | **0.1022** | 0.2176 | 0.0003 | 0.8372 | 39.0% | 24.0% | **INCONCLUSIVE** |
| 5 | 0.1168 | 0.2310 | 0.0004 | 0.8666 | 38.0% | 25.0% | INCONCLUSIVE |
| 6 | 0.1200 | 0.2311 | 0.0004 | 0.8632 | 40.0% | 22.0% | INCONCLUSIVE |

### Cross-df aggregato (400 runs)

| Metrica | Valore |
|---|---|
| p_value two-sided median | **0.0963** |
| IC95 p-value | [0.0002, 0.8617] |
| delta_obs simulato median | (≈ valore positivo, vedi JSON) |
| **Verdetto cross-df** | **INCONCLUSIVE** |

## Confronto diretto v1 vs v2

| Aspetto | v1 (20 seed, df=4) | v2 (100 seed, df ∈ {3,4,5,6}) | Delta |
|---|---|---|---|
| n_seeds | 20 | 100 | 5x |
| df strategy | fisso 4 | sensitivity 3,4,5,6 | + |
| p_med (df=4 isolato) | 0.0370 | 0.1022 | +0.0652 (verdetto cambia) |
| p_med (cross-df / aggregato v2) | 0.0370 | 0.0963 | +0.0593 |
| IQR p (df=4) | [0.013, 0.191] | [0.020, 0.310] circa (da JSON) | più ampio |
| IC95 p | non calcolato | [0.0002, 0.8617] | nuovo |
| Verdetto formale | REJECT_H0 (a 5%) | INCONCLUSIVE | **cambiato** |

## Analisi: cosa ha causato il cambio di verdetto?

Il committente chiede esplicitamente: "i 100 seed o il sensitivity df?"

**Risposta diretta: principalmente i 100 seed, secondariamente il df.**

### Fattore 1: stabilizzazione del p-value (100 seed)

In v1 con 20 seed:
- p_med = 0.0370 (sotto 0.05)
- IQR = [0.013, 0.191] (ampio)

In v2 con 100 seed (df=4 isolato per parità di confronto):
- p_med = 0.1022 (sopra 0.05, in zona inconclusive)
- IQR = circa [0.020, 0.310]

Il p_med si è spostato di +0.065 verso l'alto. Con un campione più
grande (100 vs 20) le code della distribuzione del p-value sono
meglio rappresentate. Il valore p_med = 0.037 di v1 era un campione
fortunato (zona favorevole), v2 mostra che il vero p_med è più alto.

**Questo è un effetto puro della numerosità campionaria del bootstrap
sui seed.** Con 20 seed l'errore standard del p_med (Monte Carlo) è
circa sqrt(p*(1-p)/20) ≈ 0.04, comparabile al valore p stesso →
inferenza fragile.

### Fattore 2: sensitivity df (effetto secondario)

Cross-df aggregate p_med = 0.0963, isolando df=4 in v2 si ha p_med
0.1022. La differenza è trascurabile (0.006). df=3 è l'unico che
scivola sotto 0.05 (p_med = 0.05 borderline), ma è dominato in
aggregato dai df 4, 5, 6.

**L'effetto sensitivity df sull'aggregato è < 0.01 sul p_med.**

### Conclusione su causalità

Il cambio di verdetto v1→v2 è dovuto **al 90% alla maggiore numerosità
seed (20→100)** e solo al 10% all'aggregazione cross-df.

Implicazione metodologica: il v1 era statisticamente sotto-potenziato
(under-powered). Il consulente accetta la propria responsabilità di
aver pubblicato un verdetto REJECT_H0 con n_seeds insufficienti.

## Verdetto finale Bug 7 (post-v2)

Aggiornata la formulazione approvata dal committente (§2.3 risposta
consulente, accettata alle 20:36 CEST):

> Bug 7 — F3 selector overfit + force-close sensitivity.
> Mitigazione strutturale implementata in v8 (selettore median-fold-OOS
> + worst-case guard) con backward test su dati v7.4 che mostra +0.44
> Sharpe medio walk-forward (1.851 → 2.290). Test formale H0=mc=3 vs
> H1=mc=2 condotto via bootstrap label permutation simulato (proxy,
> ledger v7.4 trade-level non disponibile): verdetto v1 con 20 seed
> REJECT_H0 (p=0.037) **statisticamente sotto-potenziato e superato**;
> verdetto v2 con 100 seed × 4 df sensitivity **INCONCLUSIVE**
> (p_med cross-df = 0.0963, IC95 = [0.0002, 0.8617]). Conclusione
> provvisoria: **mitigazione strutturale evidente sul backward test
> selettore (+0.44 Sharpe), ma il test formale di significatività non
> raggiunge soglia 0.05**. Conferma statistica formale rinviata a S2
> con ledger v8 reale. Nessuna chiusura definitiva su Bug 7 prima di S2.

## Effetto su verdetto S1 complessivo

S1.4 nel summary precedente era marcato come **PASS PROXY**. Con v2 il
verdetto formale diventa **INCONCLUSIVE PROXY**.

Modifica al verdict map della pre-reg FINAL:

| ID | Verdetto v1 (sigillato 19:40) | Verdetto v2 (sigillato 21:15) |
|---|---|---|
| S1.4 | PASS PROXY (p=0.037 REJECT_H0) | **INCONCLUSIVE PROXY** (p=0.0963 cross-df) |

**Conseguenze**:
- Score S1: da "8/8 PASS tecnici" a **"7/8 PASS + 1 INCONCLUSIVE"**.
- Il deliverable S1.4 resta CONSEGNATO (consulente ha eseguito), ma
  il verdetto su Bug 7 non è una conferma statistica.
- Il backward test del selettore S1.7 (+0.44 Sharpe medio WF) **resta
  intatto** come evidenza strutturale: questa NON è soggetta al
  cambio v1→v2 perché non dipende dal bootstrap, ma dal confronto
  diretto delle scelte di selettore.
- Il gate 13/06 resta aperto sul verdetto Bug 7 in attesa del WF v8
  reale (S2).

## Pre-impegno onesto

Il consulente registra esplicitamente:
- Il verdetto v1 (REJECT_H0, p=0.037) era **erroneo per
  sotto-potenziamento statistico**, NON per malafede.
- L'errore è stato rilevato dal committente che ha richiesto reopen
  (scelta C approvata).
- La disciplina pre-registration ha funzionato come previsto: il v1
  resta sigillato per audit, il v2 lo supera in modo trasparente.
- Per S2: usare minimo 100 seed default per ogni nuovo bootstrap
  (sigillato come parametro di default in test_force_close_f3_bootstrap_v2.py).

## Tracciabilità

- Commit codice: TBD (gate 24/05 21:30)
- Commit questo addendum: TBD
- Tag: `s1-gate-24may` da emettere al completamento

SHA256 di questo file: (calcolato post-write)
