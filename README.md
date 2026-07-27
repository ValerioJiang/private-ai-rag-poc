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

I comandi sono scritti per **Windows PowerShell**, che è la macchina di
consegna; per Linux/macOS la traduzione è annotata riga per riga.

```powershell
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3

cp .env.example .env            # `cp` in PowerShell è un alias di Copy-Item
docker compose up -d db

python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

E, **in un secondo terminale**, il worker che indicizza i documenti:

```powershell
python manage.py db_worker
```

`createsuperuser` è interattivo. Chi automatizza — script di collaudo, CI —
usa la variante non interattiva, che prende le credenziali dall'ambiente:

```powershell
$env:DJANGO_SUPERUSER_USERNAME = "dimostrazione"
$env:DJANGO_SUPERUSER_EMAIL    = "dimostrazione@example.invalid"
$env:DJANGO_SUPERUSER_PASSWORD = "..."
python manage.py createsuperuser --noinput
```

La radice http://localhost:8000/ smista per ruolo: chi non ha una sessione
finisce sul login `/accedi/`, chi amministra sull'admin `/admin/`, chiunque
altro sulla pagina di interrogazione `/chiedi/` — cfr. [Interfaccia
web](#interfaccia-web). Stato del servizio su `/health`.

Il database è pubblicato sulla porta **5434**, non sulla 5432: le porte
consuete sono spesso già occupate da altri stack. Il valore sta in
`.env.example`, quindi i comandi qui sopra funzionano così come sono; serve
saperlo solo per collegarsi al database dall'esterno. Dentro la rete di Compose
vale invece la porta interna 5432.

### `curl` su Windows PowerShell: si scrive `curl.exe`

Tre differenze che fanno fallire i comandi di questo README se si copiano nella
forma bash. Sono **misurate** sulla macchina di consegna (PowerShell 5.1) durante
la prova da zero di T-42, non dedotte: sono state la scoperta di quella prova, e
sono la ragione per cui è stata rifatta da capo.

1. **`curl` è un alias di `Invoke-WebRequest`**, non il programma `curl`.
   `curl -u utente:password …` risponde *«the parameter name 'u' is ambiguous»* e
   non parte alcuna richiesta. Il programma c'è — `C:\windows\system32\curl.exe`
   — e va invocato **con l'estensione**: `curl.exe`. Su Linux/macOS `curl` va
   bene così com'è.
2. **La continuazione di riga è il backtick `` ` ``, non `\`.** Una `\` a fine
   riga spezza il comando e curl riceve i pezzi come URL separati.
3. **Le virgolette doppie dentro un corpo JSON vanno protette con `\"`**, e
   l'apostrofo dentro una stringa fra apici singoli si raddoppia. La forma bash
   `-d '{"domanda": "…all'\''anno?"}'` in PowerShell è tornata con cinque
   `HTTP 000` ed exit 3; la forma che funziona è
   `-d '{\"domanda\": \"…all''anno?\"}'`.

I blocchi che seguono sono già scritti in questa forma. Chi legge da Linux o
macOS toglie l'estensione, sostituisce i backtick con `\` e usa il quoting bash.

### Il worker, e come farne a meno

I processi sono **due**: il server risponde alle richieste, il worker indicizza.
L'indicizzazione di un PDF costa secondi — fino a una dozzina alla prima
esecuzione di ogni processo, che deve caricare il modello di embedding — e non
sta dentro il ciclo richiesta/risposta: il caricamento risponde subito, il lavoro
avviene dopo.

La coda vive in PostgreSQL, quindi non c'è alcun servizio in più da avviare: il
worker è `python manage.py db_worker` sull'host, oppure, in Compose,

```powershell
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

```powershell
python manage.py prune_db_task_results
```

## Prova guidata

Dall'ambiente spento alla prima risposta con le fonti citate.

I tempi riportati qui sotto sono **misurati** sulla macchina di sviluppo — quelli
di esercizio il 25/07/2026 con lo script di dimostrazione (T-41), quelli di
installazione il 26/07/2026 durante la prova da zero su ambiente pulito (T-42).
Servono a far distinguere un'attesa normale da un guasto: non sono un impegno di
prestazioni.

**1. I modelli, una volta sola.**

```powershell
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3
ollama list          # devono comparire entrambi
```

**2. Database, dipendenze, schema.**

```powershell
cp .env.example .env
docker compose up -d db
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

