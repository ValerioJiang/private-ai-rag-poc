<#
.SYNOPSIS
    Percorre da capo a fondo il flusso del sistema RAG e ne dimostra i criteri
    di accettazione (T-41).

.DESCRIPTION
    Sette passi nell'ordine: presupposti (/health), caricamento del PDF di
    esempio, attesa dell'indicizzazione, domanda pertinente (CA-3), domanda
    fuori tema (CA-4), elenco delle pipeline (RF-23), riepilogo.

    LIMITE DICHIARATO (decisione D6 del piano di P6). Questo e' l'UNICO script
    di dimostrazione e gira su Windows PowerShell 5.1, perche' quella e' la
    macchina di consegna su cui girano anche le prove T-42 e T-43. Non esiste
    un gemello .sh: uno script mai eseguito e' peggio della sua assenza, e la
    via portabile c'e' gia' — i `curl` equivalenti, uno per endpoint, sono
    scritti per esteso nella sezione «API» del README.

    Nessuna credenziale e' scritta qui dentro: utente e password arrivano da
    parametro. Lo script non scrive nulla su disco e non modifica la
    configurazione: l'unico effetto collaterale e' il documento caricato, che
    alla seconda esecuzione viene riconosciuto come duplicato (409).

.EXAMPLE
    .\scripts\dimostrazione.ps1 -Utente dimostrazione -Password ********

.EXAMPLE
    # Con pochi tentativi: e' il modo di provare il messaggio «worker fermo»
    # senza attendere i due minuti predefiniti.
    .\scripts\dimostrazione.ps1 -Utente dimostrazione -Password ******** -TentativiMax 5
#>

[CmdletBinding()]
param(
    [string]$BaseUrl = "http://localhost:8000",

    [Parameter(Mandatory = $true)]
    [string]$Utente,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    # Il limite del polling del passo 3. 60 x 2 s = due minuti, contro i 16 s a
    # freddo e i 6 s a caldo misurati in T-41 sul PDF di esempio: il limite
    # scatta solo se la coda non la lavora nessuno.
    [int]$TentativiMax = 60,
    [int]$IntervalloSecondi = 2
)

# Senza questa riga un passo fallito proseguirebbe, e «riproducibile» non
# significherebbe nulla: ogni errore diventa terminante e finisce nel catch
# finale, che e' l'unico punto che stampa il fallimento e esce con codice 1.
$ErrorActionPreference = "Stop"

# La barra di avanzamento di Invoke-WebRequest non serve a uno script che
# stampa gia' il tempo di ogni passo, e sporcherebbe l'output da cui quei
# tempi si leggono.
$ProgressPreference = "SilentlyContinue"

$PdfDimostrazione = Join-Path $PSScriptRoot "..\samples\manuale-dipendenti.pdf"
$DomandaPertinente = "Quanti giorni di ferie si maturano all'anno?"
$DomandaFuoriTema = "Qual e' la capitale dell'Australia?"

# Basic PREEMPTIVO, costruito a mano invece di passare -Credential: cosi' le
# credenziali viaggiano gia' sulla prima richiesta, senza dipendere da una
# sfida 401 del server che l'API potrebbe non mandare.
$coppia = "{0}:{1}" -f $Utente, $Password
$Intestazioni = @{
    Authorization = "Basic " + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($coppia))
    Accept        = "application/json"
}

$Riepilogo = New-Object System.Collections.ArrayList


