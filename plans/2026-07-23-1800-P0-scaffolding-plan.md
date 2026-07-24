# Piano P0 — Scaffolding e spike RAG end-to-end

**Progetto:** sistema RAG in Django con LangChain e LLM privato locale (prova tecnica).
**Fase:** P0, attività T-01 → T-06 di [BACKLOG.md](../BACKLOG.md).
**Stima:** 5,75 h.
**Scadenza complessiva del progetto:** lunedì 27 luglio 2026, ore 9:30.

---

## Problema / Obiettivo

Portare il repository da «solo documentazione» a **ambiente di sviluppo
funzionante con un RAG dimostrabile**, per quanto grezzo.

L'obiettivo finale di P0 non è codice pulito: è **eliminare il rischio
tecnico**. Al termine della fase deve essere provato sul campo che PostgreSQL
con pgvector, il modello di embedding e il modello di generazione si parlano e
producono una risposta corretta su un PDF reale. Tutto il codice della fase 5
(lo spike) verrà **buttato via** in P1: serve a produrre conoscenza, non
artefatti.

Motivazione dell'ordine: la sequenza naturale (modelli → admin → ingestione →
RAG) concentrerebbe il rischio tecnico alla fine, quando non resta margine per
assorbirlo. Lo spike lo sposta all'inizio.

---

## Contesto

### Documenti da leggere prima di iniziare

Sono già presenti nel repository e contengono tutte le decisioni prese:

- `REQUIREMENTS.md` — analisi funzionale: 30 requisiti, casi d'uso, criteri di accettazione
- `ARCHITECTURE.md` — scelte architetturali, alternative valutate, modello dati, compromessi
- `PLAN.md` — piano per fasi P0→P6
- `BACKLOG.md` — scomposizione in 43 attività con priorità e dipendenze

### Decisioni di progetto già prese

| Componente | Scelta | Motivo |
|---|---|---|
| LLM di generazione | `qwen2.5:7b-instruct` via Ollama | Locale, nessun dato esce; buon multilingua; sostituibile per nome dall'admin |
| Embedding | `bge-m3` via Ollama | Multilingua (i PDF sono in italiano); **evita torch/sentence-transformers**, quindi niente dipendenza da ~2,5 GB di wheel |
| Vector store | PostgreSQL + pgvector via `langchain_postgres.PGVector` | Un solo datastore per dati applicativi e vettori |
| Estrazione PDF | PyMuPDF | Veloce, conserva il numero di pagina (serve per le citazioni) |
| Framework | Django 6.0 + DRF | Django 6 richiede **Python 3.12+** |
| Coda asincrona | `django-tasks` + `django-tasks-db` (fase P5, **non ora**) | Nessun Redis: un solo servizio con stato. In P0 non si installa nulla di tutto questo |

### Alternative scartate (non riproporle)

- **Ollama in container:** su Windows il passthrough GPU richiede WSL2 +
  nvidia-container-toolkit. Ollama gira **nativamente sull'host**; i container
  lo raggiungono via `host.docker.internal`.
- **Embedding via sentence-transformers/HuggingFace:** scartato in favore di
  `bge-m3` servito da Ollama, per non introdurre torch.
- **Chroma / FAISS / Qdrant:** scartati in favore di pgvector, cfr. ARCHITECTURE §7.2.
- **Celery + Redis:** scartato, cfr. ARCHITECTURE §7.5.
- **Modelli `-cloud` di Ollama** (`deepseek-v3.1:671b-cloud`, `gpt-oss:120b-cloud`,
  già presenti sulla macchina): **vietati**, violano il vincolo di località.

### Assunzioni verificate sulla macchina di sviluppo

Tutte già accertate, non serve rimetterle in discussione:

- Python **3.12.10**, git **2.52**, Docker **29.1.3** con Compose **v2.40.3**
- Ollama **0.32.1** nativo, in esecuzione sull'host su `localhost:11434`
- GPU **NVIDIA RTX 5060 Laptop, 8151 MiB** — `qwen2.5:7b-instruct` (~4,7 GB Q4)
  e `bge-m3` (~1,2 GB) coesistono in VRAM
- Modelli **già scaricati**: `qwen2.5:7b-instruct` e `bge-m3` (non riscaricarli)

### Vincolo d'ambiente importante: porte occupate

Sulla macchina girano già altri stack Docker:

- **5432** → occupata da `q-postgres-1`
- **5433** → occupata da `q-langfuse-postgres-1`

Il database di questo progetto usa quindi la porta host **5434**. Dentro la rete
di Compose vale comunque la porta interna 5432: i servizi containerizzati devono
ricevere `POSTGRES_PORT=5432` esplicitamente, altrimenti ereditano 5434 da `.env`
e non trovano il database.

Nota collaterale: sulla macchina è già attivo uno stack **Langfuse v3**
self-hosted. Il costo infrastrutturale che ne aveva motivato l'esclusione
(sei container, 8 GB) è quindi già sostenuto. Da rivalutare in P5 (T-35), non ora.

### Versioni verificate delle dipendenze

Installazione già eseguita e riuscita con questi vincoli; le versioni risolte
sono note e vanno ricongelate con `pip freeze` dopo l'installazione:

```
Django 6.0.7 · djangorestframework 3.17.1 · python-dotenv 1.2.2
psycopg 3.3.4 (+psycopg-binary) · pgvector 0.3.6
langchain-core 1.5.0 · langchain-text-splitters 1.1.2
langchain-ollama 1.1.0 · langchain-postgres 0.0.17
pymupdf 1.28.0 · httpx 0.28.1 (dichiarata esplicitamente: la usa l'health check)
sqlalchemy · asyncpg · psycopg-pool (transitive di langchain-postgres)
```

**Attenzione:** `langchain-core` è alla **1.x**, non 0.3. Le importazioni LCEL
(`langchain_core.prompts`, `langchain_core.output_parsers`) restano valide, ma
non dare per scontata la compatibilità con esempi scritti per 0.x.

### Stato di partenza del repository

```
archetype-lab/
├── .claude/            # skill di progetto, già committate
├── ARCHITECTURE.md     # committato
├── PLAN.md             # committato
├── REQUIREMENTS.md     # committato
└── BACKLOG.md          # NON tracciato, da committare in fase 1
```

