# Sistema RAG in Django con LangChain e LLM privato

Backend Django che implementa un sistema RAG (Retrieval-Augmented Generation)
per rispondere a domande in linguaggio naturale sul contenuto di documenti PDF,
con generazione affidata a un **LLM privato eseguito in locale**.

> **Stato:** in sviluppo. Questo README viene completato in fase P6 (T-39).

## Documentazione

| Documento | Contenuto |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Analisi funzionale: requisiti, casi d'uso, criteri di accettazione |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Scelte architetturali, alternative valutate, compromessi |
| [PLAN.md](PLAN.md) | Piano di lavoro per fasi |
| [BACKLOG.md](BACKLOG.md) | Scomposizione operativa in attività |

## Componenti

| Ruolo | Scelta |
|---|---|
| LLM di generazione | `qwen2.5:7b-instruct` via Ollama, in locale |
| Modello di embedding | `bge-m3` via Ollama, multilingua |
| Vector store | PostgreSQL + pgvector |
| Estrazione PDF | PyMuPDF |
| Framework | Django 6 + Django REST Framework |
| Orchestrazione RAG | LangChain (LCEL) |

Nessun contenuto documentale lascia la macchina: generazione ed embedding sono
entrambi locali.

## Prerequisiti

- **Python 3.12+** (richiesto da Django 6)
- **Docker** con Compose, per PostgreSQL
- **[Ollama](https://ollama.com)** installato sull'host

Ollama gira nativamente sull'host, non in un container: su Windows il
passthrough della GPU verso Docker richiederebbe WSL2 e
nvidia-container-toolkit. I container lo raggiungono via `host.docker.internal`.

## Avvio

```bash
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3

cp .env.example .env
docker compose up -d db

python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Admin su http://localhost:8000/admin/ · stato del servizio su `/health`.

Il database è pubblicato sulla porta **5434**, non sulla 5432: le porte
consuete sono spesso già occupate da altri stack. Il valore sta in
`.env.example`, quindi i comandi qui sopra funzionano così come sono; serve
saperlo solo per collegarsi al database dall'esterno. Dentro la rete di Compose
vale invece la porta interna 5432.

## Uso da riga di comando

Le stesse operazioni disponibili dall'admin esistono come comandi di gestione,
per prova e automazione:

```bash
python manage.py ingest samples/manuale-dipendenti.pdf
python manage.py ask "Quanti giorni di ferie si maturano all'anno?"
python manage.py ask "..." --pipeline "Pipeline predefinita" --json
```

`ingest` porta il documento a *indicizzato*; `ask` stampa la risposta con
documento, pagina, estratto e punteggio di ogni fonte, più i tempi di recupero e
generazione separati. Con `--json` l'uscita è analizzabile, e l'avviso sui tempi
va su `stderr` per non sporcarla. Senza `--pipeline` si usa quella predefinita.

Entrambi i comandi sono **sincroni** e a freddo attendono il caricamento dei
modelli in VRAM: alcune decine di secondi alla prima esecuzione, pochi secondi
dopo. Una domanda che non trova contesto pertinente riceve una dichiarazione di
non conoscenza, non una risposta inventata.

## Licenza

Progetto realizzato come prova tecnica.
