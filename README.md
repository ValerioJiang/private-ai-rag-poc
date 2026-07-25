# Sistema RAG in Django con LangChain e LLM privato

Backend Django che implementa un sistema RAG (Retrieval-Augmented Generation)
per rispondere a domande in linguaggio naturale sul contenuto di documenti PDF,
con generazione affidata a un **LLM privato eseguito in locale**.

Chi valuta il progetto trova in [**Prova guidata**](#prova-guidata) il percorso
più corto dall'installazione alla prima risposta, e in [**Criteri di
accettazione**](#criteri-di-accettazione) ciascuno dei dieci criteri con il modo
di verificarlo e l'esito rilevato. I [**Limiti noti**](#limiti-noti) sono
dichiarati in fondo, con i numeri misurati.

## Documentazione

| Documento | Contenuto |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Analisi funzionale: requisiti, casi d'uso, criteri di accettazione |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Scelte architetturali, alternative valutate, compromessi |
| [PLAN.md](PLAN.md) | Piano di lavoro per fasi |
| [BACKLOG.md](BACKLOG.md) | Scomposizione operativa in attività |

`plans/` conserva, per ogni fase, il piano, i prompt dei sub-agenti e il report
di esecuzione con le misure prese sul campo. È un registro storico e non viene
riscritto a posteriori: è lì che stanno le uscite reali dei comandi citati qui.

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
segue `settings.DEBUG` — il che durante lo sviluppo è comodo e in produzione non
è raccomandato (`--no-reload` per disattivarlo).

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

## Prova guidata

Dall'ambiente spento alla prima risposta con le fonti citate.

I tempi riportati qui sotto sono **misurati** il 25/07/2026 sulla macchina di
sviluppo con lo script di dimostrazione (T-41), e sono riportati per far
distinguere un'attesa normale da un guasto — non sono un impegno di prestazioni.
I tempi dei passi di installazione (`pip install`, `migrate`) non sono ancora
stati cronometrati: li compilerà la prova da zero su ambiente pulito (T-42, cfr.
[Criteri di accettazione](#criteri-di-accettazione)).

**1. I modelli, una volta sola.**

```bash
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3
ollama list          # devono comparire entrambi
```

**2. Database, dipendenze, schema.**

```bash
cp .env.example .env
docker compose up -d db
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

`migrate` applica le **cinque** migrazioni dell'app `rag` — l'ultima è
`0005_excerpt_length` — più quelle di Django e le **19** di
`django_tasks_database`, che sono di terze parti. La `0004` crea la
configurazione predefinita funzionante (RF-26): il sistema è utilizzabile senza
configurare nulla a mano.

**3. I due processi.**

```bash
python manage.py runserver      # terminale 1
python manage.py db_worker      # terminale 2
```

**4. I presupposti, in una richiesta.**

```bash
curl http://localhost:8000/health
```

Attesa: `"status": "ok"` e quattro voci — `database`, `pgvector`, `ollama`,
`coda` — tutte con `"ok": true`. `/health` è anonimo di proposito: è la sonda di
Compose. Se una voce è rossa il problema è lì, e i passi seguenti la
riprodurrebbero soltanto in forma meno leggibile.

**5. Il PDF di esempio.**

```bash
curl -u utente:password -F "file=@samples/manuale-dipendenti.pdf" \
     http://localhost:8000/api/documents/
```

Attesa: **202 Accepted**, documento in stato `pending`, zero pagine e zero
segmenti — la `POST` accoda, non indicizza. L'`id` che restituisce è quello da
interrogare finché lo stato non cambia:

```bash
curl -u utente:password http://localhost:8000/api/documents/<id>/
```

Attesa: `"status": "indexed"`, `"page_count": 3`, `"chunk_count": 3`.
**Misurato:** 1,96 s per la `POST`, e **17,13 s** dall'accodamento a `indexed`
sul worker a freddo, cioè comprensivi del caricamento del modello di embedding.
Rieseguendo lo stesso caricamento la risposta è **409** con
`documento_esistente`, e non viene creata alcuna riga né scritto alcun file
(RF-09).

**6. La prima domanda.**

```bash
curl -u utente:password -H "Content-Type: application/json" --max-time 300 \
     -d '{"domanda": "Quanti giorni di ferie si maturano all'\''anno?"}' \
     http://localhost:8000/api/ask/
```

Attesa: **200**, campo `risposta`, `fonti` con documento, pagina, estratto e
punteggio di ciascun segmento, e i due tempi separati `retrieval_ms` e
`generation_ms`. Nelle due esecuzioni di T-41 la risposta è stata identica —
«Si maturano 26 giorni di ferie all'anno.» — con tre fonti: p. 1 punteggio
**0,6831**, p. 3 **0,4577**, p. 2 **0,3725**.

**Misurato:** la prima domanda dopo l'avvio è costata **180,78 s**, di cui
**177,9 s** di sola generazione — è il caricamento del modello in VRAM, e si
paga una volta per processo. A caldo la stessa domanda è costata **4,17 s**
(recupero 1 044 ms, generazione 1 380 ms). È la ragione del `--max-time 300`:
cfr. [Limiti noti](#limiti-noti).

### Tutto insieme: `scripts/dimostrazione.ps1`

Con l'ambiente già avviato, i passi da 4 a 6 più la domanda fuori tema e
l'elenco delle configurazioni, in un unico script che cronometra ogni passo,
verifica il criterio che quel passo dimostra ed esce con codice diverso da zero
se uno non regge:

```powershell
.\scripts\dimostrazione.ps1 -Utente <utente> -Password <password>
```

Nessuna credenziale è scritta nel file: utente e password arrivano da parametro.
Lo script è **rieseguibile**: alla seconda esecuzione il caricamento riceve 409 e
prosegue sul documento già presente. Con `-TentativiMax 5` il polling si arrende
in dieci secondi invece che in due minuti, ed è il modo di vedere il messaggio
che nomina il worker fermo.

Le due esecuzioni misurate il 25/07/2026:

| Passo | A — modello freddo | B — seconda consecutiva |
|---|---|---|
| `GET /health` | 4,93 s | 4,84 s |
| `POST /api/documents/` | 1,96 s (**202**) | 1,89 s (**409**) |
| attesa dell'indicizzazione | 17,13 s | 1,66 s (già `indexed`) |
| domanda pertinente | 180,78 s | 4,17 s |
| domanda fuori tema | 4,48 s | 3,81 s |
| `GET /api/pipelines/` | 1,84 s | 1,79 s |
| **totale** | **211,12 s** | **18,16 s** |

Il rapporto fra i due totali — 211 s contro 18 s — è quasi interamente il primo
caricamento del modello di generazione.

Lo script è **solo PowerShell**, per la ragione dichiarata fra i
[limiti noti](#limiti-noti); la via portabile sono i `curl` della sezione
[API](#api), che coprono gli stessi endpoint.

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
curl -u utente:password -H "Content-Type: application/json" --max-time 300 \
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

`--max-time 300` sulle interrogazioni non è prudenza eccessiva, ed è **salito da
180 s** dopo una misura: la prima richiesta di un processo appena avviato deve
caricare il modello in VRAM, e in T-41 sono stati misurati **177,9 s di sola
generazione** sulla prima domanda a modello freddo — cioè appena sotto il limite
di 180 s che questo README indicava prima, che quindi era troppo stretto. A
caldo si sta sotto i 3 s di generazione (1 380 ms misurati).

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

## Test

```bash
docker compose up -d db
pytest
```

**29 test, 10,44 s** — misurato il 25/07/2026 alla chiusura di T-38.

I test **richiedono PostgreSQL** e **non richiedono Ollama**, e le due cose hanno
ragioni diverse.

Il database serve perché la migrazione `0001` esegue `CREATE EXTENSION vector`:
su SQLite non esiste, e sostituire il database significherebbe provare un sistema
diverso da quello che si consegna. `pytest-django` crea e distrugge da sé
`test_ragdb` con le credenziali di `.env`; il ruolo `rag` di `docker-compose.yml`
è superuser del cluster — **verificato**, `rolsuper = t` — quindi non serve alcun
`ALTER ROLE` e nessun passo in più rispetto all'[avvio](#avvio).

Ollama non serve perché tutto ciò che parla con la rete passa da
`rag/services/factories.py`, la cerniera dell'architettura (ARCHITECTURE §3): i
test sostituiscono quei pochi nomi con un finto LLM e un finto vector store. Non
è un'affermazione ma una **controprova misurata**: puntando il client di
inferenza su una porta chiusa

```powershell
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:1'
pytest -q          # 29 passed in 10.39s
```

la suite passa identica. Puntare a una porta chiusa è una prova più forte che
spegnere Ollama, perché copre anche un indirizzo eventualmente cablato in un
percorso diverso da quello atteso.

I test sono scritti in stile pytest — funzioni, `assert`, fixture — quindi
**`manage.py test` non li raccoglie**: il comando è `pytest`. `pytest.ini` non
ha `--reuse-db` di proposito: un database riusato non applicherebbe una
migrazione nuova, e i test fallirebbero con una colonna mancante e nessun indizio
sul perché. Chi ripete la suite molte volte lo aggiunge da riga di comando,
sapendo che dopo ogni migrazione serve `--create-db`.

Cosa coprono, nei tre file di `rag/tests/`:

| File | Copre |
|---|---|
| `test_segmentazione_e_factory.py` | 11 test — la segmentazione e le factory seguono la configurazione (RF-19, RF-22), i provider non attivabili sollevano un errore dichiarato (RNF-01), la chiave della cache segue i **valori** e non gli id |
| `test_ingestione.py` | 9 test — la macchina a stati completa, i casi di errore persistiti (RF-06, RF-10), la reindicizzazione idempotente, la deduplica, l'accodamento |
| `test_api_ask.py` | 9 test — `POST /api/ask/` con LLM sostituito: fonti e punteggi (RF-13), non-risposta senza interrogare l'LLM (RF-14), `QueryLog` coi tempi separati (RF-16), 401/404/500 |

## Criteri di accettazione

I dieci criteri di [REQUIREMENTS.md §7](REQUIREMENTS.md#7-criteri-di-accettazione),
con il modo di verificarli e l'esito rilevato. Dove l'esito dice **da compilare**
la prova non è ancora stata eseguita, e la riga non va letta come superata.

| # | Criterio | Come verificarlo | Esito rilevato |
|---|---|---|---|
| **CA-1** | L'ambiente si avvia da zero seguendo il solo README | Macchina pulita: `docker compose down -v`, `.venv` ricostruito, poi [Avvio](#avvio) e [Prova guidata](#prova-guidata) senza supplire con conoscenza pregressa | **Da compilare dopo T-42.** Un solo presupposto è già misurato: il ruolo `rag` è superuser, quindi `pytest` non richiede passi aggiuntivi |
| **CA-2** | Un PDF caricato passa a *indicizzato* con pagine e segmenti | Passo 5 della prova guidata, oppure `scripts\dimostrazione.ps1` (passo 3), oppure l'admin | **Superato** via API e worker: documento 62 `indexed`, **3 pagine, 3 segmenti** in 17,13 s (T-41). Coperto anche da `test_un_pdf_con_testo_arriva_a_indicizzato`, e verificato dall'admin in P2 con `django.test.Client` — stessa pila, senza rendering visivo. La lettura in un **browser** resta a T-42 |
| **CA-3** | Una domanda sul contenuto riceve una risposta con le fonti | Passo 6 della prova guidata, oppure `dimostrazione.ps1` (passo 4), che fallisce se le fonti sono zero | **Superato:** «Si maturano 26 giorni di ferie all'anno.» con 3 fonti — p. 1 **0,6831**, p. 3 0,4577, p. 2 0,3725 — e i tempi separati (recupero 1 044 ms, generazione 1 380 ms). Coperto anche da `test_una_domanda_pertinente_riceve_risposta_e_fonti` |
| **CA-4** | Una domanda fuori contenuto ottiene la non-risposta | `dimostrazione.ps1` (passo 5), che **dichiara quale** dei due meccanismi ha agito | **Superato, ma non dal meccanismo che ci si aspetta**: cfr. il riquadro qui sotto. La dichiarazione di non conoscenza arriva; in configurazione predefinita la produce il **prompt di sistema**, non la soglia |
| **CA-5** | Temperatura o prompt modificati cambiano la risposta, senza riavvio | Admin → `LLMProfile.temperature` o `PromptTemplate.text`, poi ripetere il passo 6 | **Superato in P3** con criterio stretto: temperatura cambiata dall'admin su un `runserver` in un **processo separato** — a 0 due esecuzioni danno lo stesso testo, a 1.8 testi diversi, senza riavvio. Da ripetere in T-42 sull'ambiente pulito |
| **CA-6** | Cambiando i segmenti recuperati cambia il numero di fonti | Admin → `RetrievalProfile.top_k`, poi ripetere il passo 6 | **Superato in P4 e P5:** `top_k` cambiato da un **terzo** processo porta le fonti da 4 a 2 e **di nuovo a 4**, coi pid di server e worker invariati. Il ritorno al valore iniziale esclude che il numero dipendesse dai segmenti disponibili |
| **CA-7** | Due pipeline sulla stessa base danno risposte diverse | `GET /api/pipelines/`, poi `POST /api/ask/` con `pipeline` esplicita | **Superato in P4:** due pipeline che differiscono **solo** per il prompt danno risposte diverse sulle stesse fonti |
| **CA-8** | Un PDF corrotto o solo immagine va in *fallito* con motivo | Caricare un PDF di sole immagini, poi `GET /api/documents/{id}/` | **Superato:** `202` e poi `failed` con `error_message` leggibile (P5, con `curl` vero). Coperto dai due casi di `test_un_pdf_non_indicizzabile_…` — scansione senza OCR e file illeggibile — che verificano stato **e** motivo persistiti. Verificato dall'admin in P2 con `django.test.Client`; la lettura in un **browser** resta a T-42 |
| **CA-9** | Nessuna chiamata di rete verso servizi terzi | Staccare **tutte** le interfacce di rete e rifare il ciclo completo: caricamento, indicizzazione, domanda pertinente, domanda fuori tema (ARCHITECTURE §9) | **Da compilare dopo T-43.** Ciò che è già misurato riguarda i soli test, non il sistema in esercizio: la suite passa col client di inferenza su una porta chiusa |
| **CA-10** | La suite di test passa | `docker compose up -d db` e poi `pytest` | **Superato:** **29 passed in 10,44 s**, e **29 passed in 10,39 s** con `OLLAMA_BASE_URL` puntato su una porta chiusa |

> **CA-4: quale meccanismo lo regge davvero.** Il criterio è soddisfatto, ma
> l'origine della non-risposta va detta, perché chi valuta la scoprirebbe da sé.
> Verificato sul sorgente di `_recupera()` in `rag/services/query.py`: la
> `score_threshold` filtra **solo** nella strategia `similarity_score_threshold`,
> e la pipeline predefinita usa `similarity`. Su una domanda fuori tema tornano
> quindi **3 segmenti** con rilevanza 0,2192 / 0,1946 / 0,1659 e `generata: true`:
> a produrre la dichiarazione di non conoscenza è il **prompt di sistema**, non
> il filtro di RF-14. Il filtro esiste, funziona ed è provato da
> `test_sotto_soglia_si_dichiara_di_non_sapere_senza_interrogare_l_llm` — che
> verifica anche che l'LLM **non venga invocato**, `generation_ms: 0` — ma si
> attiva solo scegliendo quella strategia dall'admin. La differenza è sostanziale:
> la prima strada è una garanzia del codice, la seconda dipende dal modello.

## Limiti noti

Dichiarati con la loro misura dove ce n'è una. Un limite noto pesa meno di una
funzionalità presente ma non funzionante.

**Recupero e generazione**

- **La soglia di pertinenza non agisce nella pipeline predefinita.** Filtra solo
  con la strategia `similarity_score_threshold`; con `similarity` i segmenti
  arrivano comunque all'LLM. Cfr. il riquadro su CA-4.
- **Prima richiesta di ogni processo a freddo.** Misurati **177,9 s** di sola
  generazione sulla prima domanda (T-41) e **30,2 s** su una singola richiesta in
  P4: è il limite inferiore per i timeout dei client, ed è la ragione del
  `--max-time 300`. A caldo, 1 380 ms.
- **`_memoizza()` non è protetto fra thread.** Non è un problema di correttezza —
  la chiave della cache contiene i *valori* della configurazione, non gli id,
  quindi due processi non possono servire configurazione stantia (verificato
  attraverso tre processi in P5) — ma un costo: il caricamento a freddo si paga
  **una volta per processo**, e il worker è sempre il secondo a pagarlo.
- **Nessuna valutazione quantitativa della qualità delle risposte.** Senza un
  dataset di riferimento sarebbe un numero senza significato; i `QueryLog`
  conservano la materia prima per costruirla (ARCHITECTURE §8.3).

**Coda e indicizzazione**

- **Nessun retry automatico dei task falliti**: si riprova con l'azione
  «Reindicizza» dall'admin, oppure `manage.py ingest`.
- **Nessun lucchetto contro il doppio accodamento**: due accodamenti dello stesso
  documento sprecano lavoro senza perdere correttezza, perché l'upsert su pgvector
  è per id deterministico (ARCHITECTURE §7.5).
- **Worker a freddo 12,4 s contro 2,7 s a caldo** sullo stesso documento
  (misurato in P5), più ~8,4 s di avvio del processo prima che il primo task
  parta.
- **La tabella `DBTaskResult` cresce** a ogni indicizzazione e non si pota da
  sola: `manage.py prune_db_task_results`.
- **Sostituire il file di un documento esistente lascia il precedente in
  `MEDIA_ROOT`.** La cancellazione del documento invece porta via file e vettori
  (RF-08, chiuso in P5).

**API e interfaccia**

- **Nessuna paginazione su `GET /api/documents/`**: l'elenco torna intero.
- **Basic auth su HTTP.** Adeguato a un uso locale; fuori da locale richiederebbe
  TLS. Non si usa `rest_framework.authtoken` perché porterebbe quattro migrazioni
  e una tabella di token che in questa prova nessuno emette né ruota.
- **L'admin di `django_tasks_db` è di terze parti e in inglese**, e compare
  accanto a quelli del progetto, che sono interamente in italiano. Resta visibile
  per scelta: nasconderlo con `admin.site.unregister()` toglierebbe l'unico punto
  in cui lo stato della coda si vede dall'interfaccia.
- **Nessuna gestione multi-utente sui documenti**: ogni utente autenticato vede
  l'intera base di conoscenza.
- **`LLMProfile.base_url` è modificabile dall'admin.** È ciò che rende il sistema
  configurabile ed è anche l'unica falla residua nella garanzia di non
  esfiltrazione: un amministratore può puntare l'inferenza a un host arbitrario.
  In produzione servirebbe una allow-list (ARCHITECTURE §8.2 e §9).

**Ambiente e strumenti**

- **Lo script di dimostrazione è solo PowerShell.** Non esiste un gemello `.sh`:
  la macchina di consegna è Windows, e uno script mai eseguito è peggio della sua
  assenza. La via portabile sono i `curl` della sezione [API](#api).
- **Su Windows il launcher del virtualenv raddoppia i processi.** Misurato in P5:
  `.venv\Scripts\python.exe` ri-esegue l'interprete di base come processo
  **figlio**, quindi `runserver` e `db_worker` compaiono due volte anche con
  `--noreload`. Il pid che serve le richieste e scrive i log è il figlio; non è
  un worker duplicato.
- **PDF scansionati non supportati.** PyMuPDF estrae testo, non fa OCR: il caso è
  rilevato e segnalato con un errore esplicito, non produce un documento vuoto.

**Fuori scope, dichiarato**

Interfaccia utente (esclusa dalla traccia), formati diversi dal PDF, OCR, memoria
conversazionale multi-turno, ricerca ibrida BM25 + vettoriale, reranking,
streaming SSE, multi-tenancy e ACL a livello di segmento, deployment in
produzione. Elenco completo in [REQUIREMENTS.md §8](REQUIREMENTS.md) e
[ARCHITECTURE.md §10](ARCHITECTURE.md).

## Licenza

Progetto realizzato come prova tecnica.
