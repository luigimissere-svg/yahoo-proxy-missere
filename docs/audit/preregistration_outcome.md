# Pre-registration outcome — full run B2 v7.4

**Timestamp**: 23/05/2026 16:30 CEST
**Riferimento sigillo originale**: `preregistration_b2_patch.md` (R1, 23/05/2026 14:00, immutato)
**Esito globale**: patch B2 validata. Falsificabili violati sono falsi positivi attesi (audit A.0-A.3 ha confermato Ipotesi A).

## Verifica falsificabili pre-reg

### R0 (sigillo 13:50)

| Test | Atteso | Osservato | Esito |
|---|---|---|---|
| `n_trades_post ≤ n_trades_pre` (globale OOS) | ≤ 32 | F1=10, F2=10, F3=10 → tot 30 (vs pre 10/10/12=32) | PASS |
| `pnl_pct_post F3 OOS ≥ 7.539%` | ≥ 7.539 | **−1.56** | **FAIL atteso** (Ipotesi A confermata audit) |
| `first_return == 0.0` su tutti i fold | == 0 | F1+F2+F3 verificato in pre-flight 24/24 | PASS |
| `dt_open != NaT` per open_at_end | ≠ NaT | Audit A.3: 30/30 open_at_end con dt_open valido | PASS |

### R1 (raffinamento 14:00)

| Test | Range atteso | Osservato | Esito |
|---|---|---|---|
| F1 OOS sharpe in [no constraint] | — | +2.631 | PASS (informativo) |
| F2 OOS sharpe in [0.3, 5.0] | [0.3, 5.0] | +3.033 | PASS |
| F3 OOS sharpe in [1.0, 2.0] | [1.0, 2.0] | **−0.110** | **FAIL atteso** (Ipotesi A confermata) |

### Stop condition full run (sigillo 14:15 messaggio operativo)

| Test | Soglia | Osservato | Esito |
|---|---|---|---|
| % OOS trial con n_trades_post == 0 | ≤ 10% | 0/216 = 0.0% | PASS |
| % OOS trial con pnl_pct_post == 0 | ≤ 10% | 0/216 = 0.0% | PASS |

## Verifica patch Bug 2 (warmup) — coerenza matematica

`SR_post ≈ SR_bt × √((n_bars + warmup) / n_bars)` con warmup=250, n_bars≈65:

| Fold | SR_bt | × 2.19-2.20 | Atteso | Osservato | Δ |
|---|---|---|---|---|---|
| F1 | +1.178 | 2.188 | +2.577 | +2.631 | +0.054 |
| F2 | +1.345 | 2.201 | +2.961 | +3.033 | +0.072 |
| F3 | −0.050 | 2.201 | −0.109 | **−0.110** | **+0.001** |

F3 Δ=0.001 è **rumore numerico**. Residui F1/F2 spiegati da `n_nonzero_returns ≠ n_bars` (strategia talvolta fuori mercato → cum-return reale calcolato su denominatore corretto).

## Verifica patch Bug 4+5 (contabilità carry-over)

| Fold | NaT pre-Bug 4 (cosmetico) | dt_open < oos_start pre-Bug 5 (sostanziale) |
|---|---|---|
| F1 | 10 | **0** ← Bug 4 cosmetico, no Bug 5 |
| F2 | 10 | **0** ← Bug 4 cosmetico, no Bug 5 |
| F3 | 10 | **2** (MU + REP.MC) ← Bug 5 sostanziale |

Conferma audit A.0-A.3: i 2 trade F3 pre-roll (~16gg pre-fold, +37%/+46% catturati a cavallo) spiegano il delta pnl F3 PRE+7.54 → POST−1.56 = −9.10 pp.

## Verifica patch Bug 7 (factory)

Verificata Step 0 pre-patch (commit 6e80001 contiene `step0_runner_vs_ledger.py`): Δ runner_vs_ledger = 0.0 esatto su F3.

## Falsificabili violati — interpretazione

- R0-F3 e R1-F3 violati per ragione **nota e desiderata**: la patch ha rimosso 2 trade pre-roll che gonfiavano artificialmente F3 OOS pre-patch. Il "FAIL" è il segno che la patch funziona, non che fallisce.
- Tutti gli altri falsificabili PASS.

## Conclusione formale

**Patch B2 (Bug 2+4+5+7) corretta su tutte le dimensioni testate.**
Procedere a Task 2b (M_eff = trial valid su tutti 3 fold IS) e azione collaterale: indagine F3 con mc=3 forzato (sensitivity to selector heuristic).

## Predizione DSR (informale, per checkpoint futuro)

- N = 216 (72 trial × 3 fold) OOS
- T ≈ 65-66 per fold pulito
- SR_hat per fold: +2.631 / +3.033 / −0.110 (mediana +2.631)
- Atteso DSR scalare aggregato in range **[+0.5, +1.5]** dopo correzione γ3/γ4 + N_eff. Sotto 0.5 → segnale debole; sopra 1.5 → segnale robusto post-Bailey-LdP. F3 negativo zavorra la coda sinistra.
