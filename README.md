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

## Licenza

Progetto realizzato come prova tecnica.
