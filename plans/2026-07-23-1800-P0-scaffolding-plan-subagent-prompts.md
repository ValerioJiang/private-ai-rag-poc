# Prompt per i sub-agenti — P0 Scaffolding (T-01 → T-06)

Piano di riferimento: [`2026-07-23-1800-P0-scaffolding-plan.md`](2026-07-23-1800-P0-scaffolding-plan.md)
Report di esecuzione da produrre: `plans/2026-07-23-1800-P0-scaffolding-plan-report.md`

Le cinque fasi vanno eseguite **in sequenza, un sub-agente per fase**. Ogni
prompt è autosufficiente: non presuppone di aver visto l'output dei precedenti.
Prima di lanciare la fase N+1, i criteri di completamento della fase N devono
essere verdi.

---

# Prerequisiti

Da verificare **una sola volta**, prima della fase 1. Se uno fallisce, risolverlo
prima di partire: nessuna fase li ricontrolla per conto proprio.

## Strumenti

- [ ] Python 3.12+ — `python --version` → atteso `3.12.x` o superiore
      *(verificato il 24/07: 3.12.10)*
- [ ] git — `git --version` *(verificato: 2.52.0)*
- [ ] Docker attivo — `docker ps` → deve rispondere senza errori *(verificato: 29.1.3)*
- [ ] Docker Compose v2 — `docker compose version` *(verificato: v2.40.3-desktop.1)*

## Servizi

- [ ] **Ollama in esecuzione** — `curl -s http://localhost:11434/api/tags`
      → deve restituire un JSON con la chiave `models`

      **Verificato il 24/07: in esecuzione, versione 0.32.3, 7 modelli.**
      Se risultasse spento, avviarlo prima della fase 3: aprire l'app Ollama,
      oppure da PowerShell
      `Start-Process -WindowStyle Hidden ollama -ArgumentList 'serve'`.
      Senza Ollama la fase 3 chiude con `/health` in stato `degraded` e le fasi
      4 e 5 falliscono del tutto.

- [ ] Modello di generazione presente — `ollama list | grep qwen2.5:7b-instruct`
      *(verificato: presente, 4,4 GB)*
- [ ] Modello di embedding presente — `ollama list | grep bge-m3`
      *(verificato: presente come `bge-m3:latest`, 1,1 GB. Il tag `:latest` è
      implicito: usare `model='bge-m3'` nel codice è corretto e funziona)*

      Entrambi risultavano già scaricati: **non riscaricarli**. Insieme occupano
      ~5,5 GB sugli ~8 GB di VRAM, quindi possono restare residenti entrambi.

## Porte

- [ ] Porta host 5434 libera — `netstat -ano | grep ":5434" | grep LISTENING`
      → **nessun output atteso** *(verificato libera il 24/07)*
- [ ] Nota: 5432 (`q-postgres-1`) e 5433 (`q-langfuse-postgres-1`) sono occupate
      da altri stack. È il motivo per cui questo progetto usa la 5434. Non
      spegnere quei container.

## Repository

- [ ] Posizionati nella radice corretta — `git rev-parse --show-toplevel`
      → atteso `C:/Users/vjiang/Documents/archetype-lab`
- [ ] Documenti presenti — `ls ARCHITECTURE.md PLAN.md REQUIREMENTS.md BACKLOG.md`
- [ ] Il piano è leggibile — `ls plans/2026-07-23-1800-P0-scaffolding-plan.md`

## Dipendenze e build

Non ci sono prerequisiti di build: **è la fase 1 a costruire il virtualenv e a
installare le dipendenze**. Le fasi 2→5 danno per scontato che `.venv/` esista.

- [ ] Verifica per le fasi 2→5 — `ls .venv/Scripts/python.exe`

## Stato atteso del working tree

- [ ] `ARCHITECTURE.md`, `PLAN.md`, `REQUIREMENTS.md` risultano **modificati e non
      committati**. È voluto: **li committa l'utente a mano.** Nessun sub-agente
      deve aggiungerli, committarli, modificarli o «sistemarli».
      Verifica: `git status --short` → tre righe ` M` per quei file.

---

# Fase 1: Igiene del repository e dipendenze

