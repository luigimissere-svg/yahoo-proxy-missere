# Yahoo Finance Proxy

Backend serverless per Patrimonio Missere — proxy a Yahoo Finance con CORS aperto.

## Endpoint

```
GET /api/quotes?symbols=MSFT,UCG.MI,ASML.AS
```

## Esempio risposta

```json
{
  "ok": true,
  "ts": "2026-05-08T15:15:00+00:00",
  "cached": false,
  "count": 3,
  "fx_eur": {"USD": 0.85},
  "data": {
    "MSFT": {
      "price": 414.83,
      "prev_close": 420.77,
      "currency": "USD",
      "variazione_pct": -1.41,
      "name": "Microsoft Corporation",
      "exchange": "NMS"
    }
  }
}
```

## Deploy

1. Crea account su https://vercel.com (gratis, niente carta)
2. Installa CLI: `npm i -g vercel`
3. In questa cartella: `vercel` (segui prompt)
4. Per re-deploy in produzione: `vercel --prod`

## Cache

- Quote: 60 secondi
- FX: 5 minuti

## Limiti free Vercel

- 100k invocazioni/mese
- 10s max per richiesta
- 1024 MB RAM
