# P6 — Prompt dei sub-agenti

Piano di riferimento: [`2026-07-25-2132-P6-plan.md`](2026-07-25-2132-P6-plan.md).
Ogni prompt è **autonomo**: chi lo esegue non ha il contesto di questa sessione
né di quelle precedenti. Le fasi vanno eseguite **in ordine**, e ciascuna
comincia solo dopo che la verifica della precedente è passata.

---

# Prerequisiti

Da verificare **una volta**, prima del primo sub-agente.

## Servizi
- [ ] PostgreSQL sulla porta 5434 (verifica: `docker compose ps db` mostra
      `healthy`)
- [ ] Ollama sull'host con i due modelli — **solo per le fasi 6, 8, 9**
      (verifica: `ollama list` mostra `qwen2.5:7b-instruct` e `bge-m3`)

## Docker
- [ ] `docker compose up -d db` eseguito nella radice del progetto
      (verifica: `docker compose ps`)

## Ambiente
- [ ] `.env` esiste (verifica: `Test-Path .env`)
- [ ] `TASKS_BACKEND=django_tasks_db.DatabaseBackend`
      (verifica: `Select-String TASKS_BACKEND .env`)

## Dipendenze
- [ ] Virtualenv in `.venv` (verifica:
      `.venv\Scripts\python.exe -c "import django; print(django.get_version())"`
      → `6.0.7`)
- [ ] Migrazioni applicate (verifica:
      `.venv\Scripts\python.exe manage.py showmigrations rag` — tutte `[X]`)

## Stato del repository
- [ ] Albero pulito (verifica: `git status --porcelain` non stampa nulla)
- [ ] Ramo `main` (verifica: `git branch --show-current`)

---

## Regole valide per TUTTI i sub-agenti

Ripetute in ogni prompt perché ciascuno parte con il comportamento predefinito.

1. **Lingua italiana ovunque**: docstring, commenti, messaggi d'errore, nomi di
   funzioni e variabili di dominio, messaggi di commit. I nomi dei campi dei
   modelli restano in inglese, con `verbose_name` in italiano.
2. **Le docstring sono la documentazione di progetto.** Lunghe di proposito,
   spiegano il *perché* con requisiti citati per id (RF-xx, T-xx, CA-xx,
   ARCHITECTURE §x) e limiti dichiarati apertamente. Niente commenti
   decorativi: ogni nota deve dire qualcosa che il codice non dice già.
3. **Distinguere verificato da dedotto.** Scrivere «misurato», «verificato sul
   sorgente della x.y.z», «osservato in pianificazione». Non affermare
   comportamenti di librerie senza averli controllati.
4. **Commit in italiano**, prefissati dalla fase e con gli id delle attività.
   **MAI il trailer `Co-Authored-By`, mai alcuna attribuzione a Claude o ad
   AI.** Il messaggio si chiude sull'ultimo paragrafo di contenuto. Autore e
   committer restano quelli configurati in git.
5. **Nessuna dipendenza che possa mandare testo fuori dalla macchina** (RNF-01):
   niente `langchain-openai`, niente `sentence-transformers`, nessun tracing
   cloud.
6. **`requirements.txt` si genera con `pip freeze`** dopo un'installazione
   reale: si modifica `requirements.in`, mai il `.txt` a mano.
7. Se una verifica fallisce, **fermarsi e riportare**, non aggirare. Un piano
   sbagliato è informazione; un piano aggirato in silenzio non lo è.

---

# Fase 1 — Impalcatura di pytest

Sei in `C:\Users\vjiang\Documents\archetype-lab`, un backend Django 6 che
implementa un sistema RAG su PDF con generazione ed embedding **interamente
locali** (Ollama sull'host). Il progetto è interamente in **italiano** — leggi
`CLAUDE.md` prima di scrivere una riga.

**Obiettivo:** mettere in piedi la suite di test, che oggi non esiste
(`rag/tests.py` è lo scheletro di `startapp`, `pytest` non è fra le dipendenze).
Criterio di accettazione CA-10: «La suite di test passa — `pytest`».

**Leggi prima:**
- `CLAUDE.md` — convenzioni, comandi, principio portante
- `plans/2026-07-25-2132-P6-plan.md` §2 e §5 fase 1 — decisioni e passi
- `requirements.in` — la forma dei commenti che motivano ogni vincolo
- `rag/services/factories.py` righe 57-99 — `_CACHE` e `svuota_cache()`
- `rag/signals.py` righe 161-207 — `MODELLI_DI_CONFIGURAZIONE` e i
  `dispatch_uid` da scollegare

**Da fare:** i punti da 1.1 a 1.6 della fase 1 del piano, che contengono il
contenuto integrale di `pytest.ini`, `rag/tests/__init__.py` e
`rag/tests/conftest.py`. In sintesi:
1. `pytest>=8.0` e `pytest-django>=4.9` in `requirements.in`, con il commento
   che spiega perché pytest e non `manage.py test`;
2. installare e rigenerare `requirements.txt` con `pip freeze`;
3. creare `pytest.ini` (senza `--reuse-db` negli `addopts`: la fase 2 aggiunge
   una migrazione, e un database riusato non la applicherebbe);
4. `git rm rag/tests.py` e creare il package `rag/tests/`;
5. `rag/tests/conftest.py` con: la fixture `autouse` che svuota `_CACHE`, la
   fixture che **scollega** il receiver `invalida_cache_factory`, le fixture di
   configurazione e utente, i tre PDF generati con PyMuPDF, e le classi
   `EmbeddingsFinti` e `VectorStoreFinto`.

**Due cose da misurare prima di darle per buone**, e da riportare:
- che `pymupdf.Document.tobytes()` esista sulla 1.28.0 installata. Se non
  esistesse, il ripiego dichiarato è `documento.save(percorso)` con la fixture
  che restituisce un percorso invece dei byte;
- che la creazione del database di prova riesca. Se `CREATE EXTENSION vector`
  fallisse per permessi, il rimedio è
  `docker compose exec db psql -U rag -d postgres -c "ALTER ROLE rag SUPERUSER"`,
  **e va riportato**, perché diventerebbe un passo dell'avvio da zero (CA-1).

**Verifica:**
```powershell
.venv\Scripts\python.exe -m pytest --collect-only
.venv\Scripts\python.exe -c "import pymupdf; d=pymupdf.open(); p=d.new_page(); p.insert_text((72,100),'prova'); print(len(d.tobytes()), 'byte')"
.venv\Scripts\python.exe -c "from langchain_core.language_models.fake_chat_models import FakeListChatModel; print('ok')"
```

**Fatto quando:** `pytest --collect-only` termina senza errori raccogliendo 0
test; il database `test_ragdb` viene creato e distrutto; `requirements.txt`
contiene le due dipendenze nuove; `rag/tests.py` non esiste più.

**Commit:** `P6: impalcatura di pytest e fixture comuni (T-36)` — senza alcun
trailer di attribuzione.

---

# Fase 2 — L'estratto diventa configurazione (RF-22)

Sei in `C:\Users\vjiang\Documents\archetype-lab`, backend Django 6 di un sistema
RAG, interamente in **italiano**. Leggi `CLAUDE.md` prima di scrivere una riga.

**Il principio portante del progetto**, che questa fase applica: *nessun
parametro di comportamento è una costante nel codice*. Ogni parametro — modello,
temperatura, `chunk_size`, strategia di retrieval, prompt — è una riga di
database modificabile dall'admin (RF-22). Una sola violazione è sopravvissuta
fino a P5 ed è dichiarata per iscritto nel report di quella fase:
`LUNGHEZZA_ESTRATTO = 300` in `rag/services/query.py:74`.

**Obiettivo:** trasformarla in `RetrievalProfile.excerpt_length`.

**Leggi prima:**
- `CLAUDE.md`
- `plans/2026-07-25-2132-P6-plan.md` §2.1 decisione D4, §4.3 e §5 fase 2 — il
  codice integrale di ogni modifica
- `rag/services/query.py` righe 70-167 e 200-245 — la costante, il dataclass,
  `_da_documento_langchain` (**l'unico punto di costruzione**) ed
  `esegui_ricerca`, che ha già il profilo
- `rag/models/profiles.py` righe 258-319 — `RetrievalProfile`
- `rag/admin.py` righe 153-190 — i fieldset di `RetrievalProfileAdmin`

**Da fare:** i punti da 2.1 a 2.6 della fase 2. In sintesi: campo
`excerpt_length` su `RetrievalProfile` (default 300, `MinValueValidator(50)`,
`help_text` che dice che **non** cambia il contesto passato all'LLM); migrazione
`0005_excerpt_length` con docstring di modulo; campo nel fieldset «Parametri» e
in `list_display` dell'admin; rimozione della costante da `query.py` con una
nota nell'intestazione del modulo che spiega da dove viene e perché il
predefinito resta 300; campo `lunghezza_estratto` nel dataclass
`SegmentoRecuperato` **prima** di `chunk_id` (che ha un default); passaggio del
valore da `esegui_ricerca` attraverso `_da_documento_langchain`.

**Due avvertenze:**
- è la **prima migrazione dell'app `rag` da P1**. È additiva e con default,
  quindi non tocca i dati esistenti, ma va generata con `makemigrations` e non
  scritta a mano;
- `replace()` in `collega_ai_chunk()` conserva il campo senza modifiche: è la
  ragione per cui il valore viaggia nel segmento invece di essere riletto dal
  profilo dentro la property.

**Verifica:**
```powershell
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py check
Select-String -Path rag\ -Pattern "LUNGHEZZA_ESTRATTO" -Recurse
```

**Fatto quando:** nessuna migrazione pendente; `manage.py check` pulito;
`LUNGHEZZA_ESTRATTO` non compare più in alcun `.py`; il campo è modificabile in
`/admin/rag/retrievalprofile/`.

**Commit:** `P6: la lunghezza dell'estratto diventa configurazione (RF-22)` —
senza alcun trailer di attribuzione.

---

# Fase 3 — T-36: test di segmentazione e factory

Sei in `C:\Users\vjiang\Documents\archetype-lab`, backend Django 6 di un sistema
RAG, interamente in **italiano**. Leggi `CLAUDE.md` prima di scrivere una riga.

**Presupposti già in essere:** `pytest` e `pytest-django` sono installati,
`pytest.ini` esiste, `rag/tests/conftest.py` contiene le fixture
(`cache_delle_factory_pulita`, `processo_senza_segnali`, `pipeline_predefinita`,
`utente`, `client_autenticato`, i tre PDF, `EmbeddingsFinti`,
`VectorStoreFinto`). `RetrievalProfile.excerpt_length` esiste.

**Obiettivo:** scrivere `rag/tests/test_segmentazione_e_factory.py` (T-36).

**Leggi prima:**
- `CLAUDE.md`
- `plans/2026-07-25-2132-P6-plan.md` §5 fase 3 — il codice integrale dei nove
  test
- `rag/services/factories.py` **per intero** — è il file sotto prova, e la sua
  docstring di modulo spiega perché la chiave della cache contiene i *valori*
  della configurazione e non solo l'id
- `rag/tests/conftest.py` — le fixture disponibili

**Da fare:** i punti da 3.1 a 3.8. Coprono: i valori del profilo che arrivano
allo splitter; il cambio di profilo che cambia la segmentazione; il caso limite
dei separatori vuoti (che significano «predefiniti», non «nessun separatore»);
i tre rifiuti espliciti (strategia a token, provider `huggingface`, provider
`openai_compatible`), che sono **limiti dichiarati e non guasti**;
`verify_embedding_dimension` nei due versi; `index_fingerprint()`; la lunghezza
dell'estratto che viene dal profilo.

**Il test che conta è 3.6**, e va scritto con cura: dimostra che a garantire
RF-22 è la **chiave** della cache e non il receiver di `signals.py`. Usa la
fixture `processo_senza_segnali`, che scollega il `post_save` e riproduce così
il processo worker, che quel segnale non lo riceve mai. Con il receiver
collegato il test passerebbe per la ragione sbagliata, restando verde anche se
la chiave contenesse il solo `pk`.

**Controprova obbligatoria, da eseguire e riportare:** sostituisci
temporaneamente la chiave di `get_llm` con `f"llm:{profile.pk}"` e verifica che
il test 3.6 **fallisca**. Poi ripristina. Un test che non può fallire non prova
nulla.

**Verifica:**
```powershell
.venv\Scripts\python.exe -m pytest rag\tests\test_segmentazione_e_factory.py -v
```

**Fatto quando:** tutti i test passano; la controprova è stata eseguita e
riportata; nessun test ha richiesto Ollama in esecuzione.

**Commit:** `P6: test di segmentazione e factory (T-36)` — senza alcun trailer
di attribuzione.

---

# Fase 4 — T-37: test della macchina a stati dell'ingestione

Sei in `C:\Users\vjiang\Documents\archetype-lab`, backend Django 6 di un sistema
RAG, interamente in **italiano**. Leggi `CLAUDE.md` prima di scrivere una riga.

**Presupposti già in essere:** l'impalcatura di pytest e `rag/tests/conftest.py`
con le fixture, fra cui i tre PDF (`pdf_con_testo`, `pdf_senza_testo`,
`pdf_illeggibile`) e le classi `EmbeddingsFinti` e `VectorStoreFinto`.

**Obiettivo:** scrivere `rag/tests/test_ingestione.py` (T-37).

**Leggi prima:**
- `CLAUDE.md`
- `plans/2026-07-25-2132-P6-plan.md` §5 fase 4 — il codice integrale dei test
- `rag/services/ingestion.py` **per intero**. La sua docstring di modulo spiega
  l'invariante che questi test proteggono: si scrive **prima in pgvector, poi in
  Django**, e gli id dei vettori sono deterministici (`"<document_id>:<ordinal>"`)
- `rag/services/loaders.py` — le due eccezioni tradotte, con le trappole di
  PyMuPDF documentate nei commenti
- `rag/services/exceptions.py` — la gerarchia
- `rag/models/domain.py` righe 150-236 — `Document.Status` e `needs_reindex`

**Attenzione — è l'errore più probabile di questa fase.** Le sostituzioni vanno
fatte su `rag.services.ingestion`, cioè **nel modulo che chiama**, non su
`rag.services.factories`: `ingestion.py` fa `from .factories import …`, quindi
il riferimento è già legato e riscrivere `factories` non avrebbe alcun effetto.
I nomi da sostituire sono tre: `get_embeddings`, `verify_embedding_dimension`,
`get_vectorstore`.

**Da fare:** i punti da 4.1 a 4.7. Coprono: il percorso felice (CA-2, con
impronta e `needs_reindex`); gli id deterministici su entrambe le metà dello
schema; l'idempotenza della reindicizzazione **con conservazione delle chiavi
primarie** (perché `RetrievedChunk.chunk` è `SET_NULL` e ricreare le righe
azzererebbe lo storico, RF-16); i lotti di `batch_size`; i tre fallimenti che
devono lasciare stato **e** motivo persistiti (CA-8, RNF-04: PDF senza testo,
PDF illeggibile, duplicato, configurazione irrealizzabile); l'accodamento che
riporta il documento «In attesa» azzerando l'errore.

**Da misurare prima di darlo per buono**, nel punto 4.7: che il percorso
`django_tasks.backends.dummy.DummyBackend` sia quello della 0.12.0 installata, e
che `settings.TASKS` riletto a caldo abbia effetto su `enqueue()` — il backend è
risolto attraverso un proxy. Se non lo fosse, il ripiego dichiarato è sostituire
`rag.tasks.indicizza_documento` con un oggetto finto che espone `.enqueue()`,
che prova comunque la coppia stato/errore, cioè ciò che quel test deve
dimostrare. **Non usare `ImmediateBackend`**: eseguirebbe l'ingestione in linea,
che è l'opposto di ciò che il test osserva.

**Verifica:**
```powershell
.venv\Scripts\python.exe -m pytest rag\tests\test_ingestione.py -v
git status --porcelain media
```

**Fatto quando:** tutti i test passano; nessuno ha richiesto Ollama; `media/`
non è stata sporcata (i test usano un `MEDIA_ROOT` temporaneo).

**Commit:** `P6: test della macchina a stati dell'ingestione (T-37)` — senza
alcun trailer di attribuzione.

---

# Fase 5 — T-38: test di `POST /api/ask/` con LLM sostituito

Sei in `C:\Users\vjiang\Documents\archetype-lab`, backend Django 6 di un sistema
RAG, interamente in **italiano**. Leggi `CLAUDE.md` prima di scrivere una riga.

**Presupposti già in essere:** l'impalcatura di pytest con le fixture di
`conftest.py` (fra cui `client_autenticato` e `VectorStoreFinto`), e
`RetrievalProfile.excerpt_length`.

**Obiettivo:** scrivere `rag/tests/test_api_ask.py` (T-38).

**Leggi prima:**
- `CLAUDE.md`
- `plans/2026-07-25-2132-P6-plan.md` §5 fase 5 — il codice integrale dei test
- `rag/views.py` righe 290-339 — `ask()`. La docstring spiega la mappatura dei
  codici e perché **l'ordine delle clausole `except` è significativo**
- `rag/services/query.py` righe 452-654 — `_esegui_interrogazione`, `_registra`,
  `rispondi`. L'intestazione del modulo spiega perché il punteggio esposto è la
  **rilevanza** (`1 - distanza`) e non la distanza grezza
- `rag/errors.py` — la rete di sicurezza di T-34

**I test stanno su due livelli, e la distinzione è deliberata:**
- **livello alto**: si sostituisce `rag.views.rispondi`, e si prova la sola
  mappatura dei codici della vista;
- **livello profondo**: si sostituiscono `get_llm` e `get_vectorstore` **dentro
  `rag.services.query`** (non in `factories`: il modulo fa
  `from .factories import …`, quindi i nomi sono già legati), e `rispondi()`
  gira per intero. È qui che si provano la soglia, la non-risposta, le fonti e
  il `QueryLog`.

**Da fare:** i punti da 5.1 a 5.7. Coprono: il percorso felice con le fonti di
RF-13 e il punteggio come rilevanza; **la non-risposta sotto soglia senza
interrogare l'LLM** (RF-14, CA-4 — il test più importante del file: si prova
contando le invocazioni, con un finto LLM che solleva se chiamato); il
`QueryLog` con i tempi separati e il rank che parte da 1; la traccia lasciata
anche dalle domande rifiutate (RNF-04); il **503** per LLM irraggiungibile
distinto dal 400; la pipeline disattivata rifiutata anche se richiesta
esplicitamente (RF-15); il **401** senza credenziali; il **500 JSON anche con
`DEBUG=True`** e il 404 in italiano (T-34).

**Due trappole da conoscere:**
- **pytest-django forza `settings.DEBUG = False`.** Il test 5.7 deve rialzarlo
  con la fixture `settings`, altrimenti proverebbe l'esatto contrario di ciò che
  afferma di provare;
- il finto LLM del test 5.4 deve reggere la composizione LCEL
  `prompt | llm | StrOutputParser()`. **Verificalo**: se non bastasse, il
  ripiego dichiarato è `RunnableLambda`, che è un Runnable per costruzione.

**Verifica:**
```powershell
.venv\Scripts\python.exe -m pytest rag\tests\test_api_ask.py -v
.venv\Scripts\python.exe -m pytest -q
```

Poi **ferma Ollama** e riesegui `pytest -q`: la suite deve passare lo stesso.
È la controprova della decisione D3 del piano, e va riportata.

**Fatto quando:** l'intera suite passa, anche con Ollama spento.

**Commit:** `P6: test di POST /api/ask/ con LLM sostituito (T-38)` — senza alcun
trailer di attribuzione.

---

# Fase 6 — T-41: script di dimostrazione riproducibile

Sei in `C:\Users\vjiang\Documents\archetype-lab`, backend Django 6 di un sistema
RAG con generazione ed embedding **locali** (Ollama sull'host). Il progetto è
interamente in **italiano**. Leggi `CLAUDE.md` prima di scrivere una riga.

**Questa fase richiede l'ambiente completo in funzione:** database, server,
worker e Ollama con i due modelli.

**Obiettivo:** `scripts/dimostrazione.ps1`, uno script che percorre il flusso
completo e lo rende **riproducibile**.

**Leggi prima:**
- `CLAUDE.md`
- `plans/2026-07-25-2132-P6-plan.md` §5 fase 6 — i sette passi richiesti e i
  requisiti dello script
- `README.md` righe 123-197 — i `curl` già scritti, che lo script deve rispettare
- `rag/views.py` — i codici di ritorno effettivi

**Sette passi, nell'ordine:** `/health` con arresto se una voce non è `ok`;
caricamento di `samples/manuale-dipendenti.pdf` attendendo **202** (non 201);
polling di `GET /api/documents/{id}/` fino a `indexed` o `failed`, con un limite
e un messaggio allo scadere che **nomina il worker** (è il sintomo più
probabile: senza worker il documento resta «In attesa» a tempo indeterminato);
domanda pertinente (CA-3); domanda fuori tema, che deve ricevere la
dichiarazione di non conoscenza (CA-4); elenco delle pipeline (RF-23);
riepilogo finale di quale criterio ogni passo ha dimostrato.

**Requisiti non negoziabili dello script:**
- parametri `-BaseUrl` (default `http://localhost:8000`), `-Utente`,
  `-Password`. **Nessuna credenziale scritta nel file**;
- `$ErrorActionPreference = "Stop"` e uscita diversa da zero al primo passo
  fallito, altrimenti «riproducibile» non significa nulla;
- il **409** sul caricamento **non è un errore**: significa che il documento
  c'era già da un'esecuzione precedente, e lo script prosegue con l'id
  restituito in `documento_esistente`. Senza questo ramo la seconda esecuzione
  fallirebbe, che è l'opposto di riproducibile;
- ogni passo stampa il tempo impiegato: sono i numeri che finiranno nel README.

In testa allo script, un commento che dichiari il limite: è l'unico script, gira
su Windows PowerShell perché è la macchina di consegna, e i `curl` equivalenti
per gli altri sistemi stanno nel README.

**Verifica:** eseguirlo **due volte di seguito** (la seconda esercita il ramo
409), e una terza volta **con il worker fermo**, verificando che fallisca con un
messaggio che nomina il worker e non con un timeout muto.

**Fatto quando:** le tre esecuzioni si comportano come descritto.

**Commit:** `P6: script di dimostrazione riproducibile (T-41)` — senza alcun
trailer di attribuzione.

---

# Fase 7 — T-39 e T-40: documentazione di consegna

Sei in `C:\Users\vjiang\Documents\archetype-lab`. **La documentazione è essa
stessa parte della consegna**: `REQUIREMENTS.md`, `ARCHITECTURE.md`, `PLAN.md`,
`BACKLOG.md` e `README.md` vanno tenuti allineati al codice. Tutto in
**italiano**. Leggi `CLAUDE.md` prima di scrivere una riga.

**Obiettivo:** portare il README da appunti di sviluppo a istruzioni di
consegna, e allineare gli altri documenti (T-39, T-40).

**Leggi prima:**
- `CLAUDE.md`
- `plans/2026-07-25-2132-P6-plan.md` §5 fase 7 — i dodici punti, uno per uno
- `README.md` per intero — cosa c'è già e cosa manca
- `plans/2026-07-25-1958-P5-plan-report.md` — i limiti **misurati** in P5, che
  vanno riportati con i loro numeri e non riassunti
- `ARCHITECTURE.md` §8 e §9, `REQUIREMENTS.md` §7 e §9, `BACKLOG.md`

**Regola sopra tutte:** ogni misura riportata deve venire da un'esecuzione
reale, mai da una stima. Se un numero non è stato misurato, non si scrive.

**Da fare:** i punti da 7.1 a 7.12. In sintesi:
- togliere dal README «Stato: in sviluppo»;
- **sezione «Prova guidata»**: dall'installazione alla prima risposta, con
  l'output atteso e i tempi reali;
- **sezione «Criteri di accettazione»**: CA-1 → CA-10, ciascuno con *come
  verificarlo* e *l'esito rilevato*. È la parte che chi valuta legge per prima —
  va compilata **dopo** le fasi 8 e 9, o lasciata con i posti segnati;
- **sezione «Test»**: `pytest`, che richiede PostgreSQL e **non** Ollama, con il
  perché di entrambi, e la nota che `manage.py test` non li raccoglie;
- **sezione «Limiti noti»**: l'elenco del punto 7.5 del piano, che raccoglie in
  un posto solo ciò che oggi è sparso fra i report;
- `ARCHITECTURE.md` §8: il compromesso su `excerpt_length`;
- **verificare e correggere** il rinvio della docstring di
  `rag/services/factories.py` righe 18-20, che dice «Il commento in
  config/settings/base.py … è da correggere in T-40»: quel commento **risulta
  già corretto** nel file, quindi il rinvio va tolto se lo è davvero;
- `REQUIREMENTS.md` §9: completare la tracciabilità con P5 e P6;
- `BACKLOG.md`: chiudere la sezione P6 con la stessa forma delle precedenti
  (perimetro svolto, tagli e perché, debiti residui), e annotare che T-41 e T-38
  sono state **svolte** e non tagliate;
- `PLAN.md` §P6: perimetro effettivo al posto di quello previsionale;
- `CLAUDE.md`: aggiornare «Stato» e la riga «**Test:** non esistono ancora», che
  dopo la fase 5 è falsa.

**Non toccare `plans/`**: è un registro storico e non si riscrive a posteriori.
`docs/docs-manifest.yaml` lo esclude deliberatamente dal riallineamento.

**Verifica:**
```powershell
Select-String -Path README.md -Pattern "in sviluppo"
Select-String -Path *.md -Pattern "LUNGHEZZA_ESTRATTO"
```
Entrambi devono essere vuoti. Poi rilettura incrociata: ogni id `T-xx`,
`RF-xx`, `CA-xx` citato deve esistere.

**Fatto quando:** il README si legge dall'inizio alla fine come istruzioni di
consegna; ogni criterio ha un modo di verificarlo; nessun documento contiene
affermazioni superate.

**Commit:** `docs: README di consegna, criteri di accettazione e limiti (T-39, T-40)`
— senza alcun trailer di attribuzione.

---

# Fase 8 e 9 — T-42 e T-43: le prove di consegna

> **Queste due fasi non sono automatizzabili e richiedono l'operatore.** La fase
> 8 comincia con un comando **distruttivo** e la fase 9 richiede di staccare
> fisicamente la rete della macchina. Chi esegue deve **chiedere conferma prima
> di ciascuna delle due**, non procedere da solo.

Sei in `C:\Users\vjiang\Documents\archetype-lab`. Leggi `CLAUDE.md` e
`plans/2026-07-25-2132-P6-plan.md` §5 fasi 8 e 9 prima di cominciare.

## Fase 8 — T-42: prova da zero su ambiente pulito (CA-1)

**Obiettivo:** dimostrare che l'ambiente si avvia da zero seguendo il **solo**
README.

**Prima di tutto, chiedi conferma all'operatore.** Il primo passo è

```powershell
docker compose down -v
Remove-Item -Recurse -Force media -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .venv
```

e `down -v` **cancella il volume `pgdata`**, cioè tutti i documenti indicizzati e
tutto lo storico delle interrogazioni. È ciò che CA-1 richiede e **non è
reversibile**.

**Poi:** eseguire i comandi del README **così come sono scritti**, senza
supplire con conoscenza pregressa. Ogni volta che serve un passo che il README
non dice, quello è un difetto del README: si annota, si corregge il README, e si
**riparte da capo**. Cronometrare ogni passo — i numeri servono alla «Prova
guidata» di T-39. Poi `pytest` sull'ambiente ricostruito (è la verifica che le
dipendenze di test siano davvero in `requirements.txt`), poi
`scripts/dimostrazione.ps1`, poi i dieci criteri di accettazione uno per uno,
registrando per ciascuno l'esito reale.

**Fatto quando:** l'ambiente si avvia dal solo README senza passi impliciti;
`pytest` passa sull'ambiente ricostruito; CA-2 → CA-9 sono verificati e
annotati; ogni correzione al README è stata applicata **e** la sequenza
rieseguita.

## Fase 9 — T-43: prova a rete staccata (RNF-01)

**Obiettivo:** trasformare la garanzia «nulla esce dalla macchina» da promessa
in verifica.

**Chiedi conferma all'operatore prima di procedere**: la fase richiede di
disattivare **tutte** le interfacce di rete della macchina. `localhost`
continua a funzionare, ed è esattamente il punto della dimostrazione — database,
Ollama e applicazione stanno tutti sulla macchina.

**Poi:** con la rete staccata, eseguire il ciclo completo — caricamento di un
PDF **mai indicizzato prima**, attesa del worker, domanda pertinente, domanda
fuori tema. Registrare i tempi e confrontarli con quelli a rete attiva: **non
devono differire**, e questo è l'argomento. Registrare l'output completo,
compreso quello del worker: un tentativo di uscita fallito comparirebbe come
errore di risoluzione DNS o di connessione, ed è ciò che si sta cercando.

Riattaccare la rete e riportare l'esito in `ARCHITECTURE.md` §9 e nella sezione
«Criteri di accettazione» del README (CA-9), **con la data e la procedura
seguita**: una garanzia verificata una volta e non documentata torna a essere
una promessa.

**Fatto quando:** caricamento, indicizzazione e interrogazione riescono a rete
staccata; nessun errore di rete nei log; `ARCHITECTURE.md` §9 e il README
riportano l'esito con la data.

**Commit:** `docs: esiti delle prove di consegna (T-42, T-43)` — senza alcun
trailer di attribuzione.

---

# Dopo l'ultima fase

Compilare `plans/2026-07-25-2132-P6-plan-report.md` con ciò che è **successo
davvero**, scostamenti compresi. Il report non è un riassunto del piano: dice
cosa è stato misurato, cosa è stato tagliato e perché, e quali debiti restano
aperti. È un registro storico e non si riscrive a posteriori.