Copre T-01 e T-03. Nessuna fase precedente: è la prima.

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- plans/2026-07-23-1800-P0-scaffolding-plan.md, sezione "Fase 1" — contiene il
  contenuto ESATTO dei file da creare, copialo da lì senza reinventarlo
- BACKLOG.md, righe T-01 e T-03 — per confermare l'ambito
- ARCHITECTURE.md §7 — perché queste dipendenze e non altre

Obiettivo: portare il repository da "sola documentazione" ad avere igiene git,
un README e un virtualenv con le dipendenze installate e bloccate.

Esegui, nell'ordine, i passi da 1.1 a 1.7 della Fase 1 del piano:

1.1 Creare .gitignore con il contenuto indicato nel piano.
1.2 Creare requirements.in con il contenuto indicato nel piano (vincoli larghi,
    con i commenti che spiegano i vincoli: NON rimuoverli, motivano scelte non
    ovvie come pgvector<0.4).
1.3 Creare README.md con il contenuto indicato nel piano.
1.4 Creare il virtualenv e installare:
      python -m venv .venv
      .venv/Scripts/python.exe -m pip install --upgrade pip
      .venv/Scripts/python.exe -m pip install -r requirements.in
    L'installazione richiede qualche minuto. Se pip deve fare backtracking sulle
    versioni, lascialo lavorare.
1.5 Congelare le versioni risolte:
      .venv/Scripts/python.exe -m pip freeze > requirements.txt
1.6 Rimuovere .claude/settings.local.json dall'indice di git:
      git rm --cached .claude/settings.local.json
    Il file resta sul disco: --cached tocca solo l'indice. Questo passo e'
    necessario perche' .gitignore non ha alcun effetto sui file gia' tracciati.
1.7 Commit:
      git add .gitignore README.md requirements.in requirements.txt BACKLOG.md
      git commit -m "P0: igiene repo, README e dipendenze bloccate"

VINCOLI IMPORTANTI:
- NON usare `git add -A` ne' `git add .`. ARCHITECTURE.md, PLAN.md e
  REQUIREMENTS.md sono modificati DI PROPOSITO e li committa l'utente a mano.
  Aggiungerli sarebbe un errore. Anche la cartella plans/ resta non tracciata.
- NON installare torch ne' sentence-transformers: sono stati esplicitamente
  scartati (~2,5 GB di wheel). Gli embedding passano da Ollama.
- Le versioni attese dopo l'installazione sono note e documentate nel piano
  (Django 6.0.7, langchain-core 1.5.0, langchain-postgres 0.0.17, ...). Se pip
  risolve versioni diverse NON e' un errore da correggere a forza: annotalo nel
  report. Attenzione pero': langchain-core deve essere 1.x, non 0.3.x.

Verifica prima di dichiarare finito:
  .venv/Scripts/python.exe -c "import django, langchain_core, langchain_postgres, langchain_ollama, fitz; print(django.get_version())"
  .venv/Scripts/python.exe -m pip freeze | grep -Ei "^(Django|langchain-core|langchain-postgres|langchain-ollama|pymupdf|psycopg)="
  git status --short
  git ls-files .claude/settings.local.json    # deve stampare NULLA

Criteri di completamento:
- .venv esiste e importa Django 6.0.x senza errori
- requirements.txt contiene versioni esatte (nessun >=)
- .claude/settings.local.json non e' piu' tracciato
- git status --short mostra SOLO: tre ' M' per ARCHITECTURE/PLAN/REQUIREMENTS
  e '?? plans/'. Ne' .venv/ ne' settings.local.json devono comparire.