`migrate` applica le **sei** migrazioni dell'app `rag` — l'ultima è
`0006_limiti_di_ammissione`, additiva e con i default che lasciano i controlli
spenti — più quelle di Django e le **19** di
`django_tasks_database`, che sono di terze parti. La `0004` crea la
configurazione predefinita funzionante (RF-26): il sistema è utilizzabile senza
configurare nulla a mano.

Quanto costa questo passo, **misurato in T-42** su volume del database e
virtualenv appena ricreati (`docker compose down -v`, `.venv` cancellata):

| Comando | Tempo |
|---|---|
| `ollama pull` dei due modelli | 0,92 s + 0,73 s — **già scaricati**: la prima volta sono 5,9 GB di rete |
| `docker compose up -d db` | 1,35 s (il comando torna subito; il contenitore diventa *healthy* in pochi secondi) |
| `python -m venv .venv` | 13,81 s |
| `pip install -r requirements.txt` | **125,71 s**, con la cache dei wheel già popolata; senza cache va aggiunto il download di 58 pacchetti |
| `python manage.py migrate` | **9,38 s** — 45 migrazioni allora, 46 da quando c'è la `0006`; `CREATE EXTENSION vector` compresa |
| `createsuperuser --noinput` | 3,99 s |
| avvio di `runserver` fino al primo `/health` utile | 5,54 s |

Sono i tempi del **secondo** giro della prova, quello eseguito sul README
corretto; il primo giro aveva dato 22,89 s per `venv` e 172,20 s per `pip`, sulla
stessa macchina e con le stesse cache. La differenza è rumore di macchina, non
un effetto delle correzioni: si legga l'ordine di grandezza, non la cifra.

**3. I due processi.**

```powershell
python manage.py runserver      # terminale 1
python manage.py db_worker      # terminale 2
```

**4. I presupposti, in una richiesta.**

```powershell
curl.exe --max-time 30 http://localhost:8000/health
```

Attesa: `"status": "ok"` e quattro voci — `database`, `pgvector`, `ollama`,
`coda` — tutte con `"ok": true`. `/health` è anonimo di proposito: è la sonda di
Compose. Se una voce è rossa il problema è lì, e i passi seguenti la
riprodurrebbero soltanto in forma meno leggibile.

**5. Il PDF di esempio.**

```powershell
curl.exe --max-time 30 -u utente:password `
     -F "file=@samples/manuale-dipendenti.pdf" http://localhost:8000/api/documents/
