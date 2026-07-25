# Prompt dei sub-agenti — Piano P4 (API REST)

Piano di riferimento: [2026-07-25-0900-P4-plan.md](2026-07-25-0900-P4-plan.md).

Cinque fasi, cinque sub-agenti **in sequenza**: ognuno parte dal commit lasciato
dal precedente. I prompt sono scritti per essere incollati così come sono; ciò
che non è scritto qui va cercato nel piano, non inventato.

L'orchestratore, fra una fase e l'altra:

1. legge la sezione di report scritta dal sub-agente;
2. verifica che il commit esista e che il working tree sia pulito;
3. se una fase ha prodotto uno **scostamento**, decide se le fasi successive
   vanno adeguate **prima** di lanciarle.

---

# Prerequisiti (valgono per tutti)

Da verificare all'inizio della **prima** fase e da ricontrollare se una fase
successiva fallisce in modo strano.

## Servizi

| Che cosa | Comando | Atteso |
|---|---|---|
| PostgreSQL + pgvector | `docker ps` | `archetype-lab-db-1 … (healthy)`, porta 5434 |
| Ollama | `curl -s -m 5 http://localhost:11434/api/tags` | HTTP 200 |
| Modelli | `ollama list` | `qwen2.5:7b-instruct`, `bge-m3` |

Se una fase spegne Ollama per una prova, **deve** poi terminare anche i processi
`llama-server` figli: sopravvivono al padre, occupano la VRAM e fanno fallire il
caricamento successivo con un 500 di out-of-memory che sembra un difetto del
codice. Costato mezz'ora in P3.

## Ambiente

- Interprete: `.venv/Scripts/python.exe`, dalla radice del progetto.
- `DJANGO_SETTINGS_MODULE` **non** impostato: `manage.py` usa `config.settings.dev`.
- Versioni attese: Django 6.0.7, **djangorestframework 3.17.1**, langchain-core
  1.5.1, langchain-ollama 1.1.0, langchain-postgres 0.0.17, httpx 0.28.1.
- `curl` disponibile.

## Stato del database (misurato il 25/07/2026)

- Documenti: uno, **id 7**, `manuale-dipendenti.pdf`, `indexed`, 3 segmenti.
- Base di conoscenza: una, **id 5**, collezione `default`.
- Pipeline: una, **id 3**, «Pipeline predefinita», attiva e predefinita.
- Profili: LLM 4 (temperatura 0,0), recupero 3 (`similarity`, `top_k` 4, soglia
  0,5), prompt 3.
- `QueryLog`: 40. Utenti: `admin` (superuser, **password ignota**).

Se i numeri non coincidono: **annotarlo nel report** e adeguare le asserzioni,
non i dati.

## Repository

- Branch `main`, working tree pulito, P3 chiusa.
- I tre file di `plans/` di questo piano restano **non tracciati**: li committa
  l'orchestratore alla chiusura di P4.

## File del report

`plans/2026-07-25-0900-P4-plan-report.md`. Ogni fase **aggiunge** la propria
sezione in coda; nessuna riscrive quelle altrui. Se il file non esiste, la prima
fase lo crea con l'intestazione e la tabella dei prerequisiti verificati.

---

# Regole valide per TUTTI i sub-agenti

1. **Il codice si copia dal piano carattere per carattere**, docstring e commenti
   compresi. Quei commenti contengono misure: riscriverli «meglio» perde
   l'informazione che li ha prodotti.
2. **Se il piano è sbagliato, si segnala — non si aggiusta in silenzio.** Se una
   *misura* impone di scostarsi (è successo in P3 con `except OSError`), si
   scosta, si misura di nuovo e si scrive nel report la misura che lo impone.
3. **Gli script di verifica NON entrano nel repository.** Si scrivono nella
   directory scratch della sessione e si eseguono così:
   ```
   .venv/Scripts/python.exe manage.py shell -c "exec(open(r'<percorso>', encoding='utf-8').read())"
   ```
4. **Una verifica che non può fallire non è una verifica.** Dove il piano chiede
   un controllo negativo, va eseguito: senza, l'asserzione non distingue il
   codice giusto da quello sbagliato.
