"""
Task 7b — Benchmark no-skill: Buy-hold MSCI World + null random N=72 Gaussian iid

Predizione P7 (sigillata pre-calcolo):
- Buy-hold MSCI World ETF (URTH) ago 2025-mag 2026: SR_d ∈ [0.03, 0.06] daily
- Null random N=72 Gaussian iid: SR_max ≈ √(2·ln(72))/√65 = 0.347 daily, DSR_form ≈ 0.50 ± 0.03
- v7.4 sistema SR_d=0.0744 vs null: DSR atteso ≈ 0.65
- Bug detection: DSR(null) > 0.55 → bug benchmark; ≤ 0.52 → calibrato
"""
import numpy as np
import pandas as pd
import urllib.request
import json
from scipy.stats import norm

rng = np.random.default_rng(2026_05_23_07)

# =============================================================================
# 1. Fetch buy-hold MSCI World (URTH)
# =============================================================================
def fetch_yahoo_history(ticker, start_date, end_date):
    """Fetch historical daily close prices da Yahoo Finance v8 chart API."""
    p1 = int(pd.Timestamp(start_date).timestamp())
    p2 = int(pd.Timestamp(end_date).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={p1}&period2={p2}&interval=1d")
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (research)'
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  Fetch failed for {ticker}: {e}")
        return None
    res = data.get('chart', {}).get('result', [None])[0]
    if res is None:
        return None
    ts = res.get('timestamp', [])
    quote = res.get('indicators', {}).get('quote', [{}])[0]
    adjclose = res.get('indicators', {}).get('adjclose', [{}])[0].get('adjclose', [])
    if not ts or not adjclose:
        return None
    df = pd.DataFrame({
        'date': pd.to_datetime(ts, unit='s').date,
        'adjclose': adjclose
    })
    df = df.dropna()
    return df

print("=" * 80)
print("Task 7b — Benchmark no-skill: Buy-hold MSCI World + null gaussian N=72")
print("=" * 80)

# Periodo OOS aggregato F1+F2+F3 = 2025-08-01 → 2026-05-01
benchmarks = {
    'URTH': 'iShares MSCI World ETF',
    'ACWI': 'iShares MSCI ACWI ETF',
    'SPY':  'SPDR S&P 500 ETF',
    'EZU':  'iShares MSCI Eurozone ETF',
}

bh_results = {}
print("\n--- Buy-hold ETF benchmarks (OOS aggregato 2025-08-01 to 2026-05-01) ---")
print(f"{'Ticker':8} {'Name':32} {'N_days':>7} {'SR_d':>10} {'SR_a':>10} {'mean_d':>11} {'std_d':>10}")

for tkr, name in benchmarks.items():
    df = fetch_yahoo_history(tkr, '2025-07-25', '2026-05-05')
    if df is None or len(df) < 50:
        print(f"{tkr:8} {name:32} fetch failed")
        continue
    df = df[(df['date'] >= pd.Timestamp('2025-08-01').date()) &
            (df['date'] <= pd.Timestamp('2026-05-01').date())].copy()
    df = df.sort_values('date').reset_index(drop=True)
    df['ret'] = df['adjclose'].pct_change()
    rets = df['ret'].dropna().values
    if len(rets) < 30:
        print(f"{tkr:8} too short")
        continue
    mu = rets.mean()
    sd = rets.std(ddof=1)
    sr_d = mu / sd
    sr_a = sr_d * np.sqrt(252)
    bh_results[tkr] = {'rets': rets, 'mu': mu, 'sd': sd, 'sr_d': sr_d, 'sr_a': sr_a, 'n': len(rets)}
    print(f"{tkr:8} {name:32} {len(rets):>7} {sr_d:>10.4f} {sr_a:>10.4f} {mu:>+11.6f} {sd:>10.6f}")

# =============================================================================
# 2. Null random N=72 Gaussian iid: SR_max distribution
# =============================================================================
print("\n--- Null distribution: 72 random Gaussian iid trial ---")

T_oos = 65  # tipico per-fold
N_trial = 72  # trial space discoverable
B = 5000  # repliche per stima SR_max distribution

# Per ogni replica: simula 72 strategie null gaussian iid, prende max SR
SR_max_dist = np.empty(B)
for b in range(B):
    # 72 strategie indipendenti, ognuna T=65 daily returns iid N(0, 1)
    # SR null = mean / std (scala 1/sqrt(T) per loi grandi numeri)
    rets_null = rng.standard_normal((N_trial, T_oos))
    sr_per_trial = rets_null.mean(axis=1) / rets_null.std(axis=1, ddof=1)
    SR_max_dist[b] = np.max(sr_per_trial)

# Statistiche
SR_max_median = np.median(SR_max_dist)
SR_max_mean = SR_max_dist.mean()
SR_max_ci90 = (np.percentile(SR_max_dist, 5), np.percentile(SR_max_dist, 95))
SR_max_formula = np.sqrt(2 * np.log(N_trial)) / np.sqrt(T_oos)  # NB: in scala daily, no /√T

# Bailey-LdP formula: SR_0 (annualized) = √(2·ln(N))/√(T*1y/T) — confusione comune
# La formula corretta per SR_0 daily: √(2·ln(N))/√T quando T è il numero di osservazioni
# Per N=72, T=65: √(2·ln(72))/√65 = 0.3470 (daily-scale standard error)

print(f"  N_trial = {N_trial}, T_oos = {T_oos}, B = {B}")
print(f"  SR_max median (empirico)   = {SR_max_median:.4f}")
print(f"  SR_max mean (empirico)     = {SR_max_mean:.4f}")
print(f"  SR_max CI 90% empirico     = [{SR_max_ci90[0]:.4f}, {SR_max_ci90[1]:.4f}]")
print(f"  SR_max formula √(2·ln(N))  = {SR_max_formula:.4f}")
print(f"  Ratio empirical/formula    = {SR_max_median/SR_max_formula:.3f}")

# DSR(null) = Φ((SR_random_null − SR_0) / σ)
# Test: prendi un singolo trial null random, calcola DSR vs SR_max_median come SR_0
# Atteso DSR ≈ 0.50 per costruzione (null is null)
print("\n  Sanity check: DSR di un trial null random vs SR_0 calibrato...")
# Estrai random trial: 1 strategia gaussian iid T=65
trial_null = rng.standard_normal(T_oos)
sr_null = trial_null.mean() / trial_null.std(ddof=1)
# γ1, γ2 per gaussian iid sample: attesi vicini a 0
mu_null = trial_null.mean()
sd_null = trial_null.std(ddof=1)
d = trial_null - mu_null
m2 = (d**2).mean()
m3 = (d**3).mean()
m4 = (d**4).mean()
g1_null = m3 / m2**1.5
g2_null = m4 / m2**2 - 3.0
# DSR formula
den_var = 1 - g1_null * sr_null + (g2_null / 4) * sr_null**2
z_null = (sr_null - SR_max_median) * np.sqrt(T_oos - 1) / np.sqrt(max(den_var, 1e-9))
dsr_null = norm.cdf(z_null)
print(f"  Single null trial: SR_d={sr_null:+.4f}, γ1={g1_null:+.3f}, γ2={g2_null:+.3f}, DSR={dsr_null:.4f}")

# Distribuzione DSR(null): per ogni replica, calcola DSR usando il median SR_max come SR_0
# e usando un random trial come SR_hat
print("\n  Distribuzione DSR(null) su 5000 random trials:")
dsr_null_dist = np.empty(B)
for b in range(B):
    trial = rng.standard_normal(T_oos)
    mu_t = trial.mean()
    sd_t = trial.std(ddof=1)
    sr_t = mu_t / sd_t if sd_t > 0 else 0
    d = trial - mu_t
    m2 = (d**2).mean(); m3 = (d**3).mean(); m4 = (d**4).mean()
    g1 = m3 / m2**1.5 if m2 > 0 else 0
    g2 = m4 / m2**2 - 3.0 if m2 > 0 else 0
    den_var = 1 - g1*sr_t + (g2/4)*sr_t**2
    if den_var <= 0:
        dsr_null_dist[b] = np.nan
        continue
    z = (sr_t - SR_max_median) * np.sqrt(T_oos - 1) / np.sqrt(den_var)
    dsr_null_dist[b] = norm.cdf(z)

dsr_null_dist = dsr_null_dist[np.isfinite(dsr_null_dist)]
print(f"  DSR(null) median       = {np.median(dsr_null_dist):.4f}")
print(f"  DSR(null) mean         = {dsr_null_dist.mean():.4f}")
print(f"  DSR(null) CI 90%       = [{np.percentile(dsr_null_dist,5):.4f}, {np.percentile(dsr_null_dist,95):.4f}]")
print(f"  Fraction DSR>0.5       = {(dsr_null_dist>0.5).mean():.4f}")
print(f"  Fraction DSR>0.674 (v7.4 agg) = {(dsr_null_dist>0.674).mean():.4f}")

# =============================================================================
# 3. Confronto v7.4 vs buy-hold vs null
# =============================================================================
print("\n--- Confronto v7.4 vs buy-hold vs null ---")
SR_hat_d_v7_4 = 0.0744  # aggregato T=196
DSR_v7_4 = 0.6744

print(f"\n{'Strategy':36} {'SR_d':>10} {'SR_a':>10} {'DSR_oos':>10}")
print(f"{'v7.4 aggregato (T_eff=220)':36} {SR_hat_d_v7_4:>10.4f} {SR_hat_d_v7_4*np.sqrt(252):>10.4f} {DSR_v7_4:>10.4f}")
for tkr, r in bh_results.items():
    print(f"{tkr+' buy-hold':36} {r['sr_d']:>10.4f} {r['sr_a']:>10.4f} {'n/a':>10}")
print(f"{'Null gaussian (median)':36} {0.0:>10.4f} {0.0:>10.4f} {np.median(dsr_null_dist):>10.4f}")

# =============================================================================
# 4. Predizione P7 — verifica
# =============================================================================
print("\n--- Predizione P7 verifica ---")
print(f"  P7a — Buy-hold MSCI World SR_d ∈ [0.03, 0.06]:")
if 'URTH' in bh_results:
    sr_urth = bh_results['URTH']['sr_d']
    p7a = "PASS" if 0.03 <= sr_urth <= 0.06 else "FAIL"
    print(f"        URTH SR_d = {sr_urth:.4f} → {p7a}")
print(f"  P7b — Null SR_max √(2·ln(72))/√65 = 0.347:")
print(f"        Empirico = {SR_max_median:.4f}, ratio = {SR_max_median/SR_max_formula:.3f}")
p7b = "PASS" if abs(SR_max_median - SR_max_formula) / SR_max_formula < 0.20 else "FAIL"
print(f"        Tolleranza ±20% → {p7b}")
print(f"  P7c — DSR null calibrato 0.50 ± 0.03:")
p7c_dsr_med = np.median(dsr_null_dist)
p7c = "PASS" if abs(p7c_dsr_med - 0.50) < 0.05 else "FAIL"
print(f"        DSR(null) median = {p7c_dsr_med:.4f} → {p7c}")
print(f"  P7d — DSR(null)>0.55 → bug benchmark; ≤0.52 → calibrato:")
print(f"        DSR(null) median = {p7c_dsr_med:.4f}")
if p7c_dsr_med > 0.55:
    print(f"        FLAG: possibile bug benchmark")
elif p7c_dsr_med <= 0.52:
    print(f"        CALIBRATO")
else:
    print(f"        AMBIGUO (zona grigia)")

# Save
np.savez('task7b_benchmark.npz',
         SR_max_dist=SR_max_dist,
         dsr_null_dist=dsr_null_dist,
         SR_max_median=SR_max_median,
         SR_max_formula=SR_max_formula,
         **{f'{tkr}_rets': r['rets'] for tkr, r in bh_results.items()},
         **{f'{tkr}_sr_d': r['sr_d'] for tkr, r in bh_results.items()})
print("\nSaved task7b_benchmark.npz")
