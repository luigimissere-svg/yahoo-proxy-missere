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

## Sintesi N_eff IS — input per Task 5/6/7 DSR

- **N_eff primario sigillato** (trace-based, da `decisione_neff_primario.md`):
  - IS C_mean = **1.1521**
  - OOS media fold = **1.2231**
  - **Stima consolidata DSR**: N_eff ≈ **1.188** (media IS+OOS)
- **N_eff secondario** (cluster-count strategie distinte) = 8 (da Task 2c)
- **SR_0 primario** = √(2·ln(1.188)) ≈ 0.5864
- **SR_0 secondario** = √(2·ln(8)) ≈ 2.0393

## Output files

- `task4_neff_is.py` (script)
- `/home/user/workspace/task4_summary.md` (questo file)
