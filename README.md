# SeekQL PoC

## Prerequisiti
- OpenSearch estratto in `.\lib\opensearch`
- Python 3.10+ (comando `py` o `python`)
- Node.js 18+ (per Vite)
- Porte libere: 9200 (OpenSearch), 8000 (Backend), 3000 (Frontend)

## Avvio rapido
1) Doppio click su `start_all.bat`
2) Apri:
   - Frontend → http://localhost:3000
   - API health → http://localhost:8000/health
   - OpenSearch → http://localhost:9200

> In locale, disabilita la security nel file `lib\opensearch\config\opensearch.yml`:
>
> ```yaml
> plugins.security.disabled: true
> network.host: 127.0.0.1
> discovery.type: single-node
> ```