# Addendum 01 alla preregistrazione S1.5 esec 3 — Chiarimento universo

**Data**: 24/05/2026 06:51 CEST
**Riferimento**: `preregistration_s15_exec3_grid_ampliato.md` SHA `a2790d3c...`
**Tipo modifica**: chiarimento NON retroattivo (le ipotesi H1-H4 restano immutate)

---

## Errore tipografico nella preregistrazione

Nei comandi Step 1 e Step 2 della preregistrazione ho scritto `--universe SP500`. **Quel valore non esiste** nella CLI `wf_runner.py`. Le scelte valide sono solo `portfolio` o `extended`.

## Decisione

Per S1.5 esec 3 uso **`--universe portfolio`** — è lo stesso universo usato in:

- Addendum 12 D3-bis (preregistrazione corrente S1.5)
- Esecuzione 2 del rerun che ha portato all'apertura di S2 (commit `63d9be3`)

Coerenza con esec 2 è critica per confrontare i risultati su grid ampliato vs grid smoke. Universe `extended` (1037 ticker EU+US) sarebbe inadeguato per il portafoglio 100 k€ del committente.

`universe_portfolio.csv` contiene 35 ticker (più header). Numero coerente con le esecuzioni F2 precedenti.

## Comandi corretti

### Step 1 — Dry-run

```bash
python -m engine.wf_runner \
    --grid s1_5_exec3 \
    --universe portfolio \
    --output-csv s1_outputs/s15_exec3_dry.csv \
    --stability-json s1_outputs/s15_exec3_dry_stability.json \
    --is-months 12 --oos-months 3 --step-months 3 \
    --max-positions 10 --per-ticker-cap 0.10
```

### Step 2 — Run autoritativo F2

```bash
python -m engine.wf_runner \
    --grid s1_5_exec3 \
    --universe portfolio \
    --output-csv s1_outputs/s15_exec3_f2_results.csv \
    --stability-json s1_outputs/s15_exec3_f2_stability.json \
    --save-equity-csv s1_outputs/s15_exec3_f2_equity.csv \
    --save-trades-csv s1_outputs/s15_exec3_f2_trades.csv \
    --is-months 12 --oos-months 3 --step-months 3 \
    --max-positions 10 --per-ticker-cap 0.10 \
    --stable-threshold 3
```

## Cosa NON cambia

- Grid `GRID_S1_5_EXEC3` (6×3×2 = 36 combo) — invariato
- Ipotesi H1-H4 e soglie di falsificazione — invariate
- Step 3-7 — invariati
- Deadline 06/06 23:59 CEST — invariata

— Luigi Missere, 24/05/2026 06:51 CEST
