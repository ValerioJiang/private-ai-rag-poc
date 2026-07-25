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
| Coda dei task | `django-tasks` + `django-tasks-db`, sullo stesso PostgreSQL |
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

E, **in un secondo terminale**, il worker che indicizza i documenti:

```bash
python manage.py db_worker
```

Admin su http://localhost:8000/admin/ · stato del servizio su `/health`.

Il database è pubblicato sulla porta **5434**, non sulla 5432: le porte
consuete sono spesso già occupate da altri stack. Il valore sta in
`.env.example`, quindi i comandi qui sopra funzionano così come sono; serve
saperlo solo per collegarsi al database dall'esterno. Dentro la rete di Compose
vale invece la porta interna 5432.

### Il worker, e come farne a meno

I processi sono **due**: il server risponde alle richieste, il worker indicizza.
L'indicizzazione di un PDF costa secondi — fino a una dozzina alla prima
esecuzione di ogni processo, che deve caricare il modello di embedding — e non
sta dentro il ciclo richiesta/risposta: il caricamento risponde subito, il lavoro
avviene dopo.

La coda vive in PostgreSQL, quindi non c'è alcun servizio in più da avviare: il
worker è `python manage.py db_worker` sull'host, oppure, in Compose,

```bash
docker compose --profile worker up --build
```

Il `--build` serve perché `requirements.txt` è cambiato. Con `DJANGO_DEBUG=True`
il worker si riavvia da sé alle modifiche del codice — l'opzione `--reload`
segue `settings.DEBUG` — il che in sviluppo è comodo e in produzione non è
raccomandato (`--no-reload` per disattivarlo).

**Se non si vuole avviare un secondo processo**, il progetto gira lo stesso: in
`.env`

```bash
TASKS_BACKEND=django_tasks.backends.immediate.ImmediateBackend
```

esegue l'indicizzazione **in linea**, nel processo del server. La risposta
all'upload torna a durare quanto l'indicizzazione, ma non serve alcun worker.

> **Il sintomo più probabile: «il documento resta in attesa».** Non è un guasto e
> non è un file rotto — significa che **nessun worker è in esecuzione**. Lo dice
> `/health`, sotto la voce `coda`:
>
> ```json
> "coda": {"ok": true, "detail": "coda su database: 1 in attesa, 0 in esecuzione (le lavora `manage.py db_worker`)"}
> ```
>
> Una coda con task in attesa **non** fa fallire l'health check: è il
> funzionamento normale, e la voce serve a distinguere «worker occupato» da
> «worker mai avviato».

La tabella dei task cresce a ogni indicizzazione ed è il registro storico della
coda. Si pota quando dà fastidio:

```bash
python manage.py prune_db_task_results
```

## API

Tutti gli endpoint sotto `/api/` richiedono autenticazione (Basic o sessione);
`/health` è anonimo di proposito, perché è la sonda del Compose.

```bash
# Caricamento di un PDF — risponde 202 e mette il documento in coda
curl -u utente:password -F "file=@samples/manuale-dipendenti.pdf" \
     http://localhost:8000/api/documents/

# Stato del documento: e' qui che si scopre com'e' finita
curl -u utente:password http://localhost:8000/api/documents/55/

# Elenco, filtrabile per stato
curl -u utente:password "http://localhost:8000/api/documents/?status=indexed"

# Interrogazione
curl -u utente:password -H "Content-Type: application/json" --max-time 180 \
     -d '{"domanda": "Quanti giorni di ferie si maturano?"}' \
     http://localhost:8000/api/ask/

# Configurazioni disponibili
curl -u utente:password http://localhost:8000/api/pipelines/
```

**`POST /api/documents/` risponde `202 Accepted`, non `201`**, e la risorsa che
restituisce è il documento in stato `pending` con zero pagine e zero segmenti. Il
caricamento è **accettato**, non concluso: per sapere com'è andata si interroga
`GET /api/documents/{id}/` finché `status` non diventa `indexed` oppure `failed`.
Nel secondo caso `error_message` porta il motivo in chiaro — per esempio un PDF
di sole immagini:

```json
{"status": "failed",
 "error_message": "Nessun testo estraibile dalle 1 pagine del documento. E' probabilmente una scansione senza OCR: …"}
```

Non esiste un **422**: quella condizione è scoperta dal worker, quando la
risposta HTTP è già partita. Gli esiti della `POST` sono tre — **202** accettato,
**400** file mancante o non PDF o base di conoscenza inesistente, **409** stesso
contenuto già presente (in questo caso non viene creata alcuna riga né scritto
alcun file).

`--max-time 180` sulle interrogazioni non è prudenza eccessiva: la prima
richiesta di un processo appena avviato deve caricare i modelli in VRAM, e sono
stati misurati fino a **30 s** su una singola richiesta. A caldo si sta sotto i
3 s.

## Uso da riga di comando

Le stesse operazioni disponibili dall'admin esistono come comandi di gestione,
per prova e automazione:

```bash
python manage.py ingest samples/manuale-dipendenti.pdf
python manage.py ingest samples/manuale-dipendenti.pdf --async
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

`ingest` resta sincrono **per scelta**, anche ora che l'API accoda: chi guarda un
terminale vuole sapere com'è andata, non che è stato accodato, e le prove di
consegna devono poter girare con un processo solo. Con `--async` accoda e torna
subito — è il modo più corto di provare la coda senza passare da HTTP, e richiede
un worker in esecuzione.

## Licenza

Progetto realizzato come prova tecnica.
