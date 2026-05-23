# Decisione metodologica — N_eff primario per DSR

**Timestamp**: 23/05/2026 17:00 CEST
**Sigillo**: pre-calcolo DSR (Task 7). Decisione fissata adesso per evitare data snooping ex post.

## Scelta

**N_eff primario** = **trace-based** (formula `N / (1 + (N-1) · ρ̄)` su matrice di correlazione equity OOS).
**N_eff secondario** = **cluster-count** (numero di tuple distinte di IS sharpe cross-fold).

## Razionale

1. Bailey-LdP (2014) raccomandano esplicitamente trace-based come stima formale della molteplicità effettiva quando le strategie non sono indipendenti.
2. Trace-based è una funzione continua della struttura di correlazione, non soggetta a tie-break o discretizzazione.
3. Cluster-count rappresenta un **lower bound** alla molteplicità (più conservativo), utile come sensitivity bound.

## Valori attesi

Da Task 2c:
- ρ̄ mean cross-fold ≈ 0.90 → N_eff_trace per fold ≈ 1.07-1.20
- Cross-fold aggregato N_eff_trace ≈ 1.11
- Cluster-count cross-fold = 8

**Range che entrerà nella DSR**:
- Primario: SR_0 ≈ √(2 · ln(1.11)) ≈ **0.45**
- Secondario: SR_0 ≈ √(2 · ln(8)) ≈ **2.04**

Differenza dirimente (Δ SR_0 ≈ 1.6). Il paper riporterà entrambi come sensitivity analysis e dichiarerà esplicitamente che il primario è trace-based.

## Implicazione

Con SR_hat median = 2.65 e SR_0 primario = 0.45:
- DSR primario range plausibile [1.5, 1.8]

Con SR_hat median = 2.65 e SR_0 secondario = 2.04:
- DSR secondario range plausibile [0.3, 0.8]

Il vero valore del paper sarà mostrare che entrambi i numeri sono positivi e robusti alle correzioni γ1/γ2 (Task 6).

## Nota

Questa decisione viene presa **prima del calcolo finale** della DSR. Non sarà modificata retroattivamente. Eventuali aggiustamenti emersi durante Task 3-7 (es. N_eff RMT come terza misura) saranno aggiunti come sensitivity, non come sostituzione del primario.
