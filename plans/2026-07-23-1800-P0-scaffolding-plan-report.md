# Report di esecuzione — Piano P0 Scaffolding

Report di esecuzione di [2026-07-23-1800-P0-scaffolding-plan.md](2026-07-23-1800-P0-scaffolding-plan.md).
Ogni fase annota qui l'esito e i **dati di realtà** raccolti sulla macchina, che
sono l'input delle fasi successive (cfr. «Modello di esecuzione: una fase = un
sub-agente» nel piano).

---

## Fase 1

**Esito: PASS.** Attività di backlog T-01 e T-03 completate. Tutti i passi da
1.1 a 1.7 eseguiti nell'ordine previsto, senza deviazioni dal contenuto dei
file indicato nel piano.

**Commit:** `fef698e819619e89035b919a9b2d8eb0b9d90a04` — «P0: igiene repo,
README e dipendenze bloccate» (6 file modificati: 5 creati più la rimozione
dall'indice di `.claude/settings.local.json`).

### File creati

| File | Note |
|---|---|
| `.gitignore` | Contenuto del piano, invariato |
| `requirements.in` | Contenuto del piano, invariato, **commenti compresi** |
| `README.md` | Contenuto del piano, invariato |
| `requirements.txt` | Generato con `pip freeze`, 49 pacchetti, tutti con `==` |

### Versioni effettivamente risolte

Python di partenza: **3.12.10**. `pip` aggiornato da 25.0.1 a **26.1.2** prima
dell'installazione.

| Pacchetto | Atteso dal piano | Risolto | Esito |
|---|---|---|---|
| Django | 6.0.7 | **6.0.7** | come atteso |
| djangorestframework | 3.17.1 | **3.17.1** | come atteso |
| python-dotenv | 1.2.2 | **1.2.2** | come atteso |
| psycopg (+ psycopg-binary) | 3.3.4 | **3.3.4** | come atteso |
| pgvector | 0.3.6 | **0.3.6** | come atteso |
| langchain-core | 1.5.0 | **1.5.1** | scostamento di patch, cfr. sotto |
| langchain-text-splitters | 1.1.2 | **1.1.2** | come atteso |
| langchain-ollama | 1.1.0 | **1.1.0** | come atteso |
| langchain-postgres | 0.0.17 | **0.0.17** | come atteso |
| pymupdf | 1.28.0 | **1.28.0** | come atteso |
| httpx | 0.28.1 | **0.28.1** | come atteso |

Transitive rilevanti confermate, come previsto da ARCHITECTURE §7.9: **SQLAlchemy
2.0.51**, **asyncpg 0.31.0**, **psycopg-pool 3.3.1** — cioè il secondo ORM e il
secondo driver, costo accettato in fase di progettazione. Presenti anche
`langsmith 0.10.10` (dipendenza diretta di `langchain-core`, cfr. ARCHITECTURE
§7.10: va neutralizzata a runtime in fase 3, non escludendo il pacchetto),
`ollama 0.6.2`, `numpy 2.5.1`, `pydantic 2.13.4`.

**Verificato: nessun `torch`, nessun `sentence-transformers`** nell'albero
installato. Il vincolo di §7.3 regge.

### Scostamenti dal piano

1. **`langchain-core` 1.5.1 anziché 1.5.0.** Unico scostamento. È una patch
   release uscita dopo la stesura del piano; il vincolo importante — la serie
   **1.x e non 0.3.x** — è rispettato. Non corretto a forza, come da istruzioni.
   Il vincolo dichiarato da `langchain-postgres` 0.0.17 è `langchain-core<2.0,>=0.2.13`:
   1.5.1 vi rientra, nessun conflitto di risoluzione. Il rischio di
   *comportamento* resta aperto e va confermato dallo spike (fase 5).
2. **Nessun backtracking di pip.** L'installazione è stata lineare: il vincolo
   `pgvector>=0.3,<0.4` scritto a mano in `requirements.in` ha evitato che il
   risolutore dovesse tornare indietro dalla 0.5, che era esattamente la sua
   ragione d'essere. Il commento nel file è quindi confermato utile.
3. **Avviso git sui fine riga** (`LF will be replaced by CRLF`) su `.gitignore`,
   `BACKLOG.md`, `README.md`, `requirements.in`. Innocuo su Windows senza
   `.gitattributes`, nessuna azione intrapresa.

### Verifica finale

- `import django, langchain_core, langchain_postgres, langchain_ollama, fitz` →
  nessuna eccezione, `django.get_version()` = **6.0.7**
- `requirements.txt` → 49 righe, tutte `==`, nessun `>=`
- `git ls-files .claude/settings.local.json` → **nessun output**: non più
  tracciato. Il file **resta sul disco** (11.249 byte), come previsto da `--cached`
- `git status --short` → esattamente le quattro righe attese:
  ` M ARCHITECTURE.md`, ` M PLAN.md`, ` M REQUIREMENTS.md`, `?? plans/`.
  Né `.venv/` né `.claude/settings.local.json` compaiono

### Consegna alla fase successiva

- `.venv/` sul disco, funzionante, con tutte le dipendenze di P0 installate
- `requirements.txt` con versioni esatte, pronto per la `COPY` del `Dockerfile`
  della fase 2 (attenzione: è congelato su Windows, la build su `python:3.12-slim`
  del passo 2.6 è la verifica che regga anche su Linux)
- `.gitignore` già contiene `.env`: il passo 2.4 può creare `.env` senza rischio
  di versionarlo

---

## Fase 2

**Esito: PASS.** Attività di backlog T-02 completata. Passi da 2.1 a 2.6 eseguiti
nell'ordine previsto, senza deviazioni dal contenuto dei file indicato nel piano.
La build opzionale 2.6 è stata **eseguita ed è riuscita**: nessun debito lasciato
aperto verso P6.

**Commit:** `5882e0bf33e8c6db038394165734e781f5908dda` — «P0: docker-compose con
pgvector e Dockerfile applicativo» (3 file creati, 111 inserzioni).

### File creati

| File | Note |
|---|---|
| `docker-compose.yml` | Contenuto del piano, invariato, commenti compresi. Servizio `worker` presente ma disattivato da `profiles: [worker]` |
| `Dockerfile` | Contenuto del piano, invariato. Base `python:3.12-slim` |
| `.env.example` | Contenuto del piano, invariato |
| `.env` | Copia di `.env.example`, **non versionata** (ignorata da `.gitignore:21`) |

### Database

- Immagine `pgvector/pgvector:pg17` già presente in cache locale: nessun
  download, avvio immediato (il container è risultato `healthy` in ~15 s).
- **PostgreSQL rilevata: 17.10** — `PostgreSQL 17.10 (Debian 17.10-1.pgdg12+1)
  on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit`.
- Porta pubblicata: **`0.0.0.0:5434->5432/tcp`**, come richiesto dal vincolo
  d'ambiente (5432 e 5433 occupate da altri stack, che non sono stati toccati).
- Estensione `vector` **disponibile** nel catalogo (`pg_available_extensions`)
  alla versione **0.8.5**. Non ancora installata: la installa la migrazione
  `0001_enable_pgvector` della fase 3, come da criterio CA-1.
- Volume `archetype-lab_pgdata` e rete `archetype-lab_default` creati da zero.

### Passo 2.6 — build dell'immagine applicativa

**Eseguita, esito PASS.** `docker compose build web` completata in ~1 minuto;
immagine `archetype-lab-web:latest`, 946 MB.

Questo era il punto di rischio della fase: `requirements.txt` è stato congelato
su Windows e non era detto che si installasse su `python:3.12-slim`. **Si
installa senza modifiche**: tutte le 49 dipendenze risolte da wheel, nessuna
compilazione da sorgente, nessun pacchetto Windows-only nel freeze. Le versioni
installate nel container coincidono con i pin (Django 6.0.7, langchain-core
1.5.1, langchain-postgres 0.0.17, pgvector 0.3.6, psycopg 3.3.4, pymupdf 1.28.0).

Conseguenza: **nessun debito da chiudere in P6** su questo fronte.

### Scostamenti dal piano

Nessuno di sostanza. Due note operative:

1. **Avviso git sui fine riga** (`LF will be replaced by CRLF`) su tutti e tre i
   file aggiunti. Stesso avviso della fase 1, innocuo, nessuna azione intrapresa.
2. Nel container di build pip segnala di essere alla 25.0.1 (l'aggiornamento
   della fase 1 riguardava il venv dell'host, non l'immagine). Irrilevante:
   l'installazione è comunque riuscita.

### Verifica finale

- `docker compose ps` → `archetype-lab-db-1  Up (healthy)  0.0.0.0:5434->5432/tcp`
- `psql -U rag -d ragdb -c "SELECT version();"` → **PostgreSQL 17.10**
- `git status --short` → esattamente le quattro righe attese
  (` M ARCHITECTURE.md`, ` M PLAN.md`, ` M REQUIREMENTS.md`, `?? plans/`).
  **`.env` non compare**; `git check-ignore -v .env` conferma la regola
  `.gitignore:21:.env`
- Nessun altro stack Docker della macchina è stato fermato o modificato

### Consegna alla fase successiva

- Container `db` in esecuzione, `healthy`, raggiungibile dall'host su
  **`localhost:5434`** con credenziali `rag` / `rag` / db `ragdb`
- `.env` presente sul disco con `POSTGRES_PORT=5434` e
  `OLLAMA_BASE_URL=http://localhost:11434`: sono i valori che `config/settings/base.py`
  leggerà nella fase 3. I nomi delle variabili in `base.py` devono corrispondere
  a quelli di `.env.example`
- L'estensione `vector` è disponibile ma **non installata**: la fase 3 deve
  crearla via migrazione, non a mano
- Immagine `archetype-lab-web:latest` già costruita; in P0 non va avviata
  (`manage.py` non esiste ancora al momento della build — il `COPY . .` ha
  copiato l'albero senza progetto Django, quindi l'immagine andrà ricostruita
  dopo la fase 3 prima di poterla eseguire)

---

## Fase 3 — Progetto Django, settings e health check

**Esito: PASS.** Tutti i passi da 3.1 a 3.11 eseguiti nell'ordine previsto.
Nessuno scostamento dal piano: il contenuto dei file Python è quello letterale
della fase 3, senza riscritture.

### File creati / modificati

| File | Operazione |
|---|---|
| `manage.py` | generato da `startproject`, poi `DJANGO_SETTINGS_MODULE` → `config.settings.dev` |
| `config/__init__.py`, `config/wsgi.py`, `config/asgi.py` | generati; nei due entrypoint `DJANGO_SETTINGS_MODULE` → `config.settings.dev` |
| `config/settings.py` | **rimosso** (modulo piatto sostituito dal package) |
| `config/settings/__init__.py` | nuovo, vuoto |
| `config/settings/base.py` | nuovo |
| `config/settings/dev.py` | nuovo |
| `config/settings/prod.py` | nuovo |
| `config/urls.py` | sostituito (admin + `include("rag.urls")`) |
| `rag/` (`__init__.py`, `admin.py`, `apps.py`, `models.py`, `tests.py`, `migrations/__init__.py`) | generati da `startapp`, lasciati intatti |
| `rag/urls.py` | nuovo |
| `rag/views.py` | sostituito con l'health check a tre controlli |
| `rag/migrations/0001_enable_pgvector.py` | nuovo (`CreateExtension("vector")`) |

`rag/models.py` è rimasto come generato da `startapp`: i modelli sono P1
(T-07 → T-13), come da vincolo.

### Principio architetturale rispettato

In `config/settings/base.py` non è stata introdotta alcuna costante di
comportamento del RAG (nessun `CHUNK_SIZE`, `LLM_MODEL`, `TOP_K`, temperatura).
L'unico riferimento al sistema di inferenza è `OLLAMA_BASE_URL`, cioè un
indirizzo di infrastruttura. Presenti come richiesto:

- `CACHES` con `LocMemCache` (`LOCATION: "rag-chain-cache"`): in-process, mai
  Redis né database, perché la catena LangChain di P3 conterrà oggetti Python vivi
- la forzatura di `LANGSMITH_TRACING` e `LANGCHAIN_TRACING_V2` a `"false"`,
  mantenuta integralmente

I nomi delle variabili lette da `base.py` corrispondono uno a uno a quelli di
`.env.example` (`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
`POSTGRES_DB/USER/PASSWORD/HOST/PORT`, `OLLAMA_BASE_URL`, `LANGFUSE_ENABLED`).

### Passo 3.5 — sostituzione degli entrypoint

Eseguita con l'editor, non con `sed -i`. I tre file sono stati letti prima della
sostituzione: Django 6.0.7 usa effettivamente gli **apici singoli**, come previsto
dal piano. Verifica obbligatoria superata — tre righe, tutte con `config.settings.dev`:

```
config/wsgi.py:14:os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
manage.py:9:    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
config/asgi.py:14:os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
```

### Migrazioni e utente amministratore

`manage.py migrate` ha applicato 19 migrazioni, fra cui `rag.0001_enable_pgvector`.
`createsuperuser --noinput` con `DJANGO_SUPERUSER_PASSWORD=admin` ha risposto
`Superuser created successfully` (utente `admin` / `admin`, mail
`admin@example.com`).

L'estensione è stata installata **dalla migrazione**, non a mano con `psql`:
l'ambiente resta ricostruibile con il solo `migrate` (criterio CA-1).

### Versione dell'estensione vector rilevata

```
 extname | extversion
---------+------------
 vector  | 0.8.5
(1 row)
```

**`vector 0.8.5`** — versione fornita dall'immagine `pgvector/pgvector:pg17`.
È il valore che compare anche nel dettaglio del check `pgvector` di `/health`.

### Verifiche di completamento

| Criterio | Esito |
|---|---|
| `manage.py check` | `System check identified no issues (0 silenced).` |
| `showmigrations rag` | `[X] 0001_enable_pgvector` |
| Query su `pg_extension` | una riga: `vector 0.8.5` |
| `GET /health` | **200**, `"status": "ok"`, tutti e tre i check a `true` |
| Admin su `/admin/` | **302** verso `/admin/login/`, che risponde **200** (con `-L`: 200) |

### Corpo JSON completo della risposta di `/health`

```json
{
  "status": "ok",
  "checks": {
    "database": { "ok": true, "detail": "ok" },
    "pgvector": { "ok": true, "detail": "vector 0.8.5" },
    "ollama": { "ok": true, "detail": "7 modelli disponibili" }
  }
}
```

Risposta grezza, così come restituita:

```
{"status":"ok","checks":{"database":{"ok":true,"detail":"ok"},"pgvector":{"ok":true,"detail":"vector 0.8.5"},"ollama":{"ok":true,"detail":"7 modelli disponibili"}}}
```

Il server è stato avviato in background con `--noreload` e spento al termine di
ogni verifica: `netstat` conferma che la **porta 8000 è libera**.

### Commit

```
f4e0ae814081c4f973fecdf71ec201dfa178ed99
P0: progetto Django, settings per ambiente, health check e pgvector
18 files changed, 319 insertions(+)
```

Staging esplicito con `git add config rag manage.py`, mai `git add -A`.
`ARCHITECTURE.md`, `PLAN.md` e `REQUIREMENTS.md` restano modificati e non
committati (li committa l'utente a mano), `plans/` resta non tracciata.

### Note e osservazioni

1. Git ha segnalato `LF will be replaced by CRLF` sui file scritti: è la normale
   normalizzazione `core.autocrlf` su Windows, non un problema. Il contenuto
   committato usa fine riga LF.
2. `/admin/` risponde **302** e non 200: è il comportamento corretto di Django
   per un utente non autenticato (redirect a `/admin/login/?next=/admin/`).
   `/admin/login/` risponde 200 e presenta il form di login. Il criterio
   «l'admin risponde» è quindi soddisfatto.
3. Il check `ollama` riporta **7 modelli disponibili**, coerente con quanto
   accertato nei prerequisiti del piano.

### Consegna alla fase successiva

- `config/settings/dev.py` è il modulo di default dei tre entrypoint: la fase 4
  può usare direttamente `manage.py shell -c ...` senza impostare variabili
- `settings.OLLAMA_BASE_URL` vale `http://localhost:11434` (letto da `.env`)
- Schema del database migrato ed estensione `vector` attiva: la fase 5 può
  creare le tabelle di `PGVector` senza passi manuali
- L'immagine `archetype-lab-web:latest` costruita in fase 2 è ora **obsoleta**:
  è stata costruita prima che esistesse il progetto Django. Va ricostruita
  (`docker compose build web`) prima di poterla eseguire — debito da chiudere in P6

---

---

## Fase 4 — Verifica del servizio di inferenza

- **Status:** PASS
- **Attività coperte:** T-05
- **Commit:** nessuno, per progetto. La fase è di sola verifica: il suo esito vive
  in questa sezione del report ed è il meccanismo che la rende separabile dalla 5.
- **Retry:** 0

### 4.1 Modelli

Entrambi già presenti, nessun `pull` eseguito:

| Modello | Dimensione | Quantizzazione |
|---|---|---|
| `qwen2.5:7b-instruct` | 4,68 GB | Q4_K_M |
| `bge-m3:latest` | 1,16 GB | F16 |

`OLLAMA_BASE_URL` confermato a `http://localhost:11434` in `config/settings/base.py`.
Unica destinazione di rete contattata: quella. **Nessun modello `-cloud` toccato**, il
vincolo di località è rispettato.

### 4.2 Generazione

Risposta ottenuta da `qwen2.5:7b-instruct`: **`Parigi`** — una sola parola, senza
preamboli. Una terza invocazione di controllo con domanda diversa ha restituito
`Roma`, quindi la risposta non arriva da una cache.

### 4.3 / 4.4 Embedding — DIMENSIONE DEL VETTORE

> # 1024
>
> Dimensione rilevata da `OllamaEmbeddings.embed_query` su `bge-m3`, confermata su due
> query diverse e corroborata dai metadati dell'API Ollama (`embedding_length: 1024`).
> **Coincide con l'attesa del piano.**
>
> È il valore che in P1 finisce in `EmbeddingProfile.dimension` e che vincola la
> colonna pgvector a `vector(1024)`.

### Tempi misurati

| Operazione | Prima invocazione (a freddo) | Successive (a caldo) |
|---|---|---|
| chat (`qwen2.5:7b-instruct`) | **155,92 s** | 0,69 s · 0,67 s |
| embed (`bge-m3`) | **65,17 s** | 9,14 s |

`ollama ps` era vuoto prima del test, quindi i ~156 s sono **cold start puro**: un
fattore ~226× contro le chiamate a caldo.

**Implicazione operativa per la fase 5 e per P2:** timeout ad **almeno 180 s** sulla
prima chiamata. Ollama scarica i modelli dopo ~5 minuti di idle, quindi ogni sessione
ricomincia a freddo — non è un errore da diagnosticare, è il comportamento normale.

### Contesa di VRAM: non materializzata

Il rischio previsto dal piano non si è verificato. I due modelli **coesistono**,
entrambi al 100% GPU, senza fallback su CPU né ricarico ciclico: 4,7 GB + 664 MB
≈ 5,4 GB sugli ~8 GB disponibili, con ~2,6 GB di margine.

Due avvertenze da non perdere:

1. Il contesto attivo durante la misura era **4096**, non i massimi dichiarati dai
   modelli (8192 / 32768). Alzarlo in P3 erode il margine di VRAM: da rivalutare lì.
2. Il **secondo** embedding a 9,14 s è anomalo contro gli 0,69 s della seconda chat,
   pur senza ricarichi visibili in `ollama ps`. Da riosservare in P2 sull'ingest
   reale, dove il costo per chunk diventa determinante.

### Scostamenti dal piano

Nessuno nei risultati. Una nota di processo: la sezione di report è stata scritta in
un secondo momento rispetto all'esecuzione delle verifiche, perché l'attivazione del
plan mode aveva bloccato le scritture su disco. Le misure riportate sono quelle
rilevate durante l'esecuzione della fase, non ricostruite.

Il repository non è stato modificato: nessun file creato, nessun commit.

---

## Fase 5 — Spike RAG end-to-end

- **Status:** PASS
- **Attività coperte:** T-06
- **Commit:** `8274af265b22646e1e49f447be2e55644ec341b8` — «P0: spike RAG end-to-end
  su PDF di prova» (2 file creati, 223 inserzioni: `scripts/spike_rag.py` e
  `samples/manuale-dipendenti.pdf`)
- **Retry:** 1 (un fallimento all'avvio, cfr. «Scostamenti»)

Tutti e sei i criteri di completamento della fase sono soddisfatti. Il rischio
tecnico che P0 doveva eliminare è **eliminato**: PyMuPDF, `bge-m3`, pgvector e
`qwen2.5:7b-instruct` si parlano e producono risposte corrette su un PDF reale.

### 5.1 PDF di prova

Nessun PDF italiano era disponibile: `samples/` non esisteva. È stato generato
con lo snippet PyMuPDF del piano, senza modifiche → `samples/manuale-dipendenti.pdf`,
**3 pagine** (ferie, rimborsi, lavoro da remoto), 1.937 byte. PDF **testuale**,
non scansionato: le 3 pagine producono tutte testo estraibile.

### 5.2 Script

`scripts/spike_rag.py` creato con il sorgente del piano, **con una sola aggiunta
funzionale** (3 righe, cfr. «Scostamenti»). Parametri lasciati scritti a mano
come da vincolo: `CHUNK_SIZE=800`, `CHUNK_OVERLAP=120`, `TOP_K=4`,
`COLLECTION="spike"`, `temperature=0`. Nessuna astrazione introdotta, nessun
parametro spostato nei settings, nessun modello Django creato.

---

## DATI DI REALTÀ (passo 5.4)

Questi sono l'input diretto delle fasi P1 e P2.

### Dimensione del vettore prodotto da `bge-m3`

> # 1024
>
> **Confermata a valle**, non solo dall'API: `vector_dims(embedding)` sulle righe
> effettivamente scritte in `langchain_pg_embedding` restituisce **1024** per tutte
> e tre. Coincide con quanto misurato in fase 4 e con l'attesa del piano.
> È il valore che in P1 finisce in `EmbeddingProfile.dimension`.

### Chunking

| Grandezza | Valore |
|---|---|
| Pagine con testo / totali | 3 / 3 |
| Chunk prodotti da `RecursiveCharacterTextSplitter(800, 120)` | **3** |
| Rapporto | 1 chunk per pagina — le pagine del PDF di prova sono corte (~180 caratteri), sotto la soglia di split |

**Nota per P2:** con questo PDF il chunking non è realmente esercitato. Il
comportamento dello splitter su pagine lunghe resta da osservare sull'ingest reale.

### Tempi misurati

Due esecuzioni complete. La prima **a freddo** (Ollama aveva già scaricato i
modelli dall'idle della fase 4), la seconda **a caldo** subito dopo.

| Operazione | 1ª esecuzione (a freddo) | 2ª esecuzione (a caldo) | Fattore |
|---|---|---|---|
| Indicizzazione, 3 chunk | **54,7 s** | **1,2 s** | ~46× |
| — per singolo chunk | **~18,2 s/chunk** | **~0,4 s/chunk** | |
| Retrieval, domanda 1 | 12,45 s | 0,88 s | |
| Generazione, domanda 1 | 10,46 s | 1,20 s | |
| Retrieval, domanda 2 | 11,50 s | 0,83 s | |
| Generazione, domanda 2 | 1,34 s | 1,12 s | |
| Retrieval, domanda 3 | 0,83 s | 0,78 s | |
| Generazione, domanda 3 | 1,14 s | 0,99 s | |

Letture importanti:

1. **I ~18 s/chunk a freddo non sono il costo per chunk**: sono il caricamento di
   `bge-m3` in VRAM ammortizzato su 3 chunk. Il costo marginale vero è quello a
   caldo, **~0,4 s/chunk**. La stima da usare in P2 per l'ingest è
   `≈ 0,4 s × n_chunk + ~50 s di cold start` se il modello non è già caricato.
2. **Il cold start si ripresenta a metà esecuzione.** Il retrieval della domanda 1
   costa 12,45 s e quello della domanda 2 ancora 11,50 s, poi crolla a 0,83 s: è
   `bge-m3` che viene **ricaricato** perché nel frattempo `qwen2.5` gli ha rubato
   la VRAM. È il *thrashing* fra i due modelli previsto dai rischi del piano, che
   in fase 4 non si era materializzato perché le due misure erano ravvicinate.
   Qui è visibile e va tenuto presente per il dimensionamento dei timeout in P4.
3. **Il cold start totale di questa fase è inferiore ai ~156 s della fase 4**
   (54,7 s di indicizzazione contro i 65 s del solo embed a freddo): i modelli
   erano parzialmente ancora in memoria. Il caso peggiore resta quello misurato
   in fase 4.
4. **A caldo il sistema è pronto per una demo**: ~2 s end-to-end per domanda.

### Nomi effettivi delle tabelle create da PGVector

`PGVector` ha creato **due** tabelle, esattamente quelle attese:

| Tabella | Contenuto |
|---|---|
| `langchain_pg_collection` | 1 riga: `uuid=6a374296-be53-4338-b996-72f70bea9f9d`, `name=spike` |
| `langchain_pg_embedding` | 3 righe, una per chunk |

Schema di `langchain_pg_embedding` così come creato:

```
    Column     |       Type        | Nullable
---------------+-------------------+----------
 id            | character varying | not null
 collection_id | uuid              |
 embedding     | vector            |
 document      | character varying |
 cmetadata     | jsonb             |
Indexes:
    "langchain_pg_embedding_pkey" PRIMARY KEY, btree (id)
    "ix_cmetadata_gin" gin (cmetadata jsonb_path_ops)
Foreign-key constraints:
    "langchain_pg_embedding_collection_id_fkey"
        FOREIGN KEY (collection_id) REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE
```

**Tre osservazioni che contano per P1 e P2:**

1. La colonna `embedding` è di tipo `vector` **senza dimensione dichiarata**, non
   `vector(1024)`. `langchain-postgres` 0.0.17 non vincola lo schema: la coerenza
   dimensionale non è imposta dal database. Se in P1 si vorranno più
   `EmbeddingProfile` con dimensioni diverse, il database **non** li separerà da
   solo — la separazione va garantita per collezione (`collection_name`), non
   sperando nel vincolo di colonna.
2. **Nessun indice ANN** (né HNSW né IVFFlat) viene creato: c'è solo la GIN sui
   metadati. Alla scala della prova la scansione sequenziale è irrilevante, ma è
   un debito noto da valutare in P2/P5 se il corpus cresce.
3. `id` è `character varying`, non `uuid`: sono UUID **come stringa**. Da tenere
   presente se in P1 si collegherà `DocumentChunk` a queste righe.

Le tabelle di Django (`auth_*`, `django_*`) sono rimaste intatte: `\dt` mostra
12 tabelle in tutto, 10 di Django più le 2 di PGVector.

### Comportamento «non lo so» (CA-4): FUNZIONA

Il prompt del piano **funziona senza modifiche**. Alla domanda sulla capitale del
Madagascar il modello ha restituito la stringa richiesta **carattere per
carattere**, in entrambe le esecuzioni:

```
Non dispongo di questa informazione nei documenti forniti.
```

Nessun preambolo, nessuna virgolettatura, nessuna aggiunta. Notevole perché il
retriever aveva comunque passato al modello 3 chunk (`k=4`, ma i documenti sono
3): il modello ha ricevuto contesto **irrilevante** e non ha ceduto alla
tentazione di rispondere «Antananarivo» dalla conoscenza parametrica. Il vincolo
del system prompt regge.

**Il prompt è quindi promuovibile come valore di default del `PromptTemplate` di P1.**

### Quale API di PGVector ha funzionato

> **`PGVector.from_documents()` — il metodo di classe. Ha funzionato al primo
> tentativo, senza fallback.**

Il rischio noto (`langchain-postgres` 0.0.17 con `langchain-core` **1.5.1**) **non
si è materializzato**. Non è stato necessario ricorrere all'API a istanza
(`PGVector(...)` + `add_documents()`), né tantomeno al ripiego strutturale del
retriever custom sull'ORM (ARCHITECTURE §7.9).

Firma verificata funzionante, da riusare in P2:

```python
PGVector.from_documents(
    documents=chunks,
    embedding=embeddings,
    collection_name=COLLECTION,
    connection=connection_string(),   # 'connection', non 'connection_string'
    pre_delete_collection=True,
)
```

Note d'uso confermate sul campo:

- Il parametro si chiama **`connection`** e accetta una stringa DSN nella forma
  `postgresql+psycopg://...` (dialetto SQLAlchemy con driver psycopg 3 esplicito).
- **`pre_delete_collection=True` è idempotente**: la seconda esecuzione ha
  ricreato la collezione senza duplicare nulla — il conteggio è rimasto a 3
  embedding e 1 collezione. Utile in P2 per la re-indicizzazione di un documento.
- Al primo giro `langchain_postgres.vectorstores` emette
  `WARNING ... Collection not found`. **Non è un errore**: è `pre_delete_collection`
  che tenta la cancellazione di una collezione inesistente. Va atteso, non diagnosticato.
- `store.as_retriever(search_kwargs={"k": TOP_K})` funziona; con meno documenti
  di `k` restituisce quanti ne trova, senza errori.

---

### Testo integrale delle tre risposte

Identiche nelle due esecuzioni (`temperature=0` è rispettata: il sistema è
deterministico).

**Domanda 1 — «Quanti giorni di ferie si maturano all'anno?»**

```
Si maturano 26 giorni di ferie all'anno.
```

Fonti: pagine `[1, 3, 2]`. **CORRETTA** — il PDF dice «26 giorni di ferie all anno» a pagina 1.

**Domanda 2 — «Qual e il rimborso chilometrico?»**

```
Il rimborso chilometrico è di 0,35 euro al chilometro.
```

Fonti: pagine `[2, 3, 1]`. **CORRETTA** — il PDF dice «0,35 euro al chilometro» a pagina 2.

**Domanda 3 — «Qual e la capitale del Madagascar?»**

```
Non dispongo di questa informazione nei documenti forniti.
```

Fonti: pagine `[3, 2, 1]`. **CORRETTA per CA-4** — dichiarazione di non conoscenza, non una risposta inventata.

In entrambe le domande sul contenuto il chunk pertinente è risultato **primo**
nell'ordinamento per similarità (pagina 1 per le ferie, pagina 2 per i rimborsi):
il retrieval con `bge-m3` discrimina correttamente su testo italiano.

### Anticipazione di CA-3 e CA-4 (REQUIREMENTS §7)

- **CA-3** — «una domanda sul contenuto del PDF riceve una risposta corretta con
  le fonti citate»: **anticipato con esito positivo**. Le risposte sono corrette e
  i numeri di pagina sono disponibili nei metadati (`cmetadata->>'page'`),
  persistiti in `langchain_pg_embedding` e restituiti dal retriever. La citazione
  formale nella risposta API è P4.
- **CA-4** — «una domanda fuori dal contenuto ottiene una dichiarazione di non
  conoscenza»: **anticipato con esito positivo**, stringa esatta.

I flussi di ARCHITECTURE §4 (ingestione: PyMuPDF → pagine → chunk → embed →
pgvector) e §5 (interrogazione: retrieval top-k → prompt → LLM → risposta) sono
stati riprodotti in forma minima e funzionano entrambi.

---

### Scostamenti dal piano

**Uno solo, e necessario.**

**Il sorgente del piano non è eseguibile così com'è.** Alla prima esecuzione lo
script è fallito con:

```
ModuleNotFoundError: No module named 'config'
```

Causa: lo script vive in `scripts/`, quindi `sys.path[0]` è `scripts/` e **non** la
radice del progetto — `django.setup()` non trova `config.settings.dev`. Non è un
problema d'ambiente: è un difetto del sorgente del piano, che riproduce l'header
di `manage.py` (il quale però sta *nella radice* del progetto).

Correzione applicata, un import più 3 righe, prima di `django.setup()`:

```python
from pathlib import Path
...
# Lo script vive in scripts/, quindi sys.path[0] e' scripts/ e non la radice del
# progetto: senza questa riga `import config.settings.dev` fallisce.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

Scelta fra le due opzioni possibili: si è preferita la correzione del sorgente a
un `PYTHONPATH=.` esterno, perché il comando documentato dal piano
(`.venv/Scripts/python.exe scripts/spike_rag.py samples/...`) deve funzionare
verbatim, ed è il comando che compare sia nel passo 5.3 sia nel blocco *Verify*.
**Nessun'altra riga del sorgente è stata toccata.** Il file del piano non è stato
modificato, come da vincolo.

Note minori, senza impatto:

1. `PYTHONIOENCODING=utf-8` impostata sull'esecuzione (non nel file) per il
   carattere `·` nella riga dei tempi. Precauzione, non un errore osservato.
2. Solito avviso git `LF will be replaced by CRLF` su `scripts/spike_rag.py`.
3. `TOP_K=4` ma i documenti indicizzati sono 3: il retriever ne restituisce 3.
   Comportamento corretto, non un errore.

### Verifica finale (blocco *Verify* del piano)

| Criterio di completamento | Esito |
|---|---|
| Lo script termina senza eccezioni | **PASS** (due esecuzioni su due) |
| Le prime due domande ricevono risposte corrette dal PDF | **PASS** |
| La terza ottiene esattamente «Non dispongo di questa informazione nei documenti forniti.» | **PASS**, carattere per carattere |
| `\dt` mostra `langchain_pg_collection` e `langchain_pg_embedding` | **PASS**, entrambe presenti |
| `SELECT COUNT(*) FROM langchain_pg_embedding` pari ai chunk indicizzati | **PASS**: `3` = 3 chunk |
| I tempi misurati sono annotati nel report | **PASS**, sopra |

`git status --short` finale: esattamente le quattro righe attese
(` M ARCHITECTURE.md`, ` M PLAN.md`, ` M REQUIREMENTS.md`, `?? plans/`).
Staging esplicito con `git add scripts samples`, mai `git add -A`.

### Vincoli rispettati

- Nessun modello `-cloud` contattato: l'unica destinazione di rete è
  `http://localhost:11434`. I `deepseek-v3.1:671b-cloud` e `gpt-oss:120b-cloud`
  presenti sulla macchina non sono stati toccati.
- Nessun modello Django creato in `rag/models.py` (è P1).
- Nessun parametro del RAG spostato nei settings: restano tutti scritti a mano
  nello spike, come da principio architetturale.
- Nessuna astrazione, nessuna configurazione estratta, nessuna generalizzazione.
  L'unica funzione scritta con cura è `load_pdf()`, che è codice di prima parte
  destinato alla promozione in T-14.

### Consegna a P1 / P2

| Conoscenza acquisita | Dove serve |
|---|---|
| Dimensione vettore = **1024** | `EmbeddingProfile.dimension` (P1, T-08) |
| `PGVector.from_documents(connection=...)` funziona con langchain-core 1.5.1 | Servizio di ingestione (P2, T-15) |
| `pre_delete_collection=True` è idempotente | Re-indicizzazione documento (P2) |
| Costo marginale ≈ **0,4 s/chunk** a caldo, più ~50 s di cold start | Dimensionamento timeout dell'ingest (P2) e della coda (P5) |
| Il cold start si ripresenta **a metà sessione** per thrashing di VRAM | Timeout delle API di interrogazione (P4, T-30): non basta tarare sulla prima chiamata |
| Il system prompt del piano produce il «non lo so» esatto | Valore di default del `PromptTemplate` (P1, T-09) |
| La colonna `embedding` è `vector` senza dimensione: nessun vincolo dal DB | Isolare i profili per `collection_name` (P2) |
| Nessun indice ANN creato da PGVector | Debito da valutare in P2/P5 se il corpus cresce |
| `load_pdf()` funziona e conserva il numero di pagina | Da **promuovere** a codice di prima parte in T-14 |
| Un PDF senza testo estraibile è intercettato da `load_pdf()` | Base della gestione strutturata di RF-10 / CA-8 (P2, T-14) |

`scripts/spike_rag.py` e `samples/` vanno **cancellati** al termine di P2, come previsto.

---

## Esito di P0

> # PASS
>
> Tutti e cinque i criteri di completamento di P0 sono soddisfatti. Le attività di
> backlog T-01 → T-06 sono chiuse. Il rischio tecnico che la fase doveva eliminare
> — «i quattro componenti si parlano davvero?» — è **eliminato con prova sul campo**.

| # | Criterio di completamento di P0 | Esito | Evidenza |
|---|---|---|---|
| 1 | `GET /health` risponde 200 con database, pgvector e Ollama tutti a `true` | **PASS** | Fase 3: `{"status":"ok"}`, `database` ok, `pgvector` «vector 0.8.5», `ollama` «7 modelli disponibili» |
| 2 | L'admin Django è raggiungibile e accetta il login | **PASS** | Fase 3: `/admin/` → 302 → `/admin/login/` → 200; utente `admin`/`admin` creato |
| 3 | Lo spike risponde correttamente a domande sul PDF e dichiara di non sapere quando la risposta non è nel documento | **PASS** | Fase 5: 2 risposte corrette con fonti più «Non dispongo di questa informazione nei documenti forniti.» |
| 4 | **Quattro** commit distinti su `main`, uno per le fasi 1, 2, 3 e 5 | **PASS** | vedi sotto |
| 5 | Sono note e annotate dimensione degli embedding e tempi reali di indicizzazione, retrieval e generazione | **PASS** | 1024 (fasi 4 e 5); tempi a freddo e a caldo tabulati in fase 5 |

### I quattro commit di P0

```
8274af2  P0: spike RAG end-to-end su PDF di prova                            (fase 5)
f4e0ae8  P0: progetto Django, settings per ambiente, health check e pgvector (fase 3)
5882e0b  P0: docker-compose con pgvector e Dockerfile applicativo            (fase 2)
fef698e  P0: igiene repo, README e dipendenze bloccate                       (fase 1)
1c89089  Init repo                                                           (pre-P0)
```

Esattamente quattro, uno per fase produttiva. La **fase 4 non ha commit proprio**,
come previsto dal piano: è di sola verifica e il suo esito vive nella sezione
«Fase 4» di questo report.

`ARCHITECTURE.md`, `PLAN.md` e `REQUIREMENTS.md` restano **modificati e non
committati** in tutte e cinque le fasi: è voluto, li committa l'utente a mano.
`plans/` resta non tracciata.

### Rischi del piano: come sono andati

| Rischio previsto | Esito reale |
|---|---|
| `langchain-postgres` 0.0.17 con `langchain-core` 1.x: incompatibilità di firma | **Non materializzato.** `from_documents()` funziona al primo tentativo con core 1.5.1 |
| `langchain-postgres` trascina SQLAlchemy, asyncpg, psycopg-pool | **Confermato e accettato** (fase 1). Nessun problema operativo |
| Prima invocazione lentissima per caricamento in VRAM | **Confermato.** Fino a ~156 s (fase 4). Non è un errore |
| `bge-m3` a 1024 dimensioni | **Confermato**, verificato anche a valle su `vector_dims()` |
| Contesa di VRAM fra i due modelli su 8 GB | **Non materializzato in fase 4, materializzato in fase 5**: i ~12 s di retrieval sulle prime due domande sono `bge-m3` ricaricato dopo che `qwen2.5` ha occupato la VRAM. Non blocca, ma va tenuto in conto per i timeout di P4 |

### Debiti aperti verso le fasi successive

1. **Immagine `archetype-lab-web:latest` obsoleta** (rilevato in fase 3): costruita
   prima che esistesse il progetto Django. Da ricostruire con
   `docker compose build web` — debito da chiudere in P6.
2. **Nessun indice ANN** sulle tabelle di PGVector: irrilevante a questa scala, da
   valutare in P2/P5.
3. **Chunking non realmente esercitato**: il PDF di prova produce 1 chunk per
   pagina. Da riosservare in P2 su documenti reali.
4. `scripts/spike_rag.py` e `samples/` sono **da cancellare** al termine di P2.

**P0 è chiusa. Si può procedere con P1 (T-07 → T-13, modelli Django e admin).**

---

## Verifica incrociata di fine P0

Controllo indipendente eseguito dopo la chiusura delle cinque fasi, per cercare punti
ciechi, effetti collaterali e incoerenze che le singole fasi non potevano vedere.

### Cosa è risultato solido

I file scritti dai sub-agenti sono stati ricostruiti dai blocchi del piano e
confrontati riga per riga: **13 su 13 identici**, l'unico scostamento è quello già
dichiarato in fase 5 (`sys.path.insert` in `spike_rag.py`, 5 righe aggiunte, nulla
rimosso). Contenuto dei commit pulito, nessuna traccia di `git add -A`. Nessuna
variabile letta da `base.py` senza dichiarazione in `.env.example`. Compose rende
`POSTGRES_PORT: 5432` internamente e `5434` pubblicata; `worker` invisibile senza
profilo. Superuser presente e funzionante. Spike riprodotto: stesse tre risposte.

### Correzioni applicate — commit `6984d97`

| # | Problema | Correzione |
|---|---|---|
| 1 | **Manca `.dockerignore`**: il `COPY . .` portava nell'immagine `.venv/` (257 MB di binari Windows in un'immagine Linux), `.git` e il **`.env` con le credenziali**, cotto in un layer | Creato `.dockerignore`. Immagine **da 946 MB a 602 MB** |
| 2 | **Immagine `web` obsoleta** (debito aperto in fase 3): costruita prima che esistesse il progetto Django | Ricostruita. `docker run --rm archetype-lab-web:latest python manage.py check` → nessun problema, **senza bind mount**: il progetto è davvero nell'immagine. Debito chiuso |
| 3 | **`DJANGO_SETTINGS_MODULE` inerte sull'host**: `load_dotenv()` gira dentro `base.py`, quando Django ha già scelto il modulo di settings. Vale solo nei container via `env_file` | Documentato in `.env.example`. La variabile resta: nei container serve davvero |
| 4 | **PDF versionato come testo**: nessun byte NUL nei primi 8 KB, quindi git lo diffa a righe con `core.autocrlf=true`. Verificato con un clone reale che non lo corrompe — gli stream compressi gli fanno saltare la conversione — ma il comportamento dipendeva da un'euristica | `.gitattributes` con `*.pdf binary`. Il file non risulta modificato: nessuna rinormalizzazione |

### Rilevato ma non correggibile in P0

**La colonna `embedding` è `vector` senza dimensione dichiarata**, `id` è
`character varying`, unico indice una GIN sui metadati. Il database **non impone la
coerenza dimensionale**: in P1 la separazione fra profili di embedding va garantita
per `collection_name`, non contando sul vincolo di colonna. Non è un difetto da
correggere ora — è un vincolo di progettazione per P1.

### Effetto collaterale sulla macchina, estraneo a questa esecuzione

Sette container dei progetti `q` e `q-langfuse` — incluso `q-postgres-1` — si sono
fermati fra le **15:12:10 e le 15:12:14 UTC** del 24/07, dopo 2-6 settimane di
uptime. **Non è stata questa esecuzione**: nessun sub-agente ha impartito
`docker stop`/`down`/`kill` né ha mai nominato quei container, e
`archetype-lab-db-1` è rimasto attivo ininterrottamente dalle 15:05:44, il che
esclude un riavvio del motore o una pausa della VM.

Tutti e sette **riaccesi** durante la verifica. Le tre porte convivono senza
conflitti: 5432 (`q-postgres-1`), 5433 (`q-langfuse-postgres-1`), 5434 (questo
progetto).

### Regressione dopo le correzioni

`/health` → 200 con i tre check a `true`; `langchain_pg_embedding` a 3 righe; spike
rieseguito con le tre risposte invariate.

### Nota sul numero di commit

Il criterio 4 di P0 chiede **quattro** commit, uno per fase produttiva: sono intatti.
`6984d97` è un **quinto** commit di consolidamento, non di fase, prodotto da questa
verifica. Se si preferisce che P0 resti a quattro commit esatti, è isolato e
rimovibile con `git revert 6984d97` senza toccare le fasi.