function Invoke-Richiesta {
    <#
        Un solo punto di contatto con l'API, che NON solleva sui codici di
        errore HTTP: 409 sul caricamento e 503 su /health sono esiti previsti
        di cui lo script deve leggere il corpo, e con $ErrorActionPreference =
        "Stop" un Invoke-WebRequest nudo li trasformerebbe in un'eccezione
        prima che qualcuno possa guardarci dentro.

        Resta terminante il solo guasto di trasporto — server spento,
        connessione rifiutata — riconoscibile perche' l'eccezione non porta
        alcuna risposta.
    #>
    param(
        [string]$Metodo = "GET",
        [Parameter(Mandatory = $true)][string]$Percorso,
        $Corpo = $null,
        [string]$TipoContenuto,
        [int]$TimeoutSec = 60
    )

    $parametri = @{
        Uri             = "$BaseUrl$Percorso"
        Method          = $Metodo
        Headers         = $Intestazioni
        TimeoutSec      = $TimeoutSec
        UseBasicParsing = $true
    }
    if ($null -ne $Corpo) { $parametri.Body = $Corpo }
    if ($TipoContenuto) { $parametri.ContentType = $TipoContenuto }

    try {
        $risposta = Invoke-WebRequest @parametri
        $codice = [int]$risposta.StatusCode
        # NON $risposta.Content. DRF risponde «application/json» senza charset, e
        # in assenza di charset Invoke-WebRequest di PowerShell 5.1 decodifica in
        # ISO-8859-1: la risposta «L'indennita' e' di 45 euro» con le accentate
        # vere usciva «L'indennitÃ  Ã¨ di 45 euro». Misurato il 26/07/2026 durante
        # il collaudo di prova-rete-staccata.ps1, che aveva ereditato da qui la
        # stessa forma. I byte grezzi sono UTF-8 e vanno letti come tali.
        $flusso = $risposta.RawContentStream
        $flusso.Position = 0
        $lettore = New-Object System.IO.StreamReader($flusso, [Text.Encoding]::UTF8)
        try { $testo = $lettore.ReadToEnd() } finally { $lettore.Close() }
    }
    catch {
        $rispostaErrore = $_.Exception.Response
        if ($null -eq $rispostaErrore) { throw }
        $codice = [int]$rispostaErrore.StatusCode
        # $_.ErrorDetails.Message PRIMA dello stream, e non e' indifferente:
        # osservato durante T-41 su questa macchina, Invoke-WebRequest di
        # PowerShell 5.1 ha gia' letto il corpo della risposta di errore e lo
        # stream torna VUOTO. Con il solo stream il ramo 409 leggeva un
        # documento_esistente nullo e il passo 3 chiedeva /api/documents//,
        # cioe' un 404: la seconda esecuzione falliva, che e' esattamente cio'
        # che quel ramo esiste per evitare.
        $testo = $_.ErrorDetails.Message
        if ([string]::IsNullOrEmpty($testo)) {
            $flusso = $rispostaErrore.GetResponseStream()
            $lettore = New-Object System.IO.StreamReader($flusso, [Text.Encoding]::UTF8)
            try { $testo = $lettore.ReadToEnd() } finally { $lettore.Close() }
        }
    }

    $dati = $null
    if ($testo) {
        # rag/errors.py garantisce JSON su ogni risposta di /api/, DEBUG
        # compreso; il try resta per le rotte fuori da /api/ (p.es. un 404 di
        # Django su un BaseUrl sbagliato), dove il corpo e' HTML.
        try { $dati = $testo | ConvertFrom-Json } catch { $dati = $null }
    }

    [pscustomobject]@{ Codice = $codice; Dati = $dati; Testo = $testo }
}