Al termine, aggiungi a plans/2026-07-23-1800-P0-scaffolding-plan-report.md
(crealo se non esiste) una sezione "## Fase 1" con: esito, versioni
effettivamente risolte delle dipendenze chiave, e qualunque scostamento dal
piano. Non modificare il file del piano.
```

---

# Fase 2: Infrastruttura Docker e configurazione d'ambiente

Copre T-02. **Richiede la fase 1 completata** (il `Dockerfile` copia `requirements.txt`).

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- plans/2026-07-23-1800-P0-scaffolding-plan.md, sezione "Fase 2" — contiene il
  contenuto ESATTO dei file da creare, copialo da li'
- ARCHITECTURE.md §2 — diagramma di deployment, perche' Ollama resta sull'host
- .gitignore gia' presente in radice — conferma che contenga la riga `.env`

Contesto che NON puoi dedurre dal codice:
- Sulla macchina girano gia' altri stack Docker. Le porte host 5432
  (q-postgres-1) e 5433 (q-langfuse-postgres-1) sono OCCUPATE. Questo progetto
  usa quindi la porta host 5434. Non spegnere gli altri container.
- Dentro la rete di Compose vale comunque la porta INTERNA 5432: per questo i
  servizi web e worker ricevono POSTGRES_PORT=5432 esplicito, altrimenti
  erediterebbero 5434 da .env e non troverebbero il database.
- Ollama NON va containerizzato: su Windows il passthrough GPU verso Docker
  richiederebbe WSL2 + nvidia-container-toolkit. Gira nativamente sull'host e i
  container lo raggiungono via host.docker.internal.

Esegui, nell'ordine, i passi da 2.1 a 2.6 della Fase 2 del piano:

2.1 Creare docker-compose.yml come da piano. Include un servizio `worker`
    disattivato tramite `profiles: [worker]`: e' predisposto per P5 e NON deve
    partire ora, perche' `manage.py db_worker` non esiste ancora.
2.2 Creare Dockerfile come da piano (base python:3.12-slim).
2.3 Creare .env.example come da piano.
2.4 Creare il .env locale e avviare il database:
      cp .env.example .env
      docker compose up -d db
    Il primo avvio scarica l'immagine pgvector/pgvector:pg17: puo' richiedere
    qualche minuto.
2.5 Commit:
      git add docker-compose.yml Dockerfile .env.example
      git commit -m "P0: docker-compose con pgvector e Dockerfile applicativo"
2.6 OPZIONALE (~3-5 min): `docker compose build web`. In P0 si avvia solo `db`,
    quindi il Dockerfile non verrebbe mai esercitato e un errore resterebbe
    latente fino a P6. Questa build verifica che requirements.txt — congelato su
    Windows — si installi davvero su python:3.12-slim. Un fallimento qui NON
    blocca le fasi successive (girano nel venv dell'host): annotalo nel report
    come debito da chiudere in P6.

VINCOLI IMPORTANTI:
- .env NON va committato: deve essere coperto da .gitignore. Se compare in
  `git status`, fermati e correggi .gitignore prima di proseguire.
- NON usare `git add -A`: ARCHITECTURE.md, PLAN.md e REQUIREMENTS.md sono
  modificati di proposito e li committa l'utente a mano.
- NON aggiungere Redis ne' Celery al compose: scartati, cfr. ARCHITECTURE §7.5.

Verifica prima di dichiarare finito:
  docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
  docker compose exec db psql -U rag -d ragdb -c "SELECT version();"
  git status --short

Criteri di completamento:
- docker compose ps mostra il servizio db in stato healthy
- la porta pubblicata e' 5434->5432
- psql risponde con una versione di PostgreSQL 17
- .env NON compare in git status

Al termine, aggiungi al report plans/2026-07-23-1800-P0-scaffolding-plan-report.md
una sezione "## Fase 2" con: esito, versione di PostgreSQL rilevata, esito della
build opzionale 2.6 (eseguita/saltata/fallita). Non modificare il file del piano.
```

---

# Fase 3: Progetto Django, settings e health check

Copre T-04. **Richiede le fasi 1 e 2 completate** (serve il venv e il database acceso).
**Richiede inoltre Ollama in esecuzione**, altrimenti `/health` non arriva a `ok`.

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- plans/2026-07-23-1800-P0-scaffolding-plan.md, sezione "Fase 3" — contiene il
  contenuto ESATTO di ogni file Python da creare, copialo da li' senza
  riscriverlo a modo tuo
- ARCHITECTURE.md §3 — il principio "nessun parametro di comportamento nei settings"
- .env.example gia' presente in radice — i nomi delle variabili lette da
  base.py devono corrispondere esattamente a quelli del file

Prerequisito da controllare PRIMA di iniziare:
  ls .venv/Scripts/python.exe                      # fase 1 completata
  docker compose ps                                # il servizio db deve essere healthy
  curl -s http://localhost:11434/api/tags          # Ollama deve rispondere