5. **Non si tocca nulla fuori dal perimetro della fase.** In particolare: niente
   modifiche a `rag/models/`, `rag/admin.py`, `rag/services/ingestion.py`,
   `rag/services/factories.py`, `requirements*.txt`. L'unico file di P3 che P4
   modifica è `rag/services/query.py`, con **una sola aggiunta**, nella fase 3.
6. **Nessuna migrazione.** Ogni fase chiude con
   `makemigrations --check --dry-run` e riporta l'uscita. Se comparisse una
   migrazione, **fermarsi** e riferire: significa che qualcosa è stato toccato
   che non doveva esserlo.
7. **Un commit per fase**, con il messaggio indicato. Il messaggio è in italiano,
   descrive che cosa fa il codice e **non contiene alcun trailer di
   co-attribuzione** (niente `Co-Authored-By`, per nessun motivo, in nessuna
   forma). È una richiesta esplicita dell'utente.
8. **Non committare i file di `plans/`**: restano non tracciati fino alla
   chiusura di P4.
9. **Il report è parte della consegna, non un riassunto di cortesia.** Ci vanno
   l'output reale dei comandi, i tempi misurati e gli scostamenti. Un «tutto ok»
   senza output non è accettabile.
10. **Prima di dichiarare finita la fase**, rileggere l'elenco «Hai finito
    quando» del proprio prompt, punto per punto.

---

# Fase 1 — Serializer e `POST /api/documents/` (T-28)

Sei il sub-agente della fase 1 del piano P4. Leggi
`plans/2026-07-25-0900-P4-plan.md`, sezioni 1–5 e «Fase 1», e attieniti ad esse.

## Cosa devi fare

Quattro passi, tutti descritti nel piano con il codice da copiare:

- **1.1** creare `rag/serializers.py` con `DocumentSerializer` e
  `DocumentUploadSerializer`;
- **1.2** sostituire intestazione e blocco import di `rag/views.py` (il blocco
  contiene anche import che serviranno alle fasi 2–4: si scrivono ora una volta
  sola);
- **1.3** aggiungere in coda a `rag/views.py` la sezione «API REST (P4)» con
  `_base_di_conoscenza_predefinita()` e `documenti()`;
- **1.4** aggiungere la rotta `api/documents/` in `rag/urls.py`.

## Prima di scrivere codice, leggi questi file

- `rag/services/ingestion.py` — `compute_checksum()`, `trova_duplicato()`,
  `ingest_document()`: sono i tre pezzi che la vista orchestra, e la loro
  docstring spiega perché l'ordine conta.
- `rag/admin.py`, `DocumentAdminForm.clean()` e `DocumentAdmin.save_model()` —
  fanno **la stessa cosa** che deve fare la tua vista, dall'altro ingresso.
  Se il tuo codice diverge da quello, chiediti perché prima di procedere.
- `rag/management/commands/ingest.py` — la regola della base di conoscenza
  predefinita.
- `rag/models/domain.py`, `Document` — stati, vincoli, `needs_reindex`.

## Le tre trappole di questa fase

1. **La deduplica precede la scrittura.** Se crei la riga e poi controlli, ogni
   duplicato rifiutato lascia un file orfano in `MEDIA_ROOT`. Il punto 2 della
   verifica controlla che il conteggio dei documenti **non** cresca: è lì per
   accorgersene.
2. **`compute_checksum()` riporta il puntatore del file a zero.** Se lo
   sostituisci con un `hashlib.sha256(file.read())` scritto da te, salverai un
   PDF di **zero byte**. Accertato in P2, non teorico.
3. **Il PDF senza testo produce 422, non 500 e non 201.** La riga deve
   sopravvivere con stato «Fallito» e il motivo: cancellarla per fare pulizia
   distruggerebbe la traccia che RNF-04 chiede.

## Verifica

Lo script `fase1.py` è nel piano, completo. Genera i PDF con PyMuPDF: `samples/`
ne ha uno solo e ricaricarlo darebbe 409 invece del 201 che serve a provare il
percorso felice.

Il punto 7 interroga Ollama per l'embedding: se il modello va caricato costa fino
a ~10 s. Non è un blocco.

## Hai finito quando

- [ ] I sette punti passano, e nel report c'è l'output **testuale**.
- [ ] Nel report: il messaggio reale del validatore sull'estensione (punto 3), il
      tempo di ingestione via API (punto 1), il motivo persistito (punto 6).