Ultimo commit: `1c89089 Init repo`, allineato con
`origin/main` = `https://github.com/ValerioJiang/private-ai-rag-poc.git`.
Non esiste `.gitignore`: per questo `.claude/settings.local.json` è finito
tracciato. **Decisione presa:** va aggiunto a `.gitignore` **e rimosso
dall'indice** con `git rm --cached` nella fase 1. Aggiungerlo soltanto a
`.gitignore` non basterebbe: il file è già tracciato e `.gitignore` non ha
alcun effetto sui file tracciati, quindi continuerebbe a comparire fra le
modifiche. Il file resta comunque sul disco.

**Nota per gli esecutori:** all'avvio di P0 `ARCHITECTURE.md`, `PLAN.md` e
`REQUIREMENTS.md` risultano modificati e non committati. **È voluto: li committa
l'utente a mano.** Nessuna fase deve aggiungerli, committarli o modificarli, e la
loro presenza in `git status` non è un errore da correggere.

### Casi limite già discussi

- Un PDF di sole immagini (scansione senza OCR) produce zero testo estraibile.
  Nello spike è sufficiente accorgersene e segnalarlo; la gestione strutturata
  arriva in P2 (T-14, requisito RF-10).
- Il primo caricamento di un modello in VRAM aggiunge diverse decine di secondi
  alla prima chiamata. Non è un errore: i timeout vanno tarati di conseguenza.

---

## Prerequisiti

Prima di eseguire qualsiasi fase, verificare:

### Strumenti
- [x] Python 3.12+ disponibile (verifica: `python --version` → attesa `3.12.x` o superiore)
- [x] git disponibile (verifica: `git --version`)
- [x] Docker attivo (verifica: `docker ps`)
- [x] Docker Compose v2 (verifica: `docker compose version`)

### Servizi
- [x] Ollama in esecuzione sull'host (verifica: `curl -s http://localhost:11434/api/tags`).
      **Verificato il 24/07: in esecuzione, versione 0.32.3, 7 modelli disponibili.**
      Se in una sessione successiva risultasse spento, va riavviato prima delle
      fasi 3, 4 e 5: senza Ollama `/health` resta `degraded` e lo spike fallisce.
      Avvio: aprire l'app Ollama, oppure
      `Start-Process -WindowStyle Hidden ollama -ArgumentList 'serve'` da PowerShell.
- [x] Modello di generazione presente (verifica: `ollama list | grep qwen2.5:7b-instruct`)
- [x] Modello di embedding presente (verifica: `ollama list | grep bge-m3`)

### Porte
- [x] Porta 5434 libera (verifica: `netstat -ano | grep ":5434" | grep LISTENING` → **nessun output atteso**)

### Repository
- [x] Posizionati in `C:\Users\vjiang\Documents\archetype-lab` (verifica: `git rev-parse --show-toplevel`)
- [x] Documenti di progetto presenti (verifica: `ls ARCHITECTURE.md PLAN.md REQUIREMENTS.md BACKLOG.md`)

### Materiale di prova
- [x] Un PDF **testuale** in italiano per lo spike, da salvare in `samples/` (verifica: `ls samples/*.pdf`).
      Se non disponibile, la fase 5 include un passo per generarne uno con PyMuPDF.

---

## Design

### Struttura del progetto al termine di P0

```
archetype-lab/
├── .env                      # NON versionato
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── requirements.in           # vincoli larghi, scritti a mano
├── requirements.txt          # generato con pip freeze
├── README.md
├── samples/                  # PDF di prova
├── scripts/
│   └── spike_rag.py          # fase 5, codice usa-e-getta
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── urls.py
│   ├── wsgi.py
│   └── settings/
│       ├── __init__.py
│       ├── base.py
│       ├── dev.py
│       └── prod.py
└── rag/
    ├── __init__.py
    ├── admin.py
    ├── apps.py
    ├── models.py             # vuoto in P0, popolato in P1
    ├── urls.py
    ├── views.py              # solo /health
    └── migrations/
        ├── __init__.py
        └── 0001_enable_pgvector.py
```

### Principio architetturale da non violare

In `settings` **non deve finire alcun parametro di comportamento del RAG**.
Modello, temperatura, chunking e retrieval saranno righe di database gestite
dall'admin (P1). In `settings` stanno soltanto indirizzi di infrastruttura
(`OLLAMA_BASE_URL`, credenziali del database). Lo spike della fase 5 è l'unica
eccezione ammessa, ed è codice destinato a essere cancellato.

### Cache

La catena LangChain costruita in P3 conterrà **oggetti Python vivi** (client di
inferenza, connessioni): non è serializzabile. La cache deve quindi essere
in-process (`LocMemCache`), mai Redis né database. Va impostata già ora.

---

## Modello di esecuzione: una fase = un sub-agente

Le cinque fasi si eseguono in **cinque sub-agenti distinti, in sequenza**. Non
serve accorparne nessuna.

Il motivo è che ogni passaggio di consegne fra fasi avviene attraverso **stato
persistente** — file sul disco e servizi in esecuzione — e mai attraverso il
contesto della conversazione:

| Da → a | Cosa passa | Come sopravvive al cambio di agente |
|---|---|---|
| 1 → 2, 3, 4, 5 | virtualenv, `requirements.txt` | cartella `.venv/` sul disco |
| 2 → 3, 5 | PostgreSQL con pgvector | container `db` in esecuzione, volume `pgdata` |
| 2 → 3 | variabili d'ambiente | file `.env` letto da `base.py` |
| 3 → 4, 5 | settings Django, migrazioni | `config/settings/` e schema del DB |
| 4 → 5 | dimensione degli embedding, tempi | **file di report**, cfr. sotto |

L'unica dipendenza che non è già un file è l'esito conoscitivo della fase 4 —
la dimensione del vettore di `bge-m3` e i tempi di prima invocazione. Il piano
lo prevedeva già come «da annotare nel report»: quel passo **non è
facoltativo**, è il meccanismo che rende la fase 4 separabile dalla 5.

Perché non accorpare 4 e 5, che sono le candidate più naturali: la fase 4 costa
tre comandi, la fase 5 è la più lunga del piano. Tenerle separate dà un punto di
arresto a basso costo — se Ollama non risponde o un modello non entra in VRAM,
lo si scopre prima di aver costruito lo spike, non durante.