Se Ollama non risponde, avvialo (app Ollama, oppure da PowerShell
`Start-Process -WindowStyle Hidden ollama -ArgumentList 'serve'`) e riprova:
senza Ollama l'ultimo criterio di completamento non e' raggiungibile.

PRINCIPIO ARCHITETTURALE DA NON VIOLARE:
nei settings non deve finire NESSUN parametro di comportamento del RAG. Modello,
temperatura, chunking e retrieval diventeranno righe di database gestite
dall'admin in P1. Nei settings stanno solo indirizzi di infrastruttura
(OLLAMA_BASE_URL, credenziali del database). Non aggiungere costanti tipo
CHUNK_SIZE o LLM_MODEL: sarebbe un errore di progettazione, non una comodita'.

Esegui, nell'ordine, i passi da 3.1 a 3.11 della Fase 3 del piano:

3.1  Generare progetto e app, poi togliere il settings.py piatto:
       .venv/Scripts/django-admin.exe startproject config .
       .venv/Scripts/python.exe manage.py startapp rag
       rm config/settings.py
       mkdir -p config/settings
3.2  config/settings/__init__.py VUOTO, e config/settings/base.py come da piano.
     Include CACHES con LocMemCache: e' obbligatorio e va impostato ora. La
     catena LangChain di P3 conterra' oggetti Python vivi (client, connessioni),
     non serializzabili: la cache deve essere in-process, mai Redis ne' database.
     Include anche la forzatura di LANGSMITH_TRACING/LANGCHAIN_TRACING_V2 a
     "false": se la macchina ha gia' quelle variabili per altri progetti, il
     tracing verso il cloud si accenderebbe da solo e le tracce conterrebbero i
     chunk dei PDF. NON rimuovere quelle due righe.
3.3  config/settings/dev.py come da piano.
3.4  config/settings/prod.py come da piano.
3.5  Far puntare i tre entrypoint a config.settings.dev: sostituire
     `config.settings` con `config.settings.dev` nella riga
     os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...) di manage.py,
     config/wsgi.py e config/asgi.py.
     USA L'EDITOR, non `sed -i`: su Windows sed -i puo' alterare i fine riga, e
     soprattutto una sed che non trova nulla ESCE CON SUCCESSO, quindi
     l'errore si manifesterebbe molto piu' tardi come un `manage.py check`
     incomprensibile. Leggi ogni file prima di sostituire (Django 6.0.7 usa
     apici singoli nei template, ma verificalo invece di fidarti).
     Verifica obbligatoria:
       grep -n "DJANGO_SETTINGS_MODULE" manage.py config/wsgi.py config/asgi.py
     Devono uscire TRE righe, tutte con config.settings.dev.
3.6  Sostituire config/urls.py come da piano.
3.7  Creare rag/urls.py come da piano.
3.8  Sostituire rag/views.py con l'health check del piano. Verifica davvero le
     tre dipendenze esterne (database, estensione pgvector, Ollama), non solo
     che Django risponda. Restituisce 200 se tutti e tre passano, 503 altrimenti.
3.9  Creare rag/migrations/0001_enable_pgvector.py come da piano. L'estensione
     va installata DA MIGRAZIONE, non a mano con psql: l'ambiente deve essere
     ricostruibile con il solo `migrate` (criterio CA-1).
3.10 Migrazioni e utente amministratore:
       .venv/Scripts/python.exe manage.py migrate
       DJANGO_SUPERUSER_PASSWORD=admin \
         .venv/Scripts/python.exe manage.py createsuperuser \
         --noinput --username admin --email admin@example.com
     ATTENZIONE: createsuperuser SENZA --noinput chiede la password da terminale
     e resterebbe bloccato per sempre in esecuzione non interattiva. Usa sempre
     la forma qui sopra. Se riporta che l'utente esiste gia', va bene.
3.11 Commit:
       git add config rag manage.py
       git commit -m "P0: progetto Django, settings per ambiente, health check e pgvector"

VINCOLI IMPORTANTI:
- NON creare modelli Django in rag/models.py: e' P1 (T-07 -> T-13). Il file
  resta come lo genera startapp.