- [ ] `makemigrations --check --dry-run` → «No changes detected», uscita 0.
- [ ] `manage.py check` → nessun problema.
- [ ] `git status --short`: solo `rag/serializers.py` (nuovo), `rag/views.py`,
      `rag/urls.py`, più i file di `plans/` non tracciati.
- [ ] Commit `P4: serializer e caricamento documenti via API (T-28)`, senza
      trailer di co-attribuzione.
- [ ] Sezione del report scritta, con gli scostamenti se ce ne sono stati.

---

# Fase 2 — Elenco e stato dei documenti (T-29)

Sei il sub-agente della fase 2 del piano P4. Parti dal commit della fase 1.

## Cosa devi fare

- **2.1** estendere il decoratore di `documenti()` a `["GET", "POST"]`, aggiungere
  la diramazione `if request.method == "GET": return _elenco(request)` come
  **prima** istruzione, e la riga di docstring indicata;
- **2.2** aggiungere `_elenco()` e `documento()`;
- **2.3** aggiungere la rotta di dettaglio in `rag/urls.py`.

## Prima di scrivere codice, leggi questi file

- `rag/views.py` come l'ha lasciato la fase 1.
- `rag/admin.py`, `DocumentAdmin.list_select_related` — è lo stesso problema di
  N+1 che `_elenco()` deve evitare, risolto lì nello stesso modo.
- `rag/models/domain.py`, `Document.needs_reindex` — capisci **quante**
  dereferenziazioni fa, o non capirai perché le `select_related` sono
  obbligatorie.

## Le due trappole di questa fase

1. **Il decoratore.** Se scrivi `@api_view(["GET"])` invece di
   `["GET", "POST"]`, la POST della fase 1 comincia a rispondere **405** e nessuna
   delle verifiche 1–5 se ne accorge. Il punto 6 esiste per questo: è una
   verifica di non regressione, non un extra.
2. **N+1.** La verifica misura le query con `CaptureQueriesContext` **al crescere
   delle righe**: se il conteggio cresce, mancano le `select_related`. È il
   difetto che la verifica incrociata di P3 ha trovato nell'inline dello storico
   — non ripeterlo il giorno dopo averlo annotato.

## Hai finito quando

- [ ] I sei punti passano; nel report i **due conteggi di query** del punto 2.
- [ ] `makemigrations --check --dry-run` → «No changes detected».
- [ ] `git status --short`: solo `rag/views.py` e `rag/urls.py`.
- [ ] Commit `P4: elenco e stato dei documenti via API (T-29)`.

---

# Fase 3 — `POST /api/ask/` (T-30)

Sei il sub-agente della fase 3 del piano P4. È la fase che abilita CA-3, CA-4 e
CA-7 sul canale con cui i criteri di accettazione sono scritti.

## Cosa devi fare

- **3.1** aggiungere `EsitoInterrogazione.come_payload()` in
  `rag/services/query.py` (fra la property `fonti` e `__str__`);
- **3.2** far usare quel payload a `manage.py ask --json`, sostituendo il
  dizionario scritto a mano e **conservando** il commento su `ensure_ascii`;
- **3.3** aggiungere `AskSerializer` a `rag/serializers.py`;
- **3.4** aggiungere la vista `ask()` a `rag/views.py`, estendendo gli import
  esistenti (non duplicarli);
- **3.5** aggiungere la rotta `api/ask/`.

## ATTENZIONE — tocchi un file di P3

`rag/services/query.py` è codice di P3, verificato e committato. La tua modifica
è **un'aggiunta**: un metodo nuovo dentro una dataclass. Nessuna riga esistente
cambia comportamento, e `git diff` deve mostrarlo. Se ti ritrovi a modificare
`rispondi()`, `_registra()` o la clausola `except (OSError, httpx.TransportError)`,
**fermati**: stai facendo qualcosa che il piano non chiede.

## Prima di scrivere codice, leggi questi file

- `rag/services/query.py` **per intero**. Soprattutto: `rispondi()` (che cosa
  solleva e quando), `EsitoInterrogazione` (i campi e la property `fonti`),
  `seleziona_pipeline()` (le quattro forme di RF-15 e il controllo su
  `is_active`).
