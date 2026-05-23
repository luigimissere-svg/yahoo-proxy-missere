# Pre-registration S1 v8 — Addendum 04

Data sigillo: 23/05/2026 — 19:30 CEST
Riferimento: pre-reg root + addendum 01, 02, 03
Scope: S1.4 — Bug 7 force-close F3, test formale bootstrap

## Sigillo procedura S1.4

File implementativo: `quant_v3/test_force_close_f3_bootstrap.py`
Sealed version: `v8.s1.4`

### Procedura

H0: SR(mc=3, F3 OOS) = SR(mc=2, F3 OOS) — il Delta osservato +1.315
    è dovuto al caso.
H1: SR(mc=3, F3 OOS) > SR(mc=2, F3 OOS) — mc=2 è overfit a F3 IS.

Test: bootstrap label permutation.
  - 20 seed indipendenti
  - 5000 permutazioni per seed
  - N trade per fold = 10 (sealed v7.4)
  - Distribuzione per-trade simulata: t-Student df=4, sigma_d=0.012,
    holding=63 bar (~3 mesi)

### Risultato sealed v7.4 backward

| Metrica | Valore |
|---|---|
| SR_obs target mc=2 | -0.110 |
| SR_obs target mc=3 | +1.205 |
| Delta_obs target | +1.315 |
| Delta_obs simulato (median 20 seed) | +1.918 |
| p_value two-sided (median) | 0.037 |
| p_value two-sided (IQR) | [0.013, 0.191] |
| p_value one-sided (median) | 0.019 |
| Verdetto (median): | REJECT_H0 |

Output sigillati:
- `quant_v3/s1_outputs/s1_4_force_close_f3_bootstrap_report.txt`
  sha256: `9116714ff7ddbe71...`
- `quant_v3/s1_outputs/s1_4_force_close_f3_bootstrap_results.json`
  sha256: `17a8cb7b03a57d9e...`

### Interpretazione e caveat onesto

1. **Verdetto formale**: con p_value median = 0.037 < 0.05, H0
   (no diff) è formalmente rifiutato a livello α=0.05.
   mc=3 OOS in F3 è sistematicamente migliore di mc=2 nella
   simulazione proxy.

2. **Incertezza**: IQR p_value = [0.013, 0.191] indica che 25%
   delle simulazioni cade nella zona INCONCLUSIVE (p > 0.05),
   alcune nell'intervallo [0.05, 0.20] di non-rifiuto debole.
   Robustezza del verdetto **media**, non forte.

3. **Test PROXY, non definitivo**:
   - Il ledger v7.4 dei trade individuali F3 OOS per mc=2 e mc=3
     non è preservato in sandbox (solo aggregati Sharpe).
   - La simulazione genera return per-trade da Sharpe target +
     assunzioni distribuzionali (t-Student df=4). Il test misura
     la significatività attesa SOTTO QUESTE ASSUNZIONI, non sul
     vero ledger.
   - Delta_obs simulato (+1.918) > Delta_obs target (+1.315): la
     simulazione amplifica la separazione → p-value reale potrebbe
     essere meno favorevole.

4. **Conseguenza per Bug 7**: il segnale di overfitting del selettore
   v7.4 (Bug 7) RIMANE confermato dal selettore v8 (S1.7 backward
   test, verdetto PASS netto +0.44 Sharpe). Il bootstrap formale
   S1.4 conferma la direzione ma con incertezza moderata.

5. **Action item per S2**: ri-eseguire S1.4 con ledger v8 reale
   (trade individuali) appena disponibile dal primo walk-forward
   v8 completo. Verdetto SOLO PROXY in S1; verdetto DEFINITIVO in S2.

### Falsificazione F3 della pre-reg

Pre-reg root: "se bootstrap force-close p-value ∈ [0.05, 0.20] →
inconclusivo, F3 input prioritario S2".

Risultato osservato: p median = 0.037 (sotto 0.05) → REJECT_H0.
Ma IQR [0.013, 0.191] sfora la soglia superiore → la regola pre-reg
viene applicata in modo CONSERVATIVO:

**Decisione operativa**: nonostante il median rifiuti H0, dato
l'IQR ampio e il caveat sulla simulazione proxy, F3 RIMANE input
prioritario per S2 (verifica con ledger v8 reale). Bug 7 PARZIALMENTE
mitigato dal selettore v8 (S1.7), in attesa di conferma S2.

## Append-only

SHA256 di questo file: (calcolato post-write)
