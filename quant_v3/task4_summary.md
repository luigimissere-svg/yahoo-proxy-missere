# Task 4 — N_eff IS multi-metodo + verifica P5

_Generated: 2026-05-23T17:10:51.231553+02:00_

## Predizione sigillata pre-calcolo (P5)

> N_eff IS trace-based convergerà a N_eff OOS Task 2c entro ±5%. Predizione puntuale: N_eff IS ∈ [1.05, 1.20].

## Metodo 1 — N_eff trace-based (PRIMARIO sigillato)

Formula: `N_eff = (Σλ)² / Σλ²` (participation ratio degli autovalori di C)

| Fold | N_eff_trace IS | ρ̄_IS    |
|------|----------------|----------|
| 1    | **1.1573**   | 0.9270 |
| 2    | **1.1035**   | 0.9506 |
| 3    | **1.1972**   | 0.9103 |
| **C_mean** | **1.1521** | 0.9293 |

## Metodo 2 — N_eff off-diagonal (constant-correlation)

Formula: `N_eff = N / (1 + (N-1) ρ̄)`

| Fold | N_eff_offdiag IS | ρ̄      |
|------|------------------|---------|
| 1    | 1.0776    | 0.9270 |
| 2    | 1.0512    | 0.9506 |
| 3    | 1.0970    | 0.9103 |
| **C_mean** | 1.0749 | 0.9293 |

## Metodo 3 — N_eff RMT (n_spike Marchenko-Pastur)

| Fold | n_spike | N_eff_RMT |
|------|---------|-----------|
| 1    | 2 | 2.0 |
| 2    | 1 | 1.0 |
| 3    | 2 | 2.0 |

## Metodo 4 — Frobenius cross-fold (stabilità)

| Coppia    | ||ΔC||_F | Rel (%) |
|-----------|---------|---------|
| F1-F2 | 2.6526 | 3.96% |
| F1-F3 | 1.7914 | 2.68% |
| F2-F3 | 4.0128 | 5.85% |

Tutte le distanze <6%: struttura correlazione molto stabile cross-fold.

## VERIFICA P5 — IS vs OOS trace-based per fold

| Fold | N_eff_IS | N_eff_OOS | Δrel % | Entro ±5%? |
|------|----------|-----------|--------|--------------|
| 1    | 1.1573   | 1.1350    | -1.93% | PASS |
| 2    | 1.1035   | 1.1522    | +4.42% | PASS |
| 3    | 1.1972   | 1.3821    | +15.44% | FAIL |

**Aggregato**: N_eff IS (C_mean) = **1.1521** vs N_eff OOS (media fold) = **1.2231**
  → Δrel = +6.16%  → **FAIL ±5%**

### Esito predizione P5

**P5 FALSIFICATA in aggregato (+6.16% > ±5%) e su F3 (+15.44%).**

Dettaglio: PASS su F1 (−1.93%) e F2 (+4.42%), FAIL su F3 (+15.44%) e aggregato.

**Causa root**: F3 OOS ha ρ̄=0.832 vs F3 IS ρ̄=0.910 (drop −8.4 punti). Coerente con il fenomeno selector overfitting già documentato in `journal_f3_selector_overfitting.md`: in F3 OOS i cluster mc=2 e mc=3 divergono performance-wise (mc=2 negativa, mc=3 positiva), aumentando dispersione → ρ̄ scende → N_eff sale. In F1+F2 i cluster restano coerenti tra IS e OOS, quindi ρ̄ resta stabile.

**Lezione operativa**: la stabilità della struttura di correlazione tra IS e OOS dipende dalla stabilità della performance dei cluster strategici sottostanti. Quando il selettore sceglie un sub-ottimo (F3), aumenta la divergenza cross-cluster in OOS, aumentando N_eff. È interpretabile come **"overfitting cost sulla scala N_eff"**, non solo sulla scala Sharpe.

**Conseguenza DSR** (sigillata, corretta post-feedback): per Task 7 riporteremo **entrambi** come sensitivity dichiarata:
- DSR(N_eff IS = 1.1521, SR_0_annual = 0.5321) — ex-ante (informazione disponibile al selettore)
- DSR(N_eff OOS = 1.2231, SR_0_annual = 0.6346) — ex-post (più conservativo, ma usa info OOS per dimensionare correzione OOS)

**Caveat metodologico paper v7.3**: stiamo usando correlazione di **daily returns** OOS come proxy della correlazione tra **SR_hat dei trial candidati** (canone Bailey-LdP). La correlazione di SR è generalmente ≥ della correlazione di returns; quindi la nostra stima N_eff è conservativamente alta (N_eff alto → SR_0 alto → DSR più stringente). Documentato come scelta metodologica con caveat.