- `rag/services/exceptions.py` — la gerarchia. `LlmNonRaggiungibile` **è** un
  `QueryError`: da qui viene la trappola 1.
- `rag/management/commands/ask.py` — il tuo payload deve restare identico al suo.

## Le tre trappole di questa fase

1. **L'ordine delle clausole `except`.** `LlmNonRaggiungibile` è sottoclasse di
   `QueryError`: se metti `except QueryError` per prima, il ramo 503 non sarà mai
   raggiunto e **nessuna verifica scritta con domande pertinenti se ne
   accorgerà**. Il punto 7 della verifica esiste solo per questo, e il suo
   controllo negativo (7b) è ciò che lo rende non vuoto.
2. **Non riscrivere il dominio nel serializer.** `allow_blank=True` e
   `trim_whitespace=False` sono voluti: la domanda vuota la respinge il servizio,
   con il suo messaggio. Il punto 4 controlla che a rispondere sia stato il
   servizio e **non** DRF.
3. **Non scrivere il `QueryLog` nella vista.** È già scritto — anche per le
   richieste rifiutate e per quelle fallite. Una seconda scrittura produrrebbe
   righe doppie e un `QueryLog.error` in due copie.

## Verifica

Lo script `fase3.py` è nel piano. Due avvertenze:

- il punto 2 esegue **davvero** `manage.py ask --json` in un sottoprocesso: a
  freddo può richiedere ~25 s, e `timeout=300` è la misura di P3, non prudenza;
- il punto 7 sostituisce `rag.views.rispondi` e **lo ripristina** in un `finally`.
  Se lo script si interrompe a metà, riesegui lo shell da capo: uno shell con la
  funzione sostituita produce risultati falsi.

## Hai finito quando

- [ ] Gli otto punti passano.
- [ ] Nel report ci sono **le risposte reali** ai punti 1 e 3, con fonti,
      punteggi e tempi separati.
- [ ] `git diff rag/services/query.py` mostra **solo** l'aggiunta del metodo.
- [ ] `makemigrations --check --dry-run` → «No changes detected».
- [ ] Commit `P4: interrogazione via API con selezione della pipeline (T-30)`.

---

# Fase 4 — `GET /api/pipelines/` e autenticazione (T-31)

Sei il sub-agente della fase 4 del piano P4. È la fase che **chiude** le API:
dopo di te nulla risponde più a un anonimo, tranne `/health`.

## Cosa devi fare

- **4.1** `RagPipelineSerializer` in `rag/serializers.py`;
- **4.2** la vista `pipelines()` e la rotta;
- **4.3** sostituire il blocco `REST_FRAMEWORK` in `config/settings/base.py` con
  quello del piano, **commento compreso**: contiene la misura che giustifica
  l'ordine delle classi.

## Prima di scrivere codice, leggi questi file

- `config/settings/base.py` — il blocco `REST_FRAMEWORK` attuale e il commento su
  `CACHES`, che è l'esempio di come questo progetto scrive le decisioni nel punto
  in cui vivono.
- `rag/views.py`, `health()` — ha già `@permission_classes([AllowAny])`: è il
  motivo per cui sopravvive alla tua modifica. **Verificalo**, non darlo per
  scontato (punto 4).
- `rag/models/domain.py`, `RagPipeline` — quali profili appende, per il
  serializer.

## Le due trappole di questa fase

1. **401 contro 403.** DRF costruisce `WWW-Authenticate` dal **primo**
   autenticatore: con `SessionAuthentication` per prima riceveresti **403**
   senza header, e `curl -u` non avrebbe modo di reagire. Il piano mette
   `BasicAuthentication` per prima proprio per questo. Il punto 1 della verifica
   **misura** il codice: se osservi 403, non è un dettaglio estetico — riporta
   la misura e correggi l'ordine.
2. **Non aggiungere `rest_framework.authtoken`.** Porterebbe quattro migrazioni,
   e la decisione 9 del piano lo esclude. Se ti viene la tentazione perché «i
   token sono più puliti», scrivilo nel report come proposta per P6, non nel
   codice.

## Hai finito quando

- [ ] I sette punti passano; nel report **il codice osservato** al punto 1 con
      l'header `WWW-Authenticate`.
- [ ] `makemigrations --check --dry-run` → «No changes detected» — è anche la
      prova che non hai aggiunto `authtoken`.