**Vincolo per ogni sub-agente:** ciascuno deve rileggere dal disco quello che gli
serve. Nessuno può presumere di aver visto l'output di un altro.

---

## Fasi di implementazione

### Fase 1: Igiene del repository e dipendenze

**Status:** DONE

**Attività di backlog coperte:** T-01, T-03

**Read first:**
- `BACKLOG.md` — per confermare l'ambito di T-01 e T-03
- `ARCHITECTURE.md` §7 — per capire perché queste dipendenze e non altre

**Files to modify:**
- `.gitignore` (nuovo)
- `README.md` (nuovo)
- `requirements.in` (nuovo)
- `requirements.txt` (generato)

**Changes:**

- [x] **1.1** Creare `.gitignore`:
  ```gitignore
  # Python
  __pycache__/
  *.py[cod]
  *.egg-info/
  build/
  dist/

  # Ambiente virtuale
  .venv/
  venv/
  env/

  # Django
  *.log
  local_settings.py
  db.sqlite3
  /staticfiles/
  /media/

  # Configurazione locale
  .env
  .env.local

  # Test e coverage
  .pytest_cache/
  .coverage
  htmlcov/

  # IDE
  .idea/
  .vscode/
  *.swp

  # Sistema operativo
  Thumbs.db
  Desktop.ini
  .DS_Store

  # Claude Code — impostazioni locali della macchina
  .claude/settings.local.json
  .claude/scheduled_tasks.lock
  ```

- [x] **1.2** Creare `requirements.in` con vincoli larghi (le versioni esatte
  le fissa `pip freeze` al passo 1.5):
  ```
  # Vincoli di alto livello. requirements.txt è generato da qui con pip freeze
  # dopo un'installazione reale, così le versioni bloccate sono verificate.

  # --- Framework ---
  Django>=6.0,<6.1
  djangorestframework>=3.16
  python-dotenv>=1.0

  # --- Database e vector store ---
  psycopg[binary]>=3.2
  # <0.4 non è una preferenza: langchain-postgres 0.0.17 dichiara pgvector<0.4.
  # Scriverlo qui evita che pip debba tornare indietro da pgvector 0.5.
  pgvector>=0.3,<0.4

  # --- LangChain ---
  langchain-core>=1.0
  langchain-text-splitters>=1.0
  langchain-ollama>=1.0
  # Nessuna 0.1: la serie si ferma alla 0.0.17. Trascina sqlalchemy, asyncpg
  # e psycopg-pool, quindi un secondo ORM e un secondo driver. Cfr. ARCHITECTURE §7.9.
  langchain-postgres>=0.0.17

  # --- Estrazione PDF ---
  pymupdf>=1.24

  # --- Client HTTP ---
  # Usato direttamente dall'health check (fase 3): arriverebbe comunque come
  # transitiva di langchain-ollama, ma il codice di prima parte non deve
  # dipendere da una transitiva.
  httpx>=0.27
  ```

- [x] **1.3** Creare `README.md`:
  ```markdown
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
  ```

- [x] **1.4** Creare il virtualenv e installare:
  ```bash
  python -m venv .venv
  .venv/Scripts/python.exe -m pip install --upgrade pip
  .venv/Scripts/python.exe -m pip install -r requirements.in
  ```

- [x] **1.5** Congelare le versioni risolte:
  ```bash
  .venv/Scripts/python.exe -m pip freeze > requirements.txt
  ```

- [x] **1.6** Rimuovere `.claude/settings.local.json` dall'indice. Il file resta
  sul disco: `--cached` tocca soltanto l'indice di git. Senza questo passo la
  riga aggiunta a `.gitignore` non produce alcun effetto, perché `.gitignore`
  è ignorato per i file già tracciati:
  ```bash
  git rm --cached .claude/settings.local.json
  ```