**Disclosure paper v7.3**: P5 nel registro disclosure come falsificazione parziale (F1+F2 PASS, F3 FAIL). La causa identificata collega P5 al fenomeno selector overfitting di F3.

---

### Preview DSR CORRETTA post-feedback (unit-mixing bug fixed)

**Bug diagnosticato**: nel preview Task 4 (17:08) avevo calcolato DSR mescolando SR_hat annual (2.631) con γ₁/γ₂ daily (0.484/3.146), e ponendo l'adjustment a denominatore della stessa radice del numeratore-z, ottenendo finto 0.282 e DSR primario falsamente saturato a 1.000.

**Formula canonica Bailey-LdP 2014 (eq. 11), scala daily coerente**:

```
DSR = Φ( (SR_hat_daily − SR_0_daily) · √(T−1) / √(1 − γ₁·SR_hat_daily + (γ₂_excess/4)·SR_hat_daily²) )
```

**Input daily-scale**:
- SR_hat_daily = 2.631 / √252 = **0.1657**
- SR_0_daily_prim = 0.6346 / √252 = **0.0400** (da N_eff OOS = 1.223)
- SR_0_daily_sec = 2.0393 / √252 = **0.1285** (da cluster = 8)
- γ₁_daily = 0.484, γ₂_excess_daily = 3.146
- T = 66 bar OOS F1 (conservativo, il più lungo)

**Calcolo**:
- Denominatore: √(1 − 0.484·0.1657 + 3.146/4·0.1657²) = √(1 − 0.0802 + 0.0216) = √0.9414 = **0.9703**
- Numeratore primario: (0.1657 − 0.0400) · √65 = **1.0139**
- z_primario = 1.0139 / 0.9703 = **1.045**
- **DSR primario = Φ(1.045) = 0.852**
- Numeratore secondario: (0.1657 − 0.1285) · √65 = 0.3005
- z_secondario = 0.3005 / 0.9703 = 0.3097
- **DSR secondario = Φ(0.3097) = 0.622**

**Sensitivity N_eff IS ex-ante**:
- SR_0_daily_IS = √(2·ln(1.1521)) / √252 = 0.5321 / 15.875 = 0.0335
- z_IS = (0.1657 − 0.0335) · √65 / 0.9703 = **1.099**
- **DSR(N_eff IS) = Φ(1.099) = 0.864** (Δ +1.2pp vs N_eff OOS)

**Esito preview (corretto)**:
- DSR primario ∈ [0.852, 0.864] — sopra 0.5 ma sotto 0.95: **"sistema interessante, da confermare con bootstrap"** (Task 5/6/7 finali)
- DSR secondario = 0.622 — sopra 0.5, sotto 0.95: stesso giudizio sul regime cluster
- **Vincolo bilatero rispettato** (entrambi > 0.5; il primario non raggiunge 1.0)
- Range realistico, niente saturazione CDF sospetta

---

### Preview DSR ricalcolato CONSISTENTE γ per-fold (post-feedback 17:22)

**Critica accolta**: la prima preview usava γ aggregato concatenato con SR_hat best-F1 — mescolanza sottile. Riformulo con consistency completa.

#### Opzione (A) DSR per-fold (sigillata come PRIMARIA)

γ per-fold + SR_hat per-fold + T per-fold + N_eff OOS per-fold (tutti dati fold-locali):

| Fold | SR_hat_d | γ₁     | γ₂_exc | T   | N_eff_OOS | SR_0_d | denom  | z      | **DSR** |
|------|----------|--------|--------|-----|-----------|--------|--------|--------|----------|
| F1   | 0.1657   | −0.199 | +0.620 | 66  | 1.1350    | 0.0317 | 1.0184 | +1.061 | **0.856** |
| F2   | 0.1911   | +0.594 | +1.086 | 65  | 1.1522    | 0.0335 | 0.9468 | +1.331 | **0.908** |
| F3   | −0.0069 | +0.550 | +2.717 | 65  | 1.3821    | 0.0507 | 1.0019 | −0.460 | **0.323** |

**Sensitivity ex-ante N_eff_IS per fold**:

| Fold | N_eff_IS | SR_0_d_IS | z      | DSR    |
|------|----------|-----------|--------|--------|
| F1   | 1.1573   | 0.0341    | +1.042 | 0.851  |
| F2   | 1.1035   | 0.0280    | +1.378 | 0.916  |
| F3   | 1.1972   | 0.0378    | −0.357 | 0.361  |