- NON usare `git add -A`: ARCHITECTURE.md, PLAN.md e REQUIREMENTS.md sono
  modificati di proposito e li committa l'utente a mano.

Verifica prima di dichiarare finito:
  .venv/Scripts/python.exe manage.py check
  .venv/Scripts/python.exe manage.py showmigrations rag
  docker compose exec db psql -U rag -d ragdb -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"

Per l'health check serve il server acceso. NON lanciare `runserver` in primo
piano: bloccherebbe l'esecuzione. Avvialo in background e spegnilo:
  .venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload &
  SRV=$!
  sleep 5
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health
  curl -s http://localhost:8000/health
  kill $SRV
--noreload evita che il reloader generi un processo figlio che kill non
raggiungerebbe, lasciando la porta 8000 occupata.

Criteri di completamento:
- manage.py check non riporta problemi
- showmigrations rag mostra [X] 0001_enable_pgvector
- la query su pg_extension restituisce una riga per 'vector'
- GET /health risponde 200 con "status": "ok" e tutti e tre i check a true
- l'admin risponde su http://localhost:8000/admin/

Al termine, aggiungi al report plans/2026-07-23-1800-P0-scaffolding-plan-report.md
una sezione "## Fase 3" con: esito, versione dell'estensione vector rilevata,
corpo JSON completo della risposta di /health. Non modificare il file del piano.
```

---

# Fase 4: Verifica del servizio di inferenza

Copre T-05. **Richiede le fasi 1 e 3 completate** e **Ollama in esecuzione**.
Fase di sola verifica: non crea file e **non produce commit**.

> **Il passo 4.4 non è facoltativo.** La dimensione del vettore è l'unico dato
> che la fase 5 e la fase P1 non possono ricavare da un file: va scritta nel
> report, altrimenti si perde nel cambio di agente.

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- config/settings/base.py — per confermare il valore di OLLAMA_BASE_URL
- plans/2026-07-23-1800-P0-scaffolding-plan.md, sezione "Fase 4"

Obiettivo: dimostrare che il servizio di inferenza locale risponde davvero,
PRIMA di costruire lo spike che e' la fase piu' lunga del piano. E' un punto di
arresto a basso costo: se qualcosa non va, si scopre qui.

Questa fase NON crea file e NON fa commit. Non modificare nulla nel repository
a parte il file di report.

Prerequisito da controllare prima di iniziare:
  ls .venv/Scripts/python.exe
  curl -s http://localhost:11434/api/tags
Se Ollama non risponde, avvialo (app Ollama, oppure da PowerShell
`Start-Process -WindowStyle Hidden ollama -ArgumentList 'serve'`).

4.1 Confermare che i due modelli siano presenti. DOVREBBERO GIA' ESSERCI:
    non riscaricarli se li trovi.
      ollama list | grep -E "qwen2.5:7b-instruct|bge-m3"
    Solo se effettivamente mancanti:
      ollama pull qwen2.5:7b-instruct
      ollama pull bge-m3

4.2 Verificare la generazione dalla shell Django:
      .venv/Scripts/python.exe manage.py shell -c "
      from django.conf import settings
      from langchain_ollama import ChatOllama
      llm = ChatOllama(model='qwen2.5:7b-instruct', base_url=settings.OLLAMA_BASE_URL, temperature=0)
      print(llm.invoke('Rispondi in italiano con una sola parola: capitale della Francia?').content)
      "
    Il PRIMO caricamento del modello in VRAM puo' richiedere DECINE DI SECONDI.
    Non e' un errore e non e' un blocco: aspetta. Non ridurre i timeout sotto i
    120 secondi in questa fase.

4.3 Verificare gli embedding e MISURARNE LA DIMENSIONE:
      .venv/Scripts/python.exe manage.py shell -c "
      from django.conf import settings
      from langchain_ollama import OllamaEmbeddings
      emb = OllamaEmbeddings(model='bge-m3', base_url=settings.OLLAMA_BASE_URL)
      v = emb.embed_query('prova di embedding in italiano')
      print('dimensione:', len(v))
      "

4.4 OBBLIGATORIO — annota nel report la dimensione rilevata. E' il valore che in
    P1 finira' in EmbeddingProfile.dimension e che vincola lo schema pgvector.
    Attesa: 1024 per bge-m3. Se il numero e' diverso, e' IL VALORE REALE A FARE
    FEDE e va usato nelle fasi successive: scrivilo in modo evidente.

VINCOLI IMPORTANTI:
- NON usare i modelli Ollama con suffisso -cloud (deepseek-v3.1:671b-cloud,
  gpt-oss:120b-cloud, presenti sulla macchina): violano il vincolo di localita'
  del progetto, che promette che nessun dato lasci la macchina.
- La macchina ha una GPU da ~8 GB. qwen2.5:7b-instruct (~4,7 GB Q4) e bge-m3
  (~1,2 GB) ci coesistono. Se noti che Ollama scarica e ricarica di continuo i
  modelli, annotalo nel report: e' il segnale di contesa di VRAM previsto fra i
  rischi del piano.

Criteri di completamento:
- ChatOllama.invoke restituisce "Parigi" (o equivalente) senza eccezioni
- OllamaEmbeddings.embed_query restituisce un vettore non vuoto
- la dimensione del vettore E' ANNOTATA NEL REPORT

Al termine, aggiungi al report plans/2026-07-23-1800-P0-scaffolding-plan-report.md
una sezione "## Fase 4" con: risposta testuale ottenuta dal modello, DIMENSIONE
DEL VETTORE (in evidenza), tempo approssimativo della prima invocazione contro
quelle successive, ed eventuali segnali di contesa di VRAM.
Non modificare il file del piano.
```

