# Pre-registration S1 v8 — Addendum 02-WIKI-PARSER

Data sigillo: 23/05/2026 — 20:50 CEST (emesso retrospettivamente)
Riferimento: pre-reg root + addendum 01
Scope: parser Wikipedia per snapshot S&P 500 + lista changes 2020-2026

## Nota di emissione retrospettiva

Questo addendum viene emesso dopo che gli artefatti tecnici sono già
stati committati nel branch `feature/v8-s1-refactor` (commit `4d2101d`,
23/05/2026 17:30 CEST circa). Il consulente non aveva sigillato un
addendum formale parallelo alla committenza tecnica — gap rilevato dal
committente Luigi Missere alle 20:28 CEST del 23/05.

L'emissione retrospettiva NON viola la disciplina append-only:
- gli artefatti committati restano immutati nei commit originali
- questo addendum aggiunge documentazione formale + SHA256 di sigillo
- non esiste retroazione su decisioni o numeri precedenti

Mea culpa accettato dal consulente, vedi §0 di
`risposta_consulente_mandato_s1_v8.md`.

## Sigillo file parser

### parse_sp500.py
- SHA256: `face8ab5485443f702a9c857d17c7167798517d0c4599fa7a964c702a87790c0`
- Funzione: parsing della tabella corrente S&P 500 da Wikipedia
  (`https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`)
- Output: `sp500_snapshot_2026_05_23.csv`
- Metodologia: pplx content fetch della pagina Wikipedia + parser
  Python su HTML table con beautifulsoup-like logic
- Esecuzione: 23/05/2026 16:54 CEST (timestamp file)

### parse_sp500_changes.py
- SHA256: `c6abfe44d80120cd5cf02f3bc8dfd448a5bb58c3e1226132ead702e68affbc3e`
- Funzione: parsing della tabella "Selected changes to the list of
  S&P 500 components" sulla stessa pagina Wikipedia
- Output: `sp500_changes_2020_2026.csv`
- Esecuzione: 23/05/2026 18:06 CEST

### build_universe_pit.py
- SHA256: `6ca0b6ee9b0a9a427b2218f7c616c671680a4b1b4a1634533c5ee5cda0803aa9`
- Funzione: composizione universo point-in-time partendo da snapshot
  corrente + back-reverting tutte le change events 2020-2026
- Output: `universe_v8_sp500_pit.csv` + `universe_v8_snapshots.json`
- Esecuzione: 23/05/2026 18:08 CEST

## Sigillo output

| File | SHA256 | Records | Note |
|---|---|---|---|
| sp500_snapshot_2026_05_23.csv | `dbe9a0371bd0ef09...` | 503 ticker | snapshot al 23/05/2026 |
| sp500_changes_2020_2026.csv | `c1b7e455cf3f7d0a...` | 125 eventi | 112 rimozioni distinte |
| universe_v8_sp500_pit.csv | `6c350fd7566bf300...` | 616 ticker | universo PIT |
| universe_v8_snapshots.json | `590edda5b27dddad...` | 4 snapshot storici | per debug |

## Limiti dichiarati del parser

1. **Fonte unica Wikipedia**: nessun cross-check automatico contro
   altre fonti (SEC EDGAR 13F iShares IVV, S&P Dow Jones official).
   Gap previsto come deliverable del gate 27/05 (Universe v8 gold
   standard cross-check).

2. **Wikipedia revision history**: il parser scarica la VERSIONE
   ATTUALE della pagina. La cronologia delle modifiche storiche
   (revision history) è prevista come fonte secondaria al gate 27/05.

3. **Reconstitution pre-2020**: OUT-OF-SCOPE S1 dichiarato. Per stress
   test 2008 (GFC) sarà necessario addendum esplicito S2 (vedi
   risposta consulente §5 aggiunta 1, accettata).

4. **Date di reconstitution**: la colonna `date_iso` nel CSV usa la
   data di effective inclusion/exclusion riportata su Wikipedia. La
   reconstitution effettiva sul mercato può essere stata fino a 5 trading
   day successivi (S&P Dow Jones policy). Effetto trascurabile per il
   nostro walk-forward con fold quarterly.

## Tracciabilità

- Commit artefatti: `4d2101d` (S1.1+S1.2 PASS)
- Commit questo addendum: TBD (gate 24/05 21:30)
- Tag: rimane `s1-prereg-v8` (cumulativo)

SHA256 di questo file: (calcolato post-write)