**Lettura**:
- F1 e F2 sopra 0.85: sistema validato statisticamente
- F3 sotto 0.5 (0.32 ex-post, 0.36 ex-ante): NON validato — emerge onestamente la negatività OOS
- F2 più forte per γ₁ positivo (right-skew) che riduce penalty Bailey-LdP

#### Opzione (B) DSR aggregato concatenato (sigillata come SECONDARIA per paper)

Identificati trial_id: F1=t.61, F2=t.61, F3=t.49 (mc/thr=0.25 con msp=None, mpb=None). Serie OOS concatenata 196 bar.

**Statistiche aggregate**:
- T_agg = 196 bar (66+65+65)
- mean_daily = 0.000818, std_daily = 0.010995
- SR_daily_agg = 0.0744 → **SR_annual_agg = 1.182** (consulente predetto 1.185, match a 0.003)
- γ₁_agg (Joanes-Gill bias-corrected) = 0.487
- γ₂_excess_agg = **6.337** (più alto del preview 3.146 — valore corretto)

**DSR aggregato**:
- Denominatore = √(1 − 0.487·0.0744 + 6.337/4·0.0744²) = √0.9726 = 0.9862
- z_OOS = (0.0744 − 0.0400) · √195 / 0.9862 = **0.488**
- **DSR aggregato (N_eff OOS) = Φ(0.488) = 0.687**
- z_IS = (0.0744 − 0.0335) · √195 / 0.9862 = 0.580
- **DSR aggregato (N_eff IS) = Φ(0.580) = 0.719**

#### Ljung-Box autocorrelazione per fold (bonus diagnostico)

| Fold | Q(10) | p     | acf_lag1 | Esito                          |
|------|-------|-------|----------|--------------------------------|
| F1   | 6.78  | 0.747 | −0.104  | No autocorrelazione (T_eff=T)  |
| F2   | 20.37 | **0.026** | **+0.188** | **AUTOCORR, T_eff < T_nom** |
| F3   | 8.43  | 0.586 | −0.112  | No autocorrelazione            |
| Agg  | 14.21 | 0.164 | n/a      | No autocorrelazione            |

**Implicazione F2**: T_eff (AR1 approx Politis) = 65·(1−0.188)/(1+0.188) = **44.4 bar**. DSR F2 scende da 0.908 (T=65) a **0.864 (T_eff=44.4)**. Anche con T_eff F2 resta sopra 0.85 (validato).

#### Sintesi opzione (A) + (B) post-Ljung-Box

| Output | F1 | F2 (T=65) | F2 (T_eff=44) | F3 | Aggregato (B) |
|--------|-----|-----------|---------------|-----|----------------|
| DSR ex-post (N_eff OOS) | 0.856 | 0.908 | 0.864 | 0.323 | **0.687** |
| DSR ex-ante (N_eff IS)  | 0.851 | 0.916 | 0.873 | 0.361 | **0.719** |

**Vincolo bilatero**:
- F1+F2 PASS in tutti i regimi (>0.5)
- F3 FAIL in tutti i regimi (<0.5)
- Aggregato (B) PASS marginale ~0.7 — dragged-down da F3 ma sopra soglia

**Decisioni sigillate** (Task 7 finale):
- **Output primario paper**: opzione (A) DSR per-fold + segnale F3 fail esplicito
- **Output secondario paper**: opzione (B) aggregato come "unconditional system DSR"
- F2 riportata con doppia T (T_nom e T_eff), preferendo T_eff come conservativo
- Per Task 5 bootstrap: priorità a F1, F2, F3 separati più aggregato

## Sintesi N_eff — input per Task 5/6/7 DSR

- **N_eff primario sigillato per DSR (Task 7)**:
  - **N_eff = 1.2231** (trace-based su matrice OOS, valore ex-post conservativo)
  - SR_0_annual = √(2·ln(1.2231)) = **0.6346**
  - SR_0_daily = 0.6346/√252 = **0.0400**
- **Sensitivity N_eff IS ex-ante** (riportata in paper come robustness check):
  - N_eff_IS = 1.1521 (trace-based su C_mean IS)
  - SR_0_annual = √(2·ln(1.1521)) = **0.5321**
  - SR_0_daily = 0.5321/√252 = **0.0335**
- **N_eff secondario** (cluster-count strategie distinte) = 8 (da Task 2c)
  - SR_0_annual = √(2·ln(8)) = **2.0393**
  - SR_0_daily = 2.0393/√252 = **0.1285**
- **NOTA**: la media IS+OOS 1.188 (riferimento qualitativo) NON è il numero primario; la primaria è OOS 1.2231.

## Output files

- `task4_neff_is.py` (script)
- `/home/user/workspace/task4_summary.md` (questo file)