- [ ] Il punto 7 conferma che l'admin è ancora riservato (RF-30 non regredito).
- [ ] Commit `P4: elenco delle pipeline e autenticazione degli endpoint (T-31)`.

---

# Fase 5 — Verifica di fase con `curl` e report

Sei il sub-agente della fase 5 del piano P4. **Non hai modifiche di codice da
fare.** Il tuo lavoro è dimostrare che il sistema funziona *davvero* attraverso
la rete, e scrivere il documento che lo prova.

## L'ambiente della prova

1. **Utente dedicato.** La password di `admin` non è nota. Crea `curl_p4` con una
   password che generi tu, usala, e **cancellalo** alla fine. Nel report va il
   nome utente, **non** la password.
2. **Server:** `manage.py runserver 127.0.0.1:8000 --noreload`, in background.
   `--noreload` è obbligatorio: con il reloader i processi sono due e la
   dimostrazione del punto (h) diventa ambigua. **Spegnilo** alla fine.
3. **Timeout:** ogni `curl` con `--max-time 180`.
4. **PDF:** generane uno nuovo con PyMuPDF. `samples/manuale-dipendenti.pdf` è
   già indicizzato e darebbe 409.

## L'ordine conta

(a) → (j) nell'ordine del piano. Il punto (c) dipende dal file caricato in (b);
il punto (h) ha senso solo con il server **acceso** dall'inizio e mai riavviato.

## La verifica di fase — dieci punti

Sono descritti nel piano, sezione «Fase 5». Per ognuno servono **il comando
eseguito e l'uscita reale**: un riassunto non è una prova.

Il punto che vale di più è **(h)**: cambiare `top_k` da un *altro* processo
mentre il server è acceso, e vedere cambiare il numero di fonti. È RF-22
dimostrata nella forma più forte — il processo del server non ha mai ricevuto il
`post_save`, e vede lo stesso il valore nuovo perché la chiave della cache
contiene `updated_at`. Se il numero di fonti **non** cambia, non aggiustare la
prova: hai trovato un difetto, e va scritto.

Il punto **(i)** (CA-7) richiede di creare una seconda pipeline e un secondo
prompt dallo shell, porre la **stessa** domanda due volte cambiando solo
`"pipeline"`, e rimuovere tutto alla fine.

## Hai finito quando

- [ ] I dieci punti sono eseguiti e riportati con comandi e uscite reali.
- [ ] Documento, pipeline, prompt e utente di prova sono stati **rimossi**; il
      runserver è **spento**; il corpus è tornato allo stato iniziale (un
      documento, una pipeline).
- [ ] `makemigrations --check --dry-run` e `manage.py check` puliti;
      `git diff --stat requirements.in requirements.txt` vuoto.
- [ ] Commit `P4: verifica di fase end-to-end via curl` (contiene solo il report,
      se non hai toccato codice; se non c'è nulla da committare, dillo).
- [ ] Il report finale è completo — vedi sotto.

## Il report finale — è parte della consegna

`plans/2026-07-25-0900-P4-plan-report.md` deve contenere:

1. la tabella dei **prerequisiti verificati**, con l'esito reale;
2. una sezione **per fase**, scritta dal sub-agente che l'ha eseguita, con
   comandi, output, scostamenti e il loro motivo;
3. i **dieci punti** della verifica di fase, con le uscite di `curl`;
4. i **tempi misurati per via HTTP**: upload, interrogazione a caldo e a freddo.
   Servono a T-39 (README) e a P5 (timeout);
5. il **registro dell'orchestrazione**: che cosa è andato storto e come è stato
   recuperato. Le fasi senza sorprese si scrivono in una riga; quelle con
   sorprese sono le più utili del documento;
6. la **consegna a P5 e a P6**, cioè la sezione 6 del piano aggiornata con ciò
   che l'esecuzione ha scoperto;
7. una riga sullo **stato del sistema alla chiusura di P4**: commit, migrazioni
   (nessuna), dipendenze (nessuna), corpus, storico.

Scrivi ciò che è successo, non ciò che doveva succedere. In P3 le tre righe più
utili del report sono state quelle in cui una verifica non poteva fallire, il
piano è stato corretto da una misura, e un incidente d'ambiente ha spiegato
perché `QueryLog.error` esiste.