---

# Fase 5: Spike RAG end-to-end

Copre T-06. **Richiede tutte le fasi precedenti**: venv, database acceso, settings
Django, Ollama funzionante.

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- plans/2026-07-23-1800-P0-scaffolding-plan.md, sezione "Fase 5" — contiene il
  sorgente ESATTO di scripts/spike_rag.py, copialo da li'
- plans/2026-07-23-1800-P0-scaffolding-plan-report.md, sezione "Fase 4" — per la
  dimensione del vettore gia' misurata
- ARCHITECTURE.md §4 e §5 — flussi di ingestione e interrogazione, che questo
  spike riproduce in forma minima
- REQUIREMENTS.md §7 — criteri CA-3 e CA-4, che questo spike anticipa

Obiettivo: dimostrare END-TO-END che PyMuPDF, bge-m3, pgvector e qwen2.5 si
parlano e producono una risposta corretta su un PDF reale, e misurare i tempi
veri sulla macchina.

NATURA DEL CODICE — leggi con attenzione, cambia come devi scriverlo:
Questo e' codice USA-E-GETTA. Verra' CANCELLATO in P2. I parametri sono scritti
a mano DI PROPOSITO: in P1 diventeranno righe di database gestite dall'admin.
NON generalizzarlo, NON estrarre configurazioni, NON aggiungere astrazioni,
NON renderlo riusabile. Serve a produrre CONOSCENZA, non artefatti.
UNICA ECCEZIONE: la funzione load_pdf(). Non esiste un loader PDF senza tirarsi
dentro langchain-community (cfr. ARCHITECTURE §7.10), quindi quella funzione e'
codice di prima parte fin d'ora e verra' PROMOSSA in T-14. Scrivila con cura;
tutto il resto del file no.

Prerequisito da controllare prima di iniziare:
  ls .venv/Scripts/python.exe
  docker compose ps                        # db healthy
  curl -s http://localhost:11434/api/tags  # Ollama risponde