function Invoke-Caricamento {
    <#
        multipart/form-data costruito a mano: PowerShell 5.1 non ha il
        parametro -Form (arrivato con PowerShell 6). Il PDF si legge come byte
        e si trasporta come stringa iso-8859-1, l'unica codifica che mappa i
        256 valori di un byte su altrettanti caratteri senza perdite: qualunque
        altra corromperebbe il file, e il worker riporterebbe un PDF illeggibile
        che illeggibile non era.
    #>
    param([Parameter(Mandatory = $true)][string]$Percorso)

    $nomeFile = Split-Path $Percorso -Leaf
    $latin1 = [Text.Encoding]::GetEncoding("iso-8859-1")
    $contenuto = $latin1.GetString([IO.File]::ReadAllBytes($Percorso))
    $confine = "confine-{0}" -f ([guid]::NewGuid().ToString("N"))

    $righe = @(
        "--$confine",
        "Content-Disposition: form-data; name=`"file`"; filename=`"$nomeFile`"",
        "Content-Type: application/pdf",
        "",
        $contenuto,
        "--$confine--",
        ""
    )
    $corpo = $latin1.GetBytes(($righe -join "`r`n"))

    Invoke-Richiesta -Metodo "POST" -Percorso "/api/documents/" -Corpo $corpo `
        -TipoContenuto "multipart/form-data; boundary=$confine" -TimeoutSec 120
}


function Invoke-Domanda {
    param(
        [Parameter(Mandatory = $true)][string]$Domanda,
        # 300 s e non 180 come il README: la prima interrogazione di un server
        # appena avviato carica il modello in VRAM, e il margine evita che una
        # dimostrazione a freddo fallisca per un'attesa che non e' un guasto.
        [int]$TimeoutSec = 300
    )
    $corpo = @{ domanda = $Domanda } | ConvertTo-Json -Compress
    Invoke-Richiesta -Metodo "POST" -Percorso "/api/ask/" `
        -Corpo ([Text.Encoding]::UTF8.GetBytes($corpo)) `
        -TipoContenuto "application/json; charset=utf-8" -TimeoutSec $TimeoutSec
}


function Scrivi-Titolo {
    param([int]$Numero, [string]$Testo)
    Write-Host ""
    Write-Host ("[{0}/7] {1}" -f $Numero, $Testo) -ForegroundColor Cyan
}


function Chiudi-Passo {
    <# Il tempo di ogni passo e' un risultato, non decorazione: sono i numeri
       che finiscono nel README e nel report di T-42. #>
    param(
        [int]$Numero,
        [string]$Descrizione,
        [string]$Criterio,
        [Diagnostics.Stopwatch]$Cronometro
    )
    $secondi = [math]::Round($Cronometro.Elapsed.TotalSeconds, 2)
    Write-Host ("       concluso in {0} s" -f $secondi) -ForegroundColor DarkGray
    [void]$Riepilogo.Add([pscustomobject]@{
            Passo     = $Numero
            Operazione = $Descrizione
            Criterio  = $Criterio
            Secondi   = $secondi
        })
}


try {
    Write-Host ""
    Write-Host "Dimostrazione del sistema RAG — $BaseUrl (utente: $Utente)" -ForegroundColor White

    if (-not (Test-Path $PdfDimostrazione)) {
        throw "Il PDF della dimostrazione non esiste: $PdfDimostrazione"
    }
    $PdfDimostrazione = (Resolve-Path $PdfDimostrazione).Path
    Write-Host "PDF: $PdfDimostrazione" -ForegroundColor DarkGray

    # ---------------------------------------------------------------- passo 1
    # /health e' anonimo di proposito e riporta quattro voci. Fermarsi qui,
    # nominando la voce guasta, e' il modo piu' corto di diagnosticare
    # l'ambiente: senza questo passo un database spento si manifesterebbe come
    # un 500 al passo 2.
    Scrivi-Titolo 1 "Presupposti: GET /health"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $salute = Invoke-Richiesta -Percorso "/health" -TimeoutSec 30
    if ($null -eq $salute.Dati) {
        throw "GET /health non ha risposto JSON (codice $($salute.Codice)). BaseUrl sbagliato, o il server non e' quello del progetto."
    }
    foreach ($voce in $salute.Dati.checks.PSObject.Properties) {
        $stato = if ($voce.Value.ok) { "ok" } else { "GUASTO" }
        $colore = if ($voce.Value.ok) { "Green" } else { "Red" }
        Write-Host ("       {0,-10} {1,-7} {2}" -f $voce.Name, $stato, $voce.Value.detail) -ForegroundColor $colore
    }
    $guaste = @($salute.Dati.checks.PSObject.Properties | Where-Object { -not $_.Value.ok })
    if ($guaste.Count -gt 0) {
        $elenco = ($guaste | ForEach-Object { "«$($_.Name)»: $($_.Value.detail)" }) -join " · "
        throw "Presupposti non soddisfatti — $elenco"
    }
    $voci = @($salute.Dati.checks.PSObject.Properties).Count
    Chiudi-Passo 1 "GET /health, $voci voci verdi" "CA-1 (ambiente avviato dal solo README)" $c

    # ---------------------------------------------------------------- passo 2
    # 202 e non 201: la POST accoda e non indicizza (RNF-03). Il 409 NON e' un
    # errore ma la seconda esecuzione dello stesso script: senza questo ramo la
    # dimostrazione sarebbe riproducibile una volta sola, cioe' non
    # riproducibile.
    Scrivi-Titolo 2 "Caricamento del PDF: POST /api/documents/ (atteso 202)"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $caricamento = Invoke-Caricamento -Percorso $PdfDimostrazione
    switch ($caricamento.Codice) {
        202 {
            $idDocumento = $caricamento.Dati.id
            Write-Host "       202 Accepted — documento $idDocumento in stato «$($caricamento.Dati.status)», accodato" -ForegroundColor Green
        }
        409 {
            $idDocumento = $caricamento.Dati.documento_esistente
            Write-Host "       409 Conflict — gia' presente come documento $idDocumento (RF-09): si prosegue con quello" -ForegroundColor Yellow
            Write-Host "       $($caricamento.Dati.detail)" -ForegroundColor DarkGray
        }
        default {
            throw "Caricamento fallito con codice $($caricamento.Codice): $($caricamento.Testo)"
        }
    }
    Chiudi-Passo 2 "POST /api/documents/ → $($caricamento.Codice)" "RNF-03 (la POST accoda e torna subito)" $c

    # ---------------------------------------------------------------- passo 3
    # GET /api/documents/{id}/ e' l'UNICO modo in cui un client scopre com'e'
    # finita: la POST e' gia' tornata. Allo scadere dei tentativi il messaggio
    # nomina il worker perche' e' il sintomo piu' probabile — un documento che
    # resta «in attesa» non e' un file rotto, e' un `manage.py db_worker` che
    # nessuno ha avviato.
    Scrivi-Titolo 3 "Attesa dell'indicizzazione: GET /api/documents/$idDocumento/"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $documento = $null
    for ($tentativo = 1; $tentativo -le $TentativiMax; $tentativo++) {
        $risposta = Invoke-Richiesta -Percorso "/api/documents/$idDocumento/" -TimeoutSec 30
        if ($risposta.Codice -ne 200) {
            throw "GET /api/documents/$idDocumento/ ha risposto $($risposta.Codice): $($risposta.Testo)"
        }
        $documento = $risposta.Dati
        if ($documento.status -in @("indexed", "failed")) { break }
        Write-Host ("       tentativo {0}/{1}: stato «{2}»…" -f $tentativo, $TentativiMax, $documento.status) -ForegroundColor DarkGray
        Start-Sleep -Seconds $IntervalloSecondi
    }
    if ($documento.status -eq "failed") {
        throw "Il documento $idDocumento e' in stato «failed»: $($documento.error_message)"
    }
    if ($documento.status -ne "indexed") {
        throw ("Il documento {0} e' ancora in stato «{1}» dopo {2} tentativi ({3} s): NESSUN WORKER IN ESECUZIONE? " -f
            $idDocumento, $documento.status, $TentativiMax, ($TentativiMax * $IntervalloSecondi)) +
            "La coda vive nel database e nessuno la lavora finche' non gira 'manage.py db_worker' in un secondo processo. " +
            "Lo conferma la voce «coda» di GET /health, che conta i task in attesa."
    }
    Write-Host ("       indicizzato: {0} pagine, {1} segmenti, base «{2}»" -f
        $documento.page_count, $documento.chunk_count, $documento.knowledge_base_name) -ForegroundColor Green
    Chiudi-Passo 3 "polling fino a «indexed»" "CA-2 (documento indicizzato, pagine e segmenti)" $c

    # ---------------------------------------------------------------- passo 4
    Scrivi-Titolo 4 "Domanda pertinente: POST /api/ask/"
    $c = [Diagnostics.Stopwatch]::StartNew()
    Write-Host "       « $DomandaPertinente »" -ForegroundColor White
    $pertinente = Invoke-Domanda -Domanda $DomandaPertinente
    if ($pertinente.Codice -ne 200) {
        throw "POST /api/ask/ ha risposto $($pertinente.Codice): $($pertinente.Testo)"
    }
    $fonti = @($pertinente.Dati.fonti)
    Write-Host "       $($pertinente.Dati.risposta)"
    Write-Host ("       recupero {0} ms · generazione {1} ms · pipeline «{2}»" -f
        $pertinente.Dati.retrieval_ms, $pertinente.Dati.generation_ms, $pertinente.Dati.pipeline) -ForegroundColor DarkGray
    foreach ($fonte in $fonti) {
        Write-Host ("       fonte: {0} p.{1} · punteggio {2}" -f $fonte.documento, $fonte.pagina, $fonte.punteggio) -ForegroundColor DarkGray
    }
    # CA-3 chiede la risposta CON LE FONTI: una risposta senza fonti sarebbe
    # generazione libera, cioe' esattamente cio' che il sistema deve escludere.
    if ($fonti.Count -eq 0) {
        throw "La domanda pertinente non ha prodotto alcuna fonte: CA-3 non e' dimostrato. Il documento risulta indicizzato, quindi il recupero ha restituito zero segmenti — indice della base sbagliato, oppure soglia non superata nella strategia «similarity_score_threshold»."
    }
    Chiudi-Passo 4 "risposta con $($fonti.Count) fonti citate" "CA-3 (risposta corretta con fonti)" $c

    # ---------------------------------------------------------------- passo 5
    Scrivi-Titolo 5 "Domanda fuori tema: POST /api/ask/"
    $c = [Diagnostics.Stopwatch]::StartNew()
    Write-Host "       « $DomandaFuoriTema »" -ForegroundColor White
    $fuoriTema = Invoke-Domanda -Domanda $DomandaFuoriTema
    if ($fuoriTema.Codice -ne 200) {
        throw "POST /api/ask/ ha risposto $($fuoriTema.Codice): $($fuoriTema.Testo)"
    }
    Write-Host "       $($fuoriTema.Dati.risposta)"
    # Due strade portano alla non conoscenza e CA-4 accetta entrambe: nessun
    # segmento recuperato — e allora la dichiarazione e' emessa senza nemmeno
    # interrogare l'LLM (RF-14, `generata` false) — oppure il modello che
    # obbedisce al prompt di sistema. Si distingue quale, perche' la prima e'
    # una garanzia del codice e la seconda dipende dal modello, e con la
    # pipeline predefinita (strategia «similarity») la strada e' la seconda:
    # la soglia filtra soltanto nella strategia «similarity_score_threshold»,
    # cfr. il ramo THRESHOLD di _recupera() in rag/services/query.py.
    $fontiFuoriTema = @($fuoriTema.Dati.fonti)
    $dichiarata = $fuoriTema.Dati.risposta -like "*Non dispongo di questa informazione*"
    if (-not $fuoriTema.Dati.generata) {
        Write-Host "       nessun segmento recuperato: dichiarazione emessa senza interrogare l'LLM (RF-14)" -ForegroundColor Green
    }
    elseif ($dichiarata) {
        $punteggi = ($fontiFuoriTema | ForEach-Object { $_.punteggio }) -join ", "
        Write-Host ("       {0} segmenti passati all'LLM (punteggi {1}), che ha dichiarato di non sapere:" -f
            $fontiFuoriTema.Count, $punteggi) -ForegroundColor Green
        Write-Host "       in questo ramo CA-4 lo regge il prompt di sistema, non la soglia" -ForegroundColor Green
    }
    else {
        throw "La domanda fuori tema ha ricevuto una risposta inventata invece della dichiarazione di non conoscenza: CA-4 non e' dimostrato. Risposta: $($fuoriTema.Dati.risposta)"
    }
    Chiudi-Passo 5 "dichiarazione di non conoscenza" "CA-4 (nessuna risposta inventata)" $c

    # ---------------------------------------------------------------- passo 6
    # RF-23: piu' configurazioni coesistono e sono selezionabili per richiesta.
    # L'elenco comprende anche le pipeline non attive, col loro flag.
    Scrivi-Titolo 6 "Configurazioni disponibili: GET /api/pipelines/"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $pipelines = Invoke-Richiesta -Percorso "/api/pipelines/" -TimeoutSec 30
    if ($pipelines.Codice -ne 200) {
        throw "GET /api/pipelines/ ha risposto $($pipelines.Codice): $($pipelines.Testo)"
    }
    $elencoPipeline = @($pipelines.Dati)
    if ($elencoPipeline.Count -eq 0) {
        throw "Nessuna pipeline configurata: la migrazione 0004 crea quella predefinita (RF-26), quindi il database non e' quello del progetto."
    }
    $elencoPipeline |
        Select-Object @{n = "id"; e = { $_.id } },
                      @{n = "nome"; e = { $_.name } },
                      @{n = "predefinita"; e = { $_.is_default } },
                      @{n = "attiva"; e = { $_.is_active } },
                      @{n = "modello"; e = { $_.model_name } },
                      @{n = "temp"; e = { $_.temperature } },
                      @{n = "strategia"; e = { $_.search_type } },
                      @{n = "top_k"; e = { $_.top_k } },
                      @{n = "soglia"; e = { $_.score_threshold } } |
        Format-Table -AutoSize | Out-String -Width 200 | Write-Host
    Chiudi-Passo 6 "elenco di $($elencoPipeline.Count) pipeline coi loro parametri" "RF-23 (piu' configurazioni coesistenti)" $c

    # ---------------------------------------------------------------- passo 7
    Scrivi-Titolo 7 "Riepilogo"
    $Riepilogo | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
    $totale = [math]::Round(($Riepilogo | Measure-Object -Property Secondi -Sum).Sum, 2)
    Write-Host ("Totale: {0} s. Nessun contenuto documentale ha lasciato la macchina (RNF-01): " -f $totale) -ForegroundColor Green
    Write-Host "generazione ed embedding sono entrambi su Ollama in locale." -ForegroundColor Green
    Write-Host ""
    exit 0
}
catch {
    Write-Host ""
    Write-Host "DIMOSTRAZIONE FALLITA: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