```

Attesa: **202 Accepted**, documento in stato `pending`, zero pagine e zero
segmenti — la `POST` accoda, non indicizza. L'`id` che restituisce è quello da
interrogare finché lo stato non cambia:

```powershell
curl.exe --max-time 30 -u utente:password http://localhost:8000/api/documents/<id>/
```

Attesa: `"status": "indexed"`, `"page_count": 3`, `"chunk_count": 3`.
**Misurato:** 1,96 s per la `POST`, e **17,13 s** dall'accodamento a `indexed`
sul worker a freddo, cioè comprensivi del caricamento del modello di embedding.
Rieseguendo lo stesso caricamento la risposta è **409** con
`documento_esistente`, e non viene creata alcuna riga né scritto alcun file
(RF-09).

**6. La prima domanda.**

```powershell
curl.exe --max-time 300 -u utente:password -H "Content-Type: application/json" `
     -d '{\"domanda\": \"Quanti giorni di ferie si maturano all''anno?\"}' `
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
[limiti noti](#limiti-noti); l'alternativa sono i `curl` della sezione
[API](#api), che coprono gli stessi endpoint uno per uno e si traducono in bash
con le tre regole del [riquadro qui sopra](#curl-su-windows-powershell-si-scrive-curlexe),
lette al contrario.

## Interfaccia web

Oltre all'admin il progetto serve quattro rotte fuori da `/api/` — due pagine e
due rimandi — e nessuna di esse aggiunge un endpoint di dominio: a rispondere
resta `POST /api/ask/`.

| Rotta | Cosa fa |
|---|---|
| `/` | Non rende nulla, smista: anonimo → `/accedi/`, `is_staff` → `/admin/`, utente ordinario → `/chiedi/` |
| `/accedi/` | Login **per tutti**, non solo per chi amministra; dopo l'accesso smista con lo stesso criterio, salvo un `next` esplicito, che ha la precedenza |
| `/esci/` | Logout. È un **POST** — da Django 5 `LogoutView` non accetta più il GET — quindi nei template è un form, non un collegamento |
| `/chiedi/` | La pagina che pone la domanda. Richiede sessione (`login_required`); interroga `POST /api/ask/` dal browser, e `GET /api/pipelines/` per l'elenco delle configurazioni |

**`/accedi/` esiste perché prima non si poteva entrare.** `LOGIN_URL` puntava ad
`admin:login`, che è il login *dell'admin*: `AdminAuthenticationForm` rifiuta chi
non ha `is_staff`, quindi un utente ordinario non aveva alcuna porta — nemmeno
per raggiungere `/chiedi/`, che è fatta per lui. Ora `LOGIN_URL` e
`LOGOUT_REDIRECT_URL` valgono `accedi`. Lo smistamento è **instradamento, non
autorizzazione**: nessuno guadagna un permesso che non aveva, e un utente
ordinario che digitasse `/admin/` viene respinto da Django come prima. Lo
smistamento è stato **provato su entrambi i ruoli**, chi amministra e chi no.

Dall'admin il collegamento «Visualizza sito» porta ora a `/chiedi/`: prima stava
a `None` — cioè non compariva — perché la radice non era instradata e avrebbe
dato un 404. Per chi amministra «vedere il sito» significa vedere ciò che vede
l'utente, non tornare all'admin da cui è appena uscito.

Le pagine non caricano nulla dall'esterno — niente CDN, niente font remoti,
nessuna libreria: **verificato**, zero riferimenti esterni nelle pagine rese
(RNF-01). La tavolozza condivisa sta in `templates/rag/_tema.html` ed è
**inclusa** nel template, non servita come file statico, così ogni pagina resta
**una sola richiesta**: è la proprietà da cui dipende la prova a rete staccata di
T-43.

## API

Tutti gli endpoint sotto `/api/` richiedono autenticazione (Basic o sessione);
`/health` è anonimo di proposito, perché è la sonda del Compose.

```powershell
# Caricamento di un PDF — risponde 202 e mette il documento in coda
curl.exe --max-time 30 -u utente:password `
     -F "file=@samples/manuale-dipendenti.pdf" http://localhost:8000/api/documents/

# Stato del documento: e' qui che si scopre com'e' finita
curl.exe --max-time 30 -u utente:password http://localhost:8000/api/documents/55/

# Elenco, filtrabile per stato
curl.exe --max-time 30 -u utente:password "http://localhost:8000/api/documents/?status=indexed"

# Interrogazione
curl.exe --max-time 300 -u utente:password -H "Content-Type: application/json" `
     -d '{\"domanda\": \"Quanti giorni di ferie si maturano?\"}' `
     http://localhost:8000/api/ask/

# Configurazioni disponibili
curl.exe --max-time 30 -u utente:password http://localhost:8000/api/pipelines/
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
**400** file mancante o non PDF, base di conoscenza inesistente, oppure un
[limite di ammissione](#limiti-di-ammissione-dei-pdf) superato, **409** stesso
contenuto già presente (in questo caso non viene creata alcuna riga né scritto
alcun file). Il **409 conserva la precedenza** sui limiti — a chi ricarica lo
stesso file si risponde «ce l'hai già», non «è troppo grande» — e con
`max_page_count` attivo il confine fra 400 e worker si sposta di un caso: è
dichiarato fra i [limiti noti](#limiti-noti).

`--max-time 300` sulle interrogazioni non è prudenza eccessiva, ed è **salito da
180 s** dopo una misura: la prima richiesta di un processo appena avviato deve
caricare il modello in VRAM, e in T-41 sono stati misurati **177,9 s di sola
generazione** sulla prima domanda a modello freddo — cioè appena sotto il limite
di 180 s che questo README indicava prima, che quindi era troppo stretto. A
caldo si sta sotto i 3 s di generazione (1 380 ms misurati).

**`GET /api/ask/` non risponde a domande**: rimanda (302) a `/chiedi/`, la pagina
dell'[interfaccia web](#interfaccia-web). Prima era un `405 Method Not Allowed`
— corretto per un endpoint di sola scrittura, un vicolo cieco per chi ci arriva
col browser. Il rimando non richiede sessione, perché non espone nulla; il `POST`
è invariato in tutto: autenticazione, corpo e codici di risposta.

## Uso da riga di comando

Le stesse operazioni disponibili dall'admin esistono come comandi di gestione,
per prova e automazione:

```powershell
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

## Limiti di ammissione dei PDF

Tre limiti facoltativi, per base di conoscenza, nell'admin sotto **«Limiti di
ammissione»** di `KnowledgeBase` (migrazione `0006`). Come ogni altro parametro
di comportamento sono righe di database e non costanti nel codice (RF-22).

| Campo | Effetto | Predefinito |
|---|---|---|
| `max_file_size_mb` | Oltre questa dimensione il caricamento è respinto subito | **0** — spento |
| `max_page_count` | Oltre questo numero di pagine il caricamento è respinto subito | **0** — spento |
| `min_text_page_ratio` | Sotto questa quota di pagine con testo estraibile il documento va in *fallito*, col conteggio nel motivo | **0.0** — spento |

**Zero disattiva il controllo**, campo per campo. Le installazioni esistenti —
compresa la base di conoscenza creata dalla `0004` — mantengono così esattamente
il comportamento con cui P2 → P6 hanno misurato, e nessuna cifra dei report
precedenti diventa incomparabile: il comportamento nuovo si ottiene
scegliendolo.

I primi due sono **sincroni** e li verifica un solo punto —
`verifica_ammissibilita()` in `rag/services/validation.py` — chiamato dai **tre**
inneschi che accettano un file *nuovo*, sempre **dopo** la deduplica:

| Innesco | Esito quando un limite non è rispettato |
|---|---|
| `POST /api/documents/` | **400** col motivo in `detail`; nessuna riga creata, nessun file scritto |
| `manage.py ingest <file>` | `CommandError` leggibile, uscita 1, nessuna riga creata |
| Salvataggio dall'admin | Errore di validazione sul campo *file*: il modulo non si salva |

L'azione «Reindicizza» **non** valida, ed è deliberato: non riceve alcun file
nuovo, rilegge dal disco un documento già accettato, e abbassare un limite non
deve far fallire il riesame di ciò che è già in archivio. Per la stessa ragione i
documenti già indicizzati restano tali anche se non passerebbero i limiti
attuali.

`min_text_page_ratio` è invece **asincrono**, e non poteva essere altrimenti:
sapere quante pagine contengono testo significa estrarlo, cioè fare il lavoro del
worker. Sotto quota il documento finisce in `failed` col motivo, e si legge da
`GET /api/documents/{id}/` come ogni altro fallimento. Serve contro le scansioni
**parziali**: se *nessuna* pagina ha testo interviene prima il controllo di
RF-10, che mantiene la precedenza e il suo messaggio sull'OCR. `page_count` resta
il totale delle pagine del **file**, non di quelle con testo (CA-2).

Cosa è **verificato**: i 14 test di `rag/tests/test_validazione.py`, e
`manage.py ingest` su un PDF di 3 pagine con `max_page_count = 2` — `CommandError`
leggibile, uscita 1, nessuna riga creata. Cosa **non** lo è: il ciclo completo per
via HTTP con worker e Ollama veri, e il rifiuto dall'admin guardato in un
browser. Sono verifiche **da fare**, e finché non sono state fatte qui non
compare alcun tempo.

## Test

```powershell
docker compose up -d db
pytest
```

**45 test.** Erano 29, cronometrati in **10,44 s** il 25/07/2026 alla chiusura di
T-38; i 16 aggiunti da T-44 sono verdi, ma la suite non è stata ricronometrata —
quei 10,44 s valgono per le 29 di allora e non sono un dato aggiornato.

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
pytest -q          # 29 passed in 10.39s; con i 45 di oggi, tutti verdi
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

Cosa coprono, nei quattro file di `rag/tests/`:

| File | Copre |
|---|---|
| `test_segmentazione_e_factory.py` | 11 test — la segmentazione e le factory seguono la configurazione (RF-19, RF-22), i provider non attivabili sollevano un errore dichiarato (RNF-01), la chiave della cache segue i **valori** e non gli id |
| `test_ingestione.py` | 11 test — la macchina a stati completa, i casi di errore persistiti (RF-06, RF-10), la reindicizzazione idempotente, la deduplica, l'accodamento, e la scansione parziale sotto `min_text_page_ratio` (T-44) |
| `test_validazione.py` | 14 test — i [limiti di ammissione](#limiti-di-ammissione-dei-pdf) (T-44): conteggio delle pagine senza estrarre il testo, limiti spenti che non aprono nemmeno il PDF, il caso esattamente al limite, il puntatore riavvolto dopo la lettura, la `POST` che risponde 400 senza creare nulla, il modulo dell'admin che respinge e il file ammesso che si salva intero |
| `test_api_ask.py` | 9 test — `POST /api/ask/` con LLM sostituito: fonti e punteggi (RF-13), non-risposta senza interrogare l'LLM (RF-14), `QueryLog` coi tempi separati (RF-16), 401/404/500 |

## Criteri di accettazione

I dieci criteri di [REQUIREMENTS.md §7](REQUIREMENTS.md#7-criteri-di-accettazione),
con il modo di verificarli e l'esito rilevato. **Sono superati tutti e dieci**, e
per ciascuno è scritto *come* — comando, misura, data. Due portano una riserva
esplicita, in riga e non in nota: **CA-4** è retto dal prompt di sistema e non
dalla soglia (riquadro sotto la tabella), e **CA-2** e **CA-8** sono stati
verificati sull'admin servito via HTTP con sessione autenticata, non guardato in
un browser. Dichiararle è parte dell'esito.

| # | Criterio | Come verificarlo | Esito rilevato |
|---|---|---|---|
| **CA-1** | L'ambiente si avvia da zero seguendo il solo README | Macchina pulita: `docker compose down -v`, `.venv` ricostruito, poi [Avvio](#avvio) e [Prova guidata](#prova-guidata) senza supplire con conoscenza pregressa | **Superato al secondo giro** (T-42, 26/07/2026). Il primo giro ha scoperto **tre difetti**, tutti nel modo in cui il README scriveva i `curl` per una macchina Windows: `curl` alias di `Invoke-WebRequest`, continuazione di riga `\`, quoting del corpo JSON. Corretti — cfr. [`curl` su Windows PowerShell](#curl-su-windows-powershell-si-scrive-curlexe) — e la sequenza è stata rieseguita da capo dall'azzeramento: volume, `media/` e `.venv` ricreati, e dall'ambiente spento alla prima risposta con le fonti **nessun passo implicito**. La sola aggiunta, dichiarata, è la variante non interattiva di `createsuperuser`, ora documentata |
| **CA-2** | Un PDF caricato passa a *indicizzato* con pagine e segmenti | Passo 5 della prova guidata, oppure `scripts\dimostrazione.ps1` (passo 3), oppure l'admin | **Superato** via API e worker: documento 62 `indexed`, **3 pagine, 3 segmenti** in 17,13 s (T-41), e ripetuto sull'ambiente ricostruito di T-42 — documento 1, stesse 3 pagine e 3 segmenti, **7,50 s** dall'accodamento a `indexed` con worker a freddo. Coperto anche da `test_un_pdf_con_testo_arriva_a_indicizzato`. **Nell'admin:** la changelist `/admin/rag/document/`, richiesta al `runserver` vivo con una sessione autenticata vera (login sul form, cookie `sessionid`), riporta la riga «manuale-dipendenti.pdf · Base di conoscenza predefinita · Indicizzato · 3 · 3». È HTML servito dall'applicazione, **non** una pagina guardata in un browser: quella lettura visiva non è stata fatta, e non va data per fatta |
| **CA-3** | Una domanda sul contenuto riceve una risposta con le fonti | Passo 6 della prova guidata, oppure `dimostrazione.ps1` (passo 4), che fallisce se le fonti sono zero | **Superato:** «Si maturano 26 giorni di ferie all'anno.» con 3 fonti — p. 1 **0,6831**, p. 3 0,4577, p. 2 0,3725 — e i tempi separati (recupero 1 044 ms, generazione 1 380 ms). **Riprodotto identico** sull'ambiente ricostruito di T-42, stessa risposta e stessi tre punteggi alla quarta cifra, su un database creato da zero. Coperto anche da `test_una_domanda_pertinente_riceve_risposta_e_fonti` |
| **CA-4** | Una domanda fuori contenuto ottiene la non-risposta | `dimostrazione.ps1` (passo 5), che **dichiara quale** dei due meccanismi ha agito | **Superato, ma non dal meccanismo che ci si aspetta**: cfr. il riquadro qui sotto. La dichiarazione di non conoscenza arriva; in configurazione predefinita la produce il **prompt di sistema**, non la soglia. Confermato in T-42 sull'ambiente pulito: «Non dispongo di questa informazione nei documenti forniti.» con 3 segmenti passati all'LLM, punteggi **0,2192 / 0,1946 / 0,1659** — gli stessi di T-41 |
| **CA-5** | Temperatura o prompt modificati cambiano la risposta, senza riavvio | Admin → `LLMProfile.temperature` o `PromptTemplate.text`, poi ripetere il passo 6 | **Superato in P3 e ripetuto in T-42** sull'ambiente pulito, con criterio stretto: `LLMProfile.temperature` cambiata da un **terzo** processo, su server e worker mai riavviati (pid invariati prima e dopo). A **0.0** due esecuzioni della stessa domanda danno un testo identico carattere per carattere; a **1.8** le due esecuzioni differiscono fra loro e dalla prima — «Il lavoro da remoto è consentito fino a 3 giorni settimanali…» contro un elenco puntato. Nessun riavvio fra le quattro richieste |
| **CA-6** | Cambiando i segmenti recuperati cambia il numero di fonti | Admin → `RetrievalProfile.top_k`, poi ripetere il passo 6 | **Superato in P4 e P5:** `top_k` cambiato da un **terzo** processo porta le fonti da 4 a 2 e **di nuovo a 4**, coi pid di server e worker invariati. Il ritorno al valore iniziale esclude che il numero dipendesse dai segmenti disponibili. **Ripetuto in T-42** con quattro valori consecutivi sullo stesso server: `top_k` 4 → 2 → 1 → 4 dà **3 → 2 → 1 → 3** fonti, e gli otto pid python sono gli stessi prima e dopo (il documento ha 3 segmenti, quindi `top_k` 4 ne può restituire al più 3) |
| **CA-7** | Due pipeline sulla stessa base danno risposte diverse | `GET /api/pipelines/`, poi `POST /api/ask/` con `pipeline` esplicita | **Superato in P4 e ripetuto in T-42:** creata «Pipeline telegrafica», identica alla predefinita per base di conoscenza, `LLMProfile` e `RetrievalProfile`, **diversa solo per il prompt**. Sulla stessa domanda le due risposte differiscono — elenco puntato contro una frase unica — mentre le fonti sono **le stesse tre, con gli stessi punteggi** (p. 3 0,6153 · p. 2 0,5342 · p. 1 0,4539): la differenza viene dal prompt e da nient'altro |
| **CA-8** | Un PDF corrotto o solo immagine va in *fallito* con motivo | Caricare un PDF di sole immagini, poi `GET /api/documents/{id}/` | **Superato:** `202` e poi `failed` con `error_message` leggibile (P5, con `curl` vero). **Ripetuto in T-42** su un PDF di sola immagine generato per la prova: `202`, poi `failed` con «Nessun testo estraibile dalle 1 pagine del documento. E' probabilmente una scansione senza OCR: …». Il sistema non ne è compromesso — la domanda successiva ha risposto `200` con le sue tre fonti. Coperto dai due casi di `test_un_pdf_non_indicizzabile_…`. **Nell'admin:** la changelist mostra «solo-immagine.pdf · Fallito · 0 · 0» e la pagina di dettaglio porta il motivo per esteso; anche qui è HTML servito dal `runserver` su sessione autenticata, **non** una pagina guardata in un browser |
| **CA-9** | Nessuna chiamata di rete verso servizi terzi | `.\scripts\prova-rete-staccata.ps1 -Utente <u> -Password <p>` a interfacce disattivate: si conduce da solo — a rete staccata nessuno può guidarlo da fuori — e lascia un verbale in `esiti-t43\` (ARCHITECTURE §9) | **Superato il 26/07/2026, ore 12:48** (T-43). Wi-Fi disattivata, Ethernet e Bluetooth già scollegate, **Tailscale disinstallato** perché un tunnel VPN attivo è un percorso di uscita; «Up» la sola `vEthernet (WSL)`, interna. Che l'esterno fosse irraggiungibile è **misurato**, e sui servizi che RNF-01 nomina: `api.smith.langchain.com`, `pypi.org` e gli host dei provider esclusi → *No such host is known*; `1.1.1.1:443`, provato **per indirizzo e non per nome**, → host unreachable; DNS in timeout. Mentre `127.0.0.1:5434` e `127.0.0.1:11434` rispondevano. Ciclo completo su un PDF **mai indicizzato prima**: 202 in 1,01 s, `indexed` in 4,07 s, risposta corretta con 4 fonti in 4,07 s, non-risposta sulla domanda fuori tema. **I tempi non differiscono da quelli a rete attiva** (0,95 / 7,50 / 13,53 in T-42), ed è questo l'argomento: una chiamata remota avrebbe atteso un timeout. Nei log, **tutte e dodici** le richieste HTTP dei due processi vanno a `localhost:11434` — 4 `/api/embed` dal worker, 2 `/api/tags`, 3 `/api/embed` e 3 `/api/chat` dal server: non l'assenza di traffico sospetto, ma l'elenco completo di quello che c'è stato |
| **CA-10** | La suite di test passa | `docker compose up -d db` e poi `pytest` | **Superato:** **29 passed in 10,44 s**, e **29 passed in 10,39 s** con `OLLAMA_BASE_URL` puntato su una porta chiusa. **Ripetuto in T-42** sul virtualenv appena ricostruito — **29 passed in 7,52 s** — che è anche la prova che `pytest` e `pytest-django` stanno davvero in `requirements.txt` e non solo nell'ambiente di sviluppo precedente. Da T-44 la suite è di **45 test**, verdi anche con `OLLAMA_BASE_URL` su una porta chiusa; il tempo complessivo non è stato ricronometrato e non se ne riporta uno |

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
- **Con `max_page_count` attivo la `POST` scopre anche i file corrotti, ed è un
  cambio di contratto.** Per contare le pagine deve aprire il PDF, quindi un file
  illeggibile riceve **400** invece di essere accettato con 202 e marcato
  *fallito* dal worker, come questo README documenta poco sopra («non esiste un
  422»). Il contratto predefinito è invariato, perché il limite nasce a 0 e
  finché è 0 il PDF non viene nemmeno aperto: il cambio si attiva scegliendo il
  limite dall'admin, e chi lo sceglie deve saperlo.
- **I [limiti di ammissione](#limiti-di-ammissione-dei-pdf) non sono stati
  percorsi end-to-end.** Sono verificati dai test e da `manage.py ingest` con un
  limite attivo; il ciclo per via HTTP con worker e Ollama veri, e il rifiuto
  dall'admin guardato in un browser, restano **da fare** — per questo di quel
  percorso non si riporta alcun tempo.
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
  assenza. L'alternativa sono i `curl` della sezione [API](#api).
- **Anche i comandi del README sono scritti per PowerShell**, per la stessa
  ragione: sono la forma che è stata *eseguita* in T-42, non una forma plausibile.
  Su Linux e macOS vanno tradotti, e la traduzione è meccanica —
  [tre regole](#curl-su-windows-powershell-si-scrive-curlexe) lette al contrario.
  Una versione precedente li dava in forma bash e **nessuno di essi funzionava**
  sulla macchina di consegna: è il difetto che la prova da zero ha scoperto.
- **Su Windows il launcher del virtualenv raddoppia i processi.** Misurato in P5:
  `.venv\Scripts\python.exe` ri-esegue l'interprete di base come processo
  **figlio**, quindi `runserver` e `db_worker` compaiono due volte anche con
  `--noreload`. Il pid che serve le richieste e scrive i log è il figlio; non è
  un worker duplicato.
- **PDF scansionati non supportati.** PyMuPDF estrae testo, non fa OCR: il caso è
  rilevato e segnalato con un errore esplicito, non produce un documento vuoto.
  Le scansioni **parziali** — poche pagine con testo su molte senza — hanno da
  T-44 un controllo dedicato, `min_text_page_ratio`, spento in configurazione
  predefinita.

**Fuori scope, dichiarato**

Interfaccia utente oltre alle quattro rotte dell'[interfaccia
web](#interfaccia-web) — la traccia non ne chiede alcuna —, formati diversi dal
PDF, OCR, memoria conversazionale multi-turno, ricerca ibrida BM25 + vettoriale,
reranking,
streaming SSE, multi-tenancy e ACL a livello di segmento, deployment in
produzione. Elenco completo in [REQUIREMENTS.md §8](REQUIREMENTS.md) e
[ARCHITECTURE.md §10](ARCHITECTURE.md).

## Licenza

Progetto realizzato come prova tecnica.
