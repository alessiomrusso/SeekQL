# PoC: Ricerca SQL con OpenSearch Stand‑Alone + FastAPI + React (bulk + QA)

Novità:
- **Bulk indexing** con `helpers.bulk` e `BULK_CHUNK_SIZE` configurabile (default 500)
- **Pulizia dipendenze**: rimosso modulo non usato
- **track_total_hits** abilitato nelle ricerche per conteggi accurati

## Avvio OpenSearch (senza Docker)
1. Scarica OpenSearch ZIP da https://opensearch.org/downloads.html
2. Estrai come `./opensearch`
3. (Opzionale per test) in `opensearch/config/opensearch.yml` aggiungi `plugins.security.disabled: true`
4. Avvia: `./run_opensearch.sh`

## Backend
1. `cd backend/`
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -r app/requirements.txt`
4. `cp .env.example .env` (modifica se serve; puoi settare BULK_CHUNK_SIZE)
5. Avvia API: `uvicorn app.main:app --reload --port 8000`
6. Indicizza: `bash run_index.sh /percorso/alle/tue/sql`

## Frontend
1. `cd frontend/ && npm install && npm run dev` (proxy su 8000 già configurato)

## Esempi di query (Lucene/OpenSearch query_string)
- AND: `user AND orders`
- OR: `error OR fail`
- NOT: `payment NOT test`
- Frase esatta: `"select * from users"`
- Wildcard: `user*`
- Fuzzy: `roam~`
- Grouping: `(select OR update) AND users`

## Note performance
- Per set di dati molto grandi, aumenta `BULK_CHUNK_SIZE` (es. 1000 o 2000) in `.env` e valuta `request_timeout` maggiore in `indexer.py`.
- Se vuoi ulteriore velocità, usa letture file in streaming e disabilita highlight quando non serve.
