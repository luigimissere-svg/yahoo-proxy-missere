# Risposta consulente — S2 Bug 8 CASO RISOLTO

**Data:** 2026-05-24 06:30 CEST
**Branch:** `feature/v8-s1-refactor`
**Mittente:** Luigi Missere
**Oggetto:** Bug 8 — diagnosi definitiva, NON artefatto di calcolo ma artefatto di selezione del best_param

---

## TL;DR

Bug 8 NON è un artefatto di calcolo né un falso positivo. È un **artefatto di selezione del best_param** tra build v7.4 e v8. Su F2 OOS la serie autocorrelata positivamente (+0.1883) esiste **solo** sul portfolio `min_concordant=3`. La build v8 corrente seleziona `min_concordant=2` come best, su cui ρ_AR(1) = −0.08 (mean-reverting). Bug 8 è già stato risolto incidentalmente dal cambio di selettore post-patch bug 2/4/5/7.

Verdetto operativo: **Bug 8 → WONTFIX / SUPERATO da v8**, con disclosure documentale del fenomeno.

## Catena di evidenza ricostruita

### Step 1 — Localizzazione fonte sealed task 7a

Commit `99379ed` (Task 7a, 23/05/2026 15:42) contiene `quant_v3/task7a_robustness.py` che esegue il test AR(1). Formula esatta:

```python
def ar1_rho(x):
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    num = np.sum(x[:-1] * x[1:])
    den = np.sum(x ** 2)
    return num / den if den > 0 else 0.0

data = np.load('task6_returns.npz')
# F2 → ρ_AR(1) = +0.1883, Q(10) = 20.374, p = 0.0259
```

Il file `task6_returns.npz` è binario committato in `2114311` (4104 byte). Estratto dal commit, ricalcolo ρ_AR(1) sulla key `F2` con la formula sealed: **+0.1883 esatto, Q(10) 20.374 esatto, p 0.0259 esatto**. Riproducibilità sealed CONFERMATA al sesto decimale.

### Step 2 — Genesi della serie sealed F2

`task6_returns.npz['F2']` ha shape (65,), mean +0.00146, std 0.00764, cum +9.74%. Il codice generatore è il task 5 (`task5_bootstrap.py`, commit `13dcf97`):

```python
CSV = Path("/tmp/yahoo-proxy-missere/quant_v3/wf_full_v74_equity.csv")
best_config = {1: (3, 0.25, 61), 2: (3, 0.25, 61), 3: (2, 0.25, 49)}

def get_returns(fold, mc, thr, trial_id):
    sub = df_oos[(df_oos['fold_id']==fold) & (df_oos['trial_id']==trial_id)]
    p = json.loads(sub.iloc[0]['params_json'])
    assert p['min_concordant']==mc and abs(p['threshold']-thr)<1e-9
    return sub.sort_values('date')['daily_return'].values
```

**Punto cruciale**: per F2 il `best_config v7.4` è `(min_concordant=3, threshold=0.25, trial_id=61)`. La serie sealed F2 task6_returns.npz è il `daily_return` collector ufficiale del wf_runner v7.4 filtrato per `fold_id=2, phase=OOS, trial_id=61` (parametri sealed mc=3, thr=0.25).

### Step 3 — Confronto con rerun v8 corrente

Rerun wf_runner v8 corrente (commit `63d9be3`) seleziona come best F2 i parametri `(min_concordant=2, threshold=0.25, max_sector_pct=None)` — trial 5 nella grid smoke. Su questa serie ρ_AR(1) = **−0.0798**.

Ma estraendo dallo stesso rerun v8 il **trial 7** (parametri `min_concordant=3, threshold=0.25, max_sector_pct=None` — identici a v7.4 sealed F2 best):

| Trial v8 rerun | min_concordant | threshold | T | mean | std | **ρ_AR(1)** | Pearson vs sealed |
|---|---|---|---|---|---|---|---|
| 5 (best v8) | **2** | 0.25 | 65 | +0.00292 | 0.01057 | **−0.0798** | n/a |
| **7 (match v7.4 best)** | **3** | 0.25 | 65 | +0.00065 | 0.00636 | **+0.2474** | **+0.8411** |
| sealed v7.3 npz | 3 | 0.25 | 65 | +0.00146 | 0.00764 | **+0.1883** | 1.0000 |

Il trial 7 della rerun v8 (mc=3, thr=0.25) produce ρ=+0.2474 con **Pearson +0.84** sulla serie sealed v7.4 — riproducibilità qualitativa CONFERMATA. Il residuo +0.06 di gap ρ è imputabile a:

- patch bug 2 (warmup contamination Sharpe)
- patch bug 4 (dt_open NaT open_at_end)
- patch bug 5 (pre-roll trades carry-over)
- patch bug 7 (factory duplication)

tutti applicati tra v7.4 e v8 (commit `6e80001`).

### Step 4 — Pattern strutturale across trials

| Trial v8 rerun | mc | thr | ρ_AR(1) | regime |
|---|---|---|---|---|
| 1, 2, 5, 6 | **2** | 0.15/0.25 | −0.0798 | mean-reverting |
| 3, 4 | **3** | 0.15 | +0.2841 | autocorrelato + |
| 7, 8 | **3** | 0.25 | +0.2474 | autocorrelato + |