- [x] **1.7** Primo commit della fase (include `BACKLOG.md`, finora non tracciato,
  e la rimozione dall'indice del passo 1.6). **Non usare `git add -A`:**
  `ARCHITECTURE.md`, `PLAN.md` e `REQUIREMENTS.md` sono modificati di proposito
  e li committa l'utente a mano.
  ```bash
  git add .gitignore README.md requirements.in requirements.txt BACKLOG.md
  git commit -m "P0: igiene repo, README e dipendenze bloccate"
  ```

**Verify:**
```bash
.venv/Scripts/python.exe -c "import django, langchain_core, langchain_postgres, langchain_ollama, fitz; print(django.get_version())"
.venv/Scripts/python.exe -m pip freeze | grep -Ei "^(Django|langchain-core|langchain-postgres|langchain-ollama|pymupdf|psycopg)="
git status --short
git ls-files --error-unmatch .claude/settings.local.json 2>&1 | grep -q "did not match" && echo "OK: non piu tracciato"
```

**Phase Complete When:**
- [x] `.venv` esiste e importa Django 6.0.x senza errori
- [x] `requirements.txt` contiene versioni esatte (nessun `>=`)
- [x] `.claude/settings.local.json` non è più tracciato da git
- [x] `git status --short` mostra soltanto le tre modifiche attese ad
      `ARCHITECTURE.md`, `PLAN.md`, `REQUIREMENTS.md` più `?? plans/`
      (non tracciata, va bene). La cartella `.venv/` **non** compare
      perché ignorata, e nemmeno `.claude/settings.local.json`

---

### Fase 2: Infrastruttura Docker e configurazione d'ambiente

**Status:** DONE

**Attività di backlog coperte:** T-02

**Read first:**
- `ARCHITECTURE.md` §2 — diagramma di deployment, motivo per cui Ollama resta sull'host
- `.gitignore` creato in fase 1 — confermare che `.env` sia ignorato

**Files to modify:**
- `docker-compose.yml` (nuovo)
- `Dockerfile` (nuovo)
- `.env.example` (nuovo)
- `.env` (nuovo, non versionato)

**Changes:**

- [x] **2.1** Creare `docker-compose.yml`. Il servizio `worker` è predisposto per
  P5 e disattivato tramite profilo, perché `manage.py db_worker` non esiste ancora:
  ```yaml
  # Ollama NON è containerizzato di proposito: gira nativamente sull'host per
  # avere accesso diretto alla GPU. I container lo raggiungono via
  # host.docker.internal. Cfr. ARCHITECTURE.md §2.

  services:
    db:
      image: pgvector/pgvector:pg17
      environment:
        POSTGRES_DB: ${POSTGRES_DB:-ragdb}
        POSTGRES_USER: ${POSTGRES_USER:-rag}
        POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-rag}
      ports:
        - "${POSTGRES_PORT:-5434}:5432"
      volumes:
        - pgdata:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-rag} -d ${POSTGRES_DB:-ragdb}"]
        interval: 5s
        timeout: 3s
        retries: 10

    web:
      build: .
      command: python manage.py runserver 0.0.0.0:8000
      env_file: .env
      environment:
        POSTGRES_HOST: db
        # dentro la rete di compose vale la porta interna, non quella pubblicata
        POSTGRES_PORT: 5432
        OLLAMA_BASE_URL: http://host.docker.internal:11434
      volumes:
        - .:/app
        - media:/app/media
      ports:
        - "8000:8000"
      depends_on:
        db:
          condition: service_healthy
      extra_hosts:
        - "host.docker.internal:host-gateway"

    # Attivo da T-32 in poi: docker compose --profile worker up
    worker:
      build: .
      command: python manage.py db_worker
      env_file: .env
      environment:
        POSTGRES_HOST: db
        POSTGRES_PORT: 5432
        OLLAMA_BASE_URL: http://host.docker.internal:11434
      volumes:
        - .:/app
        - media:/app/media
      depends_on:
        db:
          condition: service_healthy
      extra_hosts:
        - "host.docker.internal:host-gateway"
      profiles:
        - worker

  volumes:
    pgdata:
    media:
  ```

- [x] **2.2** Creare `Dockerfile`:
  ```dockerfile
  FROM python:3.12-slim

  ENV PYTHONDONTWRITEBYTECODE=1 \
      PYTHONUNBUFFERED=1 \
      PIP_NO_CACHE_DIR=1

  WORKDIR /app

  RUN apt-get update \
      && apt-get install -y --no-install-recommends libpq5 \
      && rm -rf /var/lib/apt/lists/*

  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  COPY . .

  EXPOSE 8000
  CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
  ```

- [x] **2.3** Creare `.env.example`:
  ```bash
  # Copiare in .env e adattare.

  # --- Django ---
  DJANGO_SETTINGS_MODULE=config.settings.dev
  DJANGO_SECRET_KEY=cambiami-in-produzione
  DJANGO_DEBUG=True
  DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

  # --- PostgreSQL ---
  POSTGRES_DB=ragdb
  POSTGRES_USER=rag
  POSTGRES_PASSWORD=rag
  POSTGRES_HOST=localhost
  # 5432 e 5433 sono spesso occupate da altri stack: usiamo 5434
  POSTGRES_PORT=5434

  # --- Ollama (gira sull'host, non in container) ---
  # In esecuzione nativa:  http://localhost:11434
  # Dai container Docker:  http://host.docker.internal:11434
  OLLAMA_BASE_URL=http://localhost:11434

  # --- Osservabilità opzionale (T-35), spenta di default ---
  LANGFUSE_ENABLED=False

  # Tracing verso LangSmith (cloud): spento. Una traccia conterrebbe i chunk
  # dei PDF. base.py lo forza comunque a false, questa riga è per leggibilità.
  # Cfr. ARCHITECTURE.md §9.
  LANGSMITH_TRACING=false
  ```

- [x] **2.4** Creare `.env` locale e avviare il database:
  ```bash
  cp .env.example .env
  docker compose up -d db
  ```

- [x] **2.5** Commit:
  ```bash
  git add docker-compose.yml Dockerfile .env.example
  git commit -m "P0: docker-compose con pgvector e Dockerfile applicativo"
  ```

- [x] **2.6** *(opzionale, ~3-5 minuti)* Costruire l'immagine applicativa. In P0
  si avvia soltanto `db`, quindi il `Dockerfile` non verrebbe mai esercitato e un
  errore resterebbe latente fino a P6. Questa build verifica che
  `requirements.txt` — congelato su Windows — si installi davvero su
  `python:3.12-slim`. Saltarla è ammesso se il tempo stringe:
  ```bash
  docker compose build web
  ```
  Un fallimento qui **non blocca** le fasi successive (che girano nel venv
  dell'host): va annotato nel report come debito da chiudere in P6.

**Verify:**
```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
docker compose exec db psql -U rag -d ragdb -c "SELECT version();"
git status --short
```

**Phase Complete When:**
- [x] `docker compose ps` mostra `db` in stato `healthy`
- [x] La porta pubblicata è `5434->5432`
- [x] `psql` risponde con la versione di PostgreSQL 17
- [x] `.env` **non** compare in `git status`

---

### Fase 3: Progetto Django, settings e health check

**Status:** DONE

**Attività di backlog coperte:** T-04

**Read first:**
- `ARCHITECTURE.md` §3 — il principio «nessun parametro di comportamento nei settings»
- `PLAN.md`, tabella «Decisioni prese», riga *Cache* — perché deve essere in-process
- `.env.example` creato in fase 2 — i nomi delle variabili devono corrispondere

**Files to modify:**
- `manage.py`, `config/asgi.py`, `config/wsgi.py` (generati, poi modificati)
- `config/settings/__init__.py`, `base.py`, `dev.py`, `prod.py` (nuovi)
- `config/urls.py` (sostituito)
- `rag/views.py`, `rag/urls.py` (nuovi/sostituiti)
- `rag/migrations/0001_enable_pgvector.py` (nuovo)

**Changes:**

- [x] **3.1** Generare progetto e app, poi rimuovere il modulo `settings.py` piatto:
  ```bash
  .venv/Scripts/django-admin.exe startproject config .
  .venv/Scripts/python.exe manage.py startapp rag
  rm config/settings.py
  mkdir -p config/settings
  ```

- [x] **3.2** Creare `config/settings/__init__.py` **vuoto**, e `config/settings/base.py`:
  ```python
  """Impostazioni comuni a tutti gli ambienti.

  Nota: qui NON vive alcun parametro di comportamento del sistema RAG. Modello,
  temperatura, chunking e retrieval sono righe di database gestite dall'admin
  (cfr. ARCHITECTURE.md §3). Qui c'è solo l'indirizzo del servizio di inferenza.
  """

  import os
  from pathlib import Path

  from dotenv import load_dotenv

  BASE_DIR = Path(__file__).resolve().parent.parent.parent

  load_dotenv(BASE_DIR / ".env")


  def env_bool(name: str, default: bool = False) -> bool:
      return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


  SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key-cambiami")
  DEBUG = env_bool("DJANGO_DEBUG", False)
  ALLOWED_HOSTS = [
      h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
  ]

  INSTALLED_APPS = [
      "django.contrib.admin",
      "django.contrib.auth",
      "django.contrib.contenttypes",
      "django.contrib.sessions",
      "django.contrib.messages",
      "django.contrib.staticfiles",
      "rest_framework",
      "rag",
  ]

  MIDDLEWARE = [
      "django.middleware.security.SecurityMiddleware",
      "django.contrib.sessions.middleware.SessionMiddleware",
      "django.middleware.common.CommonMiddleware",
      "django.middleware.csrf.CsrfViewMiddleware",
      "django.contrib.auth.middleware.AuthenticationMiddleware",
      "django.contrib.messages.middleware.MessageMiddleware",
      "django.middleware.clickjacking.XFrameOptionsMiddleware",
  ]

  ROOT_URLCONF = "config.urls"

  TEMPLATES = [
      {
          "BACKEND": "django.template.backends.django.DjangoTemplates",
          "DIRS": [BASE_DIR / "templates"],
          "APP_DIRS": True,
          "OPTIONS": {
              "context_processors": [
                  "django.template.context_processors.request",
                  "django.contrib.auth.context_processors.auth",
                  "django.contrib.messages.context_processors.messages",
              ],
          },
      },
  ]

  WSGI_APPLICATION = "config.wsgi.application"

  DATABASES = {
      "default": {
          "ENGINE": "django.db.backends.postgresql",
          "NAME": os.getenv("POSTGRES_DB", "ragdb"),
          "USER": os.getenv("POSTGRES_USER", "rag"),
          "PASSWORD": os.getenv("POSTGRES_PASSWORD", "rag"),
          "HOST": os.getenv("POSTGRES_HOST", "localhost"),
          "PORT": os.getenv("POSTGRES_PORT", "5434"),
      }
  }

  AUTH_PASSWORD_VALIDATORS = [
      {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
      {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
      {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
      {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
  ]

  LANGUAGE_CODE = "it-it"
  TIME_ZONE = "Europe/Rome"
  USE_I18N = True
  USE_TZ = True

  STATIC_URL = "static/"
  STATIC_ROOT = BASE_DIR / "staticfiles"
  MEDIA_URL = "media/"
  MEDIA_ROOT = BASE_DIR / "media"

  DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

  # La catena LangChain costruita da build_chain() contiene oggetti Python vivi
  # (client di inferenza, connessioni): non è serializzabile, quindi la cache
  # deve essere in-process. Cfr. PLAN.md, «Decisioni prese», riga Cache.
  CACHES = {
      "default": {
          "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
          "LOCATION": "rag-chain-cache",
      }
  }

  # --- Servizio di inferenza locale ---
  OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

  # --- Osservabilità opzionale (T-35) ---
  LANGFUSE_ENABLED = env_bool("LANGFUSE_ENABLED", False)

  # LangChain invia tracce a LangSmith (servizio cloud) se trova queste variabili
  # nell'ambiente. Una traccia contiene il prompt completo, quindi i chunk
  # estratti dai PDF: sarebbe esattamente l'esfiltrazione che il progetto
  # promette di escludere. Non basta non impostarle — se la macchina le ha già
  # per altri progetti, il tracing si accende da solo. Vanno forzate a spento.
  # Cfr. ARCHITECTURE.md §9.
  os.environ["LANGSMITH_TRACING"] = "false"
  os.environ["LANGCHAIN_TRACING_V2"] = "false"  # nome legacy, ancora letto

  REST_FRAMEWORK = {
      "DEFAULT_AUTHENTICATION_CLASSES": [
          "rest_framework.authentication.SessionAuthentication",
      ],
      "DEFAULT_PERMISSION_CLASSES": [
          "rest_framework.permissions.AllowAny",
      ],
  }

  LOGGING = {
      "version": 1,
      "disable_existing_loggers": False,
      "formatters": {
          "simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
      },
      "handlers": {
          "console": {"class": "logging.StreamHandler", "formatter": "simple"},
      },
      "root": {"handlers": ["console"], "level": "INFO"},
      "loggers": {
          "rag": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
      },
  }
  ```

- [x] **3.3** Creare `config/settings/dev.py`:
  ```python
  """Ambiente di sviluppo."""

  from .base import *  # noqa: F401,F403

  DEBUG = True
  ALLOWED_HOSTS = ["*"]
  ```

- [x] **3.4** Creare `config/settings/prod.py`:
  ```python
  """Ambiente di produzione.

  Non esercitato in questa prova: presente per completezza e per tenere fuori da
  base.py le impostazioni che varierebbero al deploy.
  """

  from .base import *  # noqa: F401,F403

  DEBUG = False

  SECURE_CONTENT_TYPE_NOSNIFF = True
  SESSION_COOKIE_SECURE = True
  CSRF_COOKIE_SECURE = True
  X_FRAME_OPTIONS = "DENY"
  ```

- [x] **3.5** Far puntare i tre entrypoint ai settings di sviluppo, cioè
  sostituire `config.settings` con `config.settings.dev` nella riga
  `os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...)` di `manage.py`,
  `config/wsgi.py` e `config/asgi.py`.

  **Metodo consigliato: modificare i tre file con l'editor**, una sostituzione
  esplicita per file. È preferibile a `sed -i` perché su Windows `sed -i`
  riscrive il file e può alterare i fine riga, e soprattutto perché una `sed`
  che non trova nulla **esce con successo**: l'errore si manifesterebbe molto
  più tardi, come un `manage.py check` incomprensibile.

  I template di Django 6.0.7 usano gli **apici singoli** (verificato dentro il
  wheel: `os.environ.setdefault('DJANGO_SETTINGS_MODULE', '{{ project_name }}.settings')`
  in `manage.py-tpl`, `wsgi.py-tpl` e `asgi.py-tpl`), ma conviene leggere il file
  prima di sostituire invece di fidarsi.

  Verifica obbligatoria dopo la sostituzione:
  ```bash
  grep -n "DJANGO_SETTINGS_MODULE" manage.py config/wsgi.py config/asgi.py
  ```
  Deve mostrare **tre** righe, tutte con `config.settings.dev`. Se anche una sola
  riporta ancora `config.settings` senza `.dev`, correggerla prima di proseguire.

- [x] **3.6** Sostituire `config/urls.py`:
  ```python
  from django.contrib import admin
  from django.urls import include, path

  urlpatterns = [
      path("admin/", admin.site.urls),
      path("", include("rag.urls")),
  ]
  ```

- [x] **3.7** Creare `rag/urls.py`:
  ```python
  from django.urls import path

  from . import views

  urlpatterns = [
      path("health", views.health, name="health"),
  ]
  ```

- [x] **3.8** Sostituire `rag/views.py` con un health check che verifica davvero
  le dipendenze esterne, non solo che Django risponda:
  ```python
  """Viste di servizio. Le API del RAG arrivano in P4 (T-28 → T-31)."""

  import httpx
  from django.conf import settings
  from django.db import connection
  from rest_framework.decorators import api_view, permission_classes
  from rest_framework.permissions import AllowAny
  from rest_framework.response import Response


  def _check_database() -> tuple[bool, str]:
      try:
          with connection.cursor() as cur:
              cur.execute("SELECT 1")
              cur.fetchone()
          return True, "ok"
      except Exception as exc:  # noqa: BLE001 - l'health check riporta, non gestisce
          return False, str(exc)


  def _check_pgvector() -> tuple[bool, str]:
      try:
          with connection.cursor() as cur:
              cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
              row = cur.fetchone()
          if row:
              return True, f"vector {row[0]}"
          return False, "estensione 'vector' non installata"
      except Exception as exc:  # noqa: BLE001
          return False, str(exc)


  def _check_ollama() -> tuple[bool, str]:
      try:
          resp = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5.0)
          resp.raise_for_status()
          models = [m["name"] for m in resp.json().get("models", [])]
          return True, f"{len(models)} modelli disponibili"
      except Exception as exc:  # noqa: BLE001
          return False, str(exc)


  @api_view(["GET"])
  @permission_classes([AllowAny])
  def health(request):
      checks = {
          "database": _check_database(),
          "pgvector": _check_pgvector(),
          "ollama": _check_ollama(),
      }
      healthy = all(ok for ok, _ in checks.values())
      return Response(
          {
              "status": "ok" if healthy else "degraded",
              "checks": {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()},
          },
          status=200 if healthy else 503,
      )
  ```

- [x] **3.9** Creare `rag/migrations/0001_enable_pgvector.py`. L'estensione va
  installata da migrazione, non a mano, perché l'ambiente deve essere
  ricostruibile con il solo `migrate` (criterio CA-1):
  ```python
  """Abilita l'estensione pgvector."""

  from django.contrib.postgres.operations import CreateExtension
  from django.db import migrations


  class Migration(migrations.Migration):
      initial = True

      dependencies = []

      operations = [
          CreateExtension("vector"),
      ]
  ```

- [x] **3.10** Applicare le migrazioni e creare l'utente amministratore.

  `createsuperuser` **senza `--noinput` chiede la password da terminale** e
  resterebbe bloccato per sempre in esecuzione non interattiva (che è il caso di
  un sub-agente: lo stdin è chiuso). Va quindi usata la forma non interattiva,
  che legge la password da `DJANGO_SUPERUSER_PASSWORD`:
  ```bash
  .venv/Scripts/python.exe manage.py migrate

  DJANGO_SUPERUSER_PASSWORD=admin \
    .venv/Scripts/python.exe manage.py createsuperuser \
    --noinput --username admin --email admin@example.com
  ```
  Credenziali `admin` / `admin`: è un ambiente di sviluppo locale che non viene
  esposto. Se il comando riporta che l'utente esiste già, va bene: è idempotente
  nella pratica, il passo si considera superato.

- [x] **3.11** Commit:
  ```bash
  git add config rag manage.py
  git commit -m "P0: progetto Django, settings per ambiente, health check e pgvector"
  ```

**Verify:**
```bash
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py showmigrations rag
docker compose exec db psql -U rag -d ragdb -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
```

Per l'health check serve il server acceso. In esecuzione non interattiva
`runserver` va avviato in **background** e poi spento, altrimenti blocca:
```bash
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload &
SRV=$!
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health
curl -s http://localhost:8000/health
kill $SRV
```
`--noreload` evita che il reloader generi un processo figlio che `kill`
non raggiungerebbe, lasciando la porta 8000 occupata.

**Phase Complete When:**
- [x] `manage.py check` non riporta problemi
- [x] `showmigrations rag` mostra `[X] 0001_enable_pgvector`
- [x] La query su `pg_extension` restituisce una riga per `vector`
- [x] `GET /health` risponde **200** con `"status": "ok"` e tutti e tre i check a `true`
- [x] L'admin è raggiungibile su `http://localhost:8000/admin/` e accetta il login

---

### Fase 4: Verifica del servizio di inferenza

**Status:** DONE

**Attività di backlog coperte:** T-05

**Read first:**
- `config/settings/base.py` — per confermare il valore di `OLLAMA_BASE_URL`

**Files to modify:**
- Nessuno. Fase di sola verifica.

**Changes:**

- [x] **4.1** Confermare che i due modelli siano presenti (dovrebbero già esserlo,
  non riscaricarli):
  ```bash
  ollama list | grep -E "qwen2.5:7b-instruct|bge-m3"
  ```
  Solo se mancanti:
  ```bash
  ollama pull qwen2.5:7b-instruct
  ollama pull bge-m3
  ```

- [x] **4.2** Verificare la generazione dalla shell Django. Il primo caricamento
  in VRAM può richiedere decine di secondi: non è un errore.
  ```bash
  .venv/Scripts/python.exe manage.py shell -c "
  from django.conf import settings
  from langchain_ollama import ChatOllama
  llm = ChatOllama(model='qwen2.5:7b-instruct', base_url=settings.OLLAMA_BASE_URL, temperature=0)
  print(llm.invoke('Rispondi in italiano con una sola parola: capitale della Francia?').content)
  "
  ```

- [x] **4.3** Verificare gli embedding e **annotarne la dimensione**: è il valore
  che in P1 finirà in `EmbeddingProfile.dimension` e che vincola lo schema
  pgvector.
  ```bash
  .venv/Scripts/python.exe manage.py shell -c "
  from django.conf import settings
  from langchain_ollama import OllamaEmbeddings
  emb = OllamaEmbeddings(model='bge-m3', base_url=settings.OLLAMA_BASE_URL)
  v = emb.embed_query('prova di embedding in italiano')
  print('dimensione:', len(v))
  "
  ```

**Verify:**
```bash
curl -s http://localhost:11434/api/tags
```

**Phase Complete When:**
- [x] `ChatOllama.invoke` restituisce «Parigi» (o equivalente) senza eccezioni
- [x] `OllamaEmbeddings.embed_query` restituisce un vettore non vuoto
- [x] **La dimensione del vettore è annotata nel report** (attesa: 1024 per `bge-m3`;
      se differisce, è il valore reale a fare fede e va usato nelle fasi successive)

---

### Fase 5: Spike RAG end-to-end

**Status:** DONE

**Attività di backlog coperte:** T-06

**Read first:**
- `ARCHITECTURE.md` §4 e §5 — flussi di ingestione e interrogazione da riprodurre in forma minima
- `REQUIREMENTS.md` §7 — criteri CA-3 e CA-4, che questo spike anticipa

**Files to modify:**
- `scripts/spike_rag.py` (nuovo, **usa-e-getta**)
- `samples/` (PDF di prova)

**Changes:**

- [x] **5.1** Procurare un PDF testuale in italiano in `samples/`. Se non se ne
  ha uno a disposizione, generarlo:
  ```bash
  .venv/Scripts/python.exe -c "
  import fitz, pathlib
  pathlib.Path('samples').mkdir(exist_ok=True)
  doc = fitz.open()
  testi = [
      'Politica aziendale sulle ferie. I dipendenti maturano 26 giorni di ferie all anno. '
      'Le ferie vanno richieste con almeno 15 giorni di preavviso al proprio responsabile.',
      'Rimborsi spese. Il rimborso chilometrico e fissato a 0,35 euro al chilometro. '
      'Le note spese vanno presentate entro il giorno 5 del mese successivo.',
      'Lavoro da remoto. Sono consentiti fino a 3 giorni di lavoro da remoto a settimana, '
      'previo accordo con il responsabile diretto.',
  ]
  for t in testi:
      p = doc.new_page()
      p.insert_textbox(fitz.Rect(60, 60, 520, 700), t, fontsize=12)
  doc.save('samples/manuale-dipendenti.pdf')
  print('creato samples/manuale-dipendenti.pdf con', doc.page_count, 'pagine')
  "
  ```

- [x] **5.2** Creare `scripts/spike_rag.py`. **Valori scritti a mano di
  proposito:** in P1 diventeranno righe di database; qui servono solo a provare
  che la catena funziona.

  Unica eccezione alla regola «tutto da buttare»: la funzione `load_pdf()`.
  Non esiste un loader PDF senza tirarsi dentro `langchain-community` (cfr.
  ARCHITECTURE §7.10), quindi quella funzione è codice di prima parte fin
  d'ora e verrà **promossa** in T-14. Scriverla con un minimo di cura; tutto
  il resto del file no.
  ```python
  """SPIKE — codice usa-e-getta (T-06).

  Scopo: dimostrare end-to-end che PyMuPDF, bge-m3, pgvector e qwen2.5 si
  parlano, e misurare i tempi reali sulla macchina.

  NON è codice di produzione: i parametri sono scritti a mano apposta. In P1
  diventeranno righe di database gestite dall'admin. Questo file va cancellato
  quando la fase P2 è completa.

  Uso:
      .venv/Scripts/python.exe scripts/spike_rag.py samples/manuale-dipendenti.pdf
  """

  import os
  import sys
  import time

  import django

  os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
  django.setup()

  from django.conf import settings  # noqa: E402

  import fitz  # noqa: E402  (PyMuPDF)
  from langchain_core.documents import Document  # noqa: E402
  from langchain_core.output_parsers import StrOutputParser  # noqa: E402
  from langchain_core.prompts import ChatPromptTemplate  # noqa: E402
  from langchain_ollama import ChatOllama, OllamaEmbeddings  # noqa: E402
  from langchain_postgres import PGVector  # noqa: E402
  from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402

  # --- parametri scritti a mano: in P1 diventano righe di DB ---
  LLM_MODEL = "qwen2.5:7b-instruct"
  EMBED_MODEL = "bge-m3"
  CHUNK_SIZE = 800
  CHUNK_OVERLAP = 120
  TOP_K = 4
  COLLECTION = "spike"


  def connection_string() -> str:
      return (
          f"postgresql+psycopg://{settings.DATABASES['default']['USER']}:"
          f"{settings.DATABASES['default']['PASSWORD']}@"
          f"{settings.DATABASES['default']['HOST']}:"
          f"{settings.DATABASES['default']['PORT']}/"
          f"{settings.DATABASES['default']['NAME']}"
      )


  def load_pdf(path: str) -> list[Document]:
      """Estrae il testo pagina per pagina, conservando il numero di pagina."""
      doc = fitz.open(path)
      docs = []
      for i, page in enumerate(doc, start=1):
          text = page.get_text().strip()
          if text:
              docs.append(Document(page_content=text, metadata={"source": path, "page": i}))
      if not docs:
          raise SystemExit(
              f"ERRORE: nessun testo estraibile da {path}. "
              "Probabile PDF scansionato senza OCR (caso RF-10)."
          )
      print(f"[load] {len(docs)} pagine con testo su {doc.page_count} totali")
      return docs


  def main() -> None:
      path = sys.argv[1] if len(sys.argv) > 1 else "samples/manuale-dipendenti.pdf"

      pages = load_pdf(path)

      splitter = RecursiveCharacterTextSplitter(
          chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
      )
      chunks = splitter.split_documents(pages)
      print(f"[split] {len(chunks)} chunk")

      embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=settings.OLLAMA_BASE_URL)

      t0 = time.perf_counter()
      store = PGVector.from_documents(
          documents=chunks,
          embedding=embeddings,
          collection_name=COLLECTION,
          connection=connection_string(),
          pre_delete_collection=True,
      )
      print(f"[index] {len(chunks)} chunk indicizzati in {time.perf_counter() - t0:.1f}s")

      retriever = store.as_retriever(search_kwargs={"k": TOP_K})

      prompt = ChatPromptTemplate.from_messages([
          (
              "system",
              "Sei un assistente che risponde ESCLUSIVAMENTE sulla base del contesto fornito. "
              "Se il contesto non contiene l'informazione, rispondi esattamente: "
              "'Non dispongo di questa informazione nei documenti forniti.' "
              "Rispondi in italiano, in modo conciso.",
          ),
          ("human", "Contesto:\n{context}\n\nDomanda: {question}"),
      ])

      llm = ChatOllama(model=LLM_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0)

      def format_docs(docs: list[Document]) -> str:
          return "\n\n".join(f"[pagina {d.metadata.get('page')}] {d.page_content}" for d in docs)

      domande = [
          "Quanti giorni di ferie si maturano all'anno?",          # atteso: nel documento
          "Qual e il rimborso chilometrico?",                       # atteso: nel documento
          "Qual e la capitale del Madagascar?",                     # atteso: non lo so (CA-4)
      ]

      for domanda in domande:
          t0 = time.perf_counter()
          docs = retriever.invoke(domanda)
          t_ret = time.perf_counter() - t0

          t0 = time.perf_counter()
          chain = prompt | llm | StrOutputParser()
          risposta = chain.invoke({"context": format_docs(docs), "question": domanda})
          t_gen = time.perf_counter() - t0

          print("\n" + "=" * 70)
          print(f"D: {domanda}")
          print(f"R: {risposta.strip()}")
          print(f"   fonti: pagine {[d.metadata.get('page') for d in docs]}")
          print(f"   tempi: retrieval {t_ret:.2f}s · generazione {t_gen:.2f}s")


  if __name__ == "__main__":
      main()
  ```

- [x] **5.3** Eseguire lo spike:
  ```bash
  .venv/Scripts/python.exe scripts/spike_rag.py samples/manuale-dipendenti.pdf
  ```

- [x] **5.4** Annotare nel report di esecuzione i **dati di realtà** raccolti,
  perché sono l'input delle fasi successive:
  - dimensione del vettore prodotto da `bge-m3`
  - tempo di indicizzazione per chunk
  - tempo di retrieval e di generazione per domanda
  - nomi effettivi delle tabelle create da `PGVector` in PostgreSQL
  - se il comportamento «non lo so» funziona con questo prompt

- [x] **5.5** Commit (lo spike si versiona: documenta come si è arrivati alle
  scelte, e verrà rimosso in P2):
  ```bash
  git add scripts samples
  git commit -m "P0: spike RAG end-to-end su PDF di prova"
  ```

**Verify:**
```bash
.venv/Scripts/python.exe scripts/spike_rag.py samples/manuale-dipendenti.pdf
docker compose exec db psql -U rag -d ragdb -c "\dt"
docker compose exec db psql -U rag -d ragdb -c "SELECT COUNT(*) FROM langchain_pg_embedding;"
```

**Phase Complete When:**
- [x] Lo script termina senza eccezioni
- [x] Le prime due domande ricevono risposte **corrette** tratte dal PDF
- [x] La terza domanda ottiene «Non dispongo di questa informazione nei documenti forniti.»
- [x] `\dt` mostra le tabelle `langchain_pg_collection` e `langchain_pg_embedding`
- [x] `SELECT COUNT(*) FROM langchain_pg_embedding` restituisce un numero pari ai chunk indicizzati
- [x] I tempi misurati sono annotati nel report

---

## Criteri di completamento di P0

- [x] `GET /health` risponde 200 con database, pgvector e Ollama tutti a `true`
- [x] L'admin Django è raggiungibile e accetta il login
- [x] Lo spike risponde correttamente a domande sul PDF e dichiara di non sapere
      quando la risposta non è nel documento
- [x] **Quattro** commit distinti sul branch `main`, uno per le fasi 1, 2, 3 e 5.
      La fase 4 è di sola verifica e non produce file, quindi non ha un commit
      proprio: il suo esito vive nel report di esecuzione
- [x] Sono note e annotate: dimensione degli embedding, tempi reali di indicizzazione,
      retrieval e generazione sulla macchina

## Rischi noti di questa fase

| Rischio | Mitigazione |
|---|---|
| `langchain-postgres` 0.0.17 con `langchain-core` 1.x: possibili incompatibilità di firma. **Verificato:** il vincolo dichiarato è `langchain-core<2.0,>=0.2.13`, quindi 1.5.x rientra e non c'è conflitto di risoluzione; resta il rischio di comportamento | Se `PGVector.from_documents` fallisce, provare l'API a istanza (`PGVector(...)` + `add_documents`). Annotare quale funziona: sarà quella da usare in P2. Ripiego strutturale, se nemmeno quella regge: retriever custom sull'ORM, cfr. ARCHITECTURE §7.9 |
| `langchain-postgres` trascina **SQLAlchemy, asyncpg e psycopg-pool**: due ORM e due driver verso lo stesso database | Atteso, non un errore: `pip freeze` al passo 1.5 li mostrerà. Vincola inoltre `pgvector` a `<0.4` (la 0.3.6 pinnata va bene) |
| Prima invocazione lentissima per caricamento in VRAM | Attesa, non errore. Non ridurre i timeout sotto i 120 s in questa fase |
| `bge-m3` produce vettori a 1024 dimensioni, più pesanti dei 384 di e5-small | Accettato: la qualità multilingua conta più della dimensione dell'indice a questa scala |
| Contesa di VRAM fra i due modelli su 8 GB | Se Ollama scarica e ricarica di continuo i modelli, ridurre a un solo modello per volta o valutare `qwen2.5:3b-instruct` |

## Cosa NON fare in questa fase

- Non creare modelli Django in `rag/models.py`: è P1 (T-07 → T-13)
- Non generalizzare lo spike: è codice destinato a essere cancellato
- Non spostare parametri del RAG nei settings: devono diventare righe di database
- Non introdurre Celery né Redis
- Non usare i modelli Ollama con suffisso `-cloud`