5.1 Procurare un PDF TESTUALE in italiano in samples/. Se non ce n'e' uno,
    generalo con lo snippet PyMuPDF riportato nel piano al passo 5.1 (crea
    samples/manuale-dipendenti.pdf, 3 pagine su ferie, rimborsi e lavoro da
    remoto). Verifica: ls samples/*.pdf
5.2 Creare scripts/spike_rag.py con il sorgente del piano.
5.3 Eseguire lo spike:
      .venv/Scripts/python.exe scripts/spike_rag.py samples/manuale-dipendenti.pdf
    L'indicizzazione e la prima generazione possono richiedere parecchio tempo
    (caricamento dei modelli in VRAM). Non e' un errore: aspetta.
5.4 OBBLIGATORIO — annotare nel report i DATI DI REALTA' raccolti, perche' sono
    l'input diretto delle fasi P1 e P2:
      - dimensione del vettore prodotto da bge-m3
      - tempo di indicizzazione, e tempo per singolo chunk
      - tempo di retrieval e di generazione per ciascuna domanda
      - nomi effettivi delle tabelle create da PGVector in PostgreSQL
      - se il comportamento "non lo so" funziona con questo prompt
      - quale API di PGVector ha funzionato (vedi sotto)
5.5 Commit (lo spike SI VERSIONA: documenta come si e' arrivati alle scelte, e
    verra' rimosso in P2):
      git add scripts samples
      git commit -m "P0: spike RAG end-to-end su PDF di prova"

RISCHIO NOTO E RIPIEGO GIA' DECISO:
langchain-postgres 0.0.17 gira con langchain-core 1.x. Il vincolo dichiarato e'
langchain-core<2.0,>=0.2.13, quindi non c'e' conflitto di risoluzione, ma resta
un rischio di comportamento. Se PGVector.from_documents() fallisce, NON
improvvisare: prova l'API a istanza, cioe' PGVector(...) seguito da
add_documents(). ANNOTA NEL REPORT quale delle due ha funzionato — sara' quella
da usare in P2. Se non regge nemmeno quella, il ripiego strutturale e' un
retriever custom sull'ORM (cfr. ARCHITECTURE §7.9): in quel caso fermati e
segnalalo, non costruirlo in questa fase.

ALTRO CASO PREVISTO:
se il PDF non produce testo estraibile, lo script esce con un errore esplicito.
E' il caso di un PDF di sole immagini (scansione senza OCR). In questa fase
basta ACCORGERSENE E SEGNALARLO: la gestione strutturata arriva in P2 (T-14,
requisito RF-10). Non implementare OCR.

VINCOLI IMPORTANTI:
- NON usare i modelli Ollama con suffisso -cloud: violano il vincolo di localita'.
- NON creare modelli Django in rag/models.py: e' P1.
- NON spostare i parametri dello spike nei settings: devono diventare righe di
  database in P1.
- NON usare `git add -A`: ARCHITECTURE.md, PLAN.md e REQUIREMENTS.md sono
  modificati di proposito e li committa l'utente a mano.

Verifica prima di dichiarare finito:
  .venv/Scripts/python.exe scripts/spike_rag.py samples/manuale-dipendenti.pdf
  docker compose exec db psql -U rag -d ragdb -c "\dt"
  docker compose exec db psql -U rag -d ragdb -c "SELECT COUNT(*) FROM langchain_pg_embedding;"

Criteri di completamento:
- lo script termina senza eccezioni
- le prime due domande (giorni di ferie, rimborso chilometrico) ricevono
  risposte CORRETTE tratte dal PDF
- la terza domanda (capitale del Madagascar) ottiene esattamente
  "Non dispongo di questa informazione nei documenti forniti."
- \dt mostra le tabelle langchain_pg_collection e langchain_pg_embedding
- SELECT COUNT(*) FROM langchain_pg_embedding restituisce un numero pari ai
  chunk indicizzati
- i tempi misurati sono annotati nel report

Al termine, aggiungi al report plans/2026-07-23-1800-P0-scaffolding-plan-report.md
una sezione "## Fase 5" con tutti i dati del passo 5.4, il testo integrale delle
tre risposte ottenute, e una sezione finale "## Esito di P0" che riepiloghi se i
criteri di completamento della fase sono soddisfatti.
Non modificare il file del piano.
```

---

# Riepilogo delle dipendenze fra fasi

| Fase | Richiede | Passa alla successiva | Commit |
|---|---|---|---|
| 1 | — | `.venv/`, `requirements.txt` | sì |
| 2 | fase 1 | container `db` acceso, `.env` | sì |
| 3 | fasi 1, 2 + Ollama acceso | `config/settings/`, schema del DB | sì |
| 4 | fasi 1, 3 + Ollama acceso | dimensione del vettore **via report** | no |
| 5 | tutte + Ollama acceso | dati di realtà **via report** | sì |

Totale atteso: **quattro commit**. La fase 4 è di sola verifica e non ne produce.