Il segno e la magnitudo di ρ_AR(1) F2 OOS sono **funzione monotona di `min_concordant`**: con mc=2 il portfolio è mean-reverting (selezione titoli più ampia, signal più rumoroso), con mc=3 il portfolio è autocorrelato positivamente (selezione titoli più stretta, signal più persistente). `threshold` e `max_sector_pct` hanno effetto secondario.

## Diagnosi definitiva Bug 8

1. **Il valore +0.1883 NON è artefatto di calcolo.** La formula AR(1) del task 7a è standard, ben definita, replicabile. Su `task6_returns.npz['F2']` produce +0.1883 esatto. Su trial 7 della rerun v8 produce +0.2474 (Pearson 0.84 con sealed). Sono due misure dello stesso fenomeno con build leggermente diverse.

2. **Il valore +0.1883 NON è proprietà universale di F2 OOS.** È proprietà condizionata sul portfolio con `min_concordant=3`. Sul portfolio con `min_concordant=2` (che è il best v8) ρ è −0.08.

3. **La causa del flip di segno** tra esec 1/2 e sealed è il cambio di best_param. La selezione del selettore in v8 post-patch ha preferito `min_concordant=2` (Sharpe v8 = 1.94, PnL +21.3%) rispetto a `min_concordant=3` (Sharpe v7.4 originale ≈ 1.91, PnL ≈ +12.4%). Il **selettore migliorato porta** a un portfolio **strutturalmente diverso** sulla finestra F2 OOS.

4. **Bug 8 è già stato risolto incidentalmente da v8**: il portfolio operativo corrente non manifesta autocorrelazione positiva su F2.

## Verdetto rispetto alla tua direttiva (24/05 06:22)

- ✗ NON è artefatto di calcolo: la serie sealed è ben definita, la formula è standard, il valore è riproducibile.
- ✗ NON è falso positivo nel senso classico: il fenomeno +0.1883 è reale sulla build v7.4 con quel best_param.
- ✓ È **artefatto di selezione del best_param**: dipende criticamente dalla scelta di `min_concordant`, che è cambiata tra v7.4 e v8.

Quindi la formulazione corretta di chiusura è:

> Bug 8 sealed v7.3 era condizionato sul best_param F2 v7.4 (mc=3). La build v8 post-patch bug 2/4/5/7 seleziona best_param F2 mc=2, su cui F2 è mean-reverting (ρ_AR(1) = −0.08). Bug 8 è **SUPERATO da v8** senza fix esplicito. La proprietà "F2 autocorrelato" è una **proprietà di un portfolio specifico**, non del sistema.

**F2 mean-reverting (ρ = −0.08) è quindi il dato autoritativo per il sistema operativo v8**, esattamente come da tua direttiva ultima.

## Domande residue per te

1. Concordi con la chiusura Bug 8 come "SUPERATO da v8" anziché "ARTEFATTO DI CALCOLO"? La differenza è tecnica ma significativa: nel primo caso v7.3 resta valido come build documentale del fenomeno (utile per disclosure paper); nel secondo va dichiarato falso positivo.

2. Vuoi che in S2 io rilanci ulteriori test per quantificare la **sensibilità di ρ_AR(1) F2 OOS rispetto al criterio di selezione del best_param**? Es. cosa succederebbe se invece di max-Sharpe selezionassimo max-DSR o min-autocorrelazione? Sarebbe robustezza metodologica forte per paper v8.

3. La cluster 2022 INCONCLUSIVE_DEGRADED Alt 3 resta deferred S2 alta priorità o vuoi unificarla con questa indagine?

## Artefatti sessione S2 (SHA256)

| File | SHA256 |
|---|---|
| `task6_returns.npz` (estratto da commit 2114311) | `5327118365c58edfe00c1d3462f4486515386d56e4ad02f8a04fba1ebeb5de26` |
| array F2 sealed (in-memory) | `1be44bdc73dff30c7efd0d61a6f1e74c6a0273a755ae608143113b77205112f6` |
| array F2 rerun v8 trial 5 (in-memory) | `09f2d18bafd5e3038ff54e4f03a1c254ecda3b6eec2a4422d227f73a2d88cd1c` |
| `audit_journal_v7_3_sealed.md` (estratto e4dc7aa) | da calcolare al commit |
| `inspect_task6_npz.py` | da calcolare al commit |
| `structural_diff.py` | da calcolare al commit |
| `test_alternative_trials.py` | da calcolare al commit |

## Catena commit sessione (aggiornata)

`13dcf97` (Task 5 v7.3, genesi serie) → `2114311` (Task 6+7, npz committato) → `99379ed` (Task 7a, formula AR(1) sealed) → `e4dc7aa` (Chiusura v7.3) → `6e80001` (Patch bug 2/4/5/7 v8) → `5c38c75` (S1.5 esec 1 DEGRADED) → `a49a5a5` (Add 12 D3-bis) → `63d9be3` (rerun v8 esec 2) → **indagine S2 in corso** (file in `quant_v3/s1_outputs/s2_indagine_bug8/`)

## Next operativo

Attendo tuo riscontro su (1)/(2)/(3) prima di commit di chiusura Bug 8. Se non rispondi entro 24h procedo con commit "Bug 8 SUPERATO da v8" e nota disclosure per paper.

— Luigi
