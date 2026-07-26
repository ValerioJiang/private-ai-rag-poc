<#
.SYNOPSIS
    Esegue il ciclo completo del sistema RAG a rete staccata e ne lascia un
    verbale su disco (T-43, RNF-01, CA-9).

.DESCRIPTION
    RNF-01 dice che nulla esce dalla macchina. Finche' resta un'affermazione
    sull'architettura — nessun `langchain-openai`, nessun `sentence-transformers`,
    LANGSMITH_TRACING forzato a false — e' un argomento, non una verifica. Questa
    prova la trasforma in verifica: si staccano le interfacce di rete e il
    sistema deve continuare a funzionare identico, perche' database, Ollama e
    applicazione stanno tutti su localhost.

    PERCHE' UNO SCRIPT E NON UNA SESSIONE INTERATTIVA. A rete staccata la
    macchina non raggiunge alcun servizio remoto — compreso quello che
    guiderebbe la prova da fuori. L'unico modo onesto di eseguirla e' che la
    macchina se la conduca da sola e ne lasci traccia: l'intero output finisce
    in un file di verbale, che si legge a rete riattaccata. E' anche la ragione
    per cui lo script AVVIA E FERMA DA SE' server e worker, invece di
    presupporli gia' in esecuzione.

    NOVE PASSI, nell'ordine:
      1. fotografia delle interfacce di rete;
      2. prova che l'esterno e' IRRAGGIUNGIBILE — e' l'evidenza su cui poggia
         tutto il resto: se questi tentativi riuscissero, la prova non
         dimostrerebbe nulla e lo script si ferma;
      3. prova che localhost e' RAGGIUNGIBILE (database e Ollama);
      4. avvio di server e worker, con l'output dirottato su file;
      5. generazione di un PDF MAI INDICIZZATO PRIMA;
      6. caricamento (atteso 202) e attesa dell'indicizzazione;
      7. domanda pertinente sul contenuto di quel PDF;
      8. domanda fuori tema;
      9. arresto dei processi, lettura dei loro log in cerca di errori di
         risoluzione DNS o di connessione, e riepilogo dei tempi.

    I TEMPI SONO IL SECONDO ARGOMENTO. Non devono differire da quelli misurati a
    rete attiva in T-42 (caricamento 0,95 s · indicizzazione 7,50 s · domanda
    13,53 s): se il sistema chiamasse un servizio remoto, staccare la rete lo
    farebbe attendere un timeout, e il confronto lo mostrerebbe. Lo script
    stampa i due valori affiancati.

    Nessuna credenziale e' scritta qui dentro: utente e password arrivano da
    parametro, come in dimostrazione.ps1.

.EXAMPLE
    # A rete gia' staccata, dalla radice del progetto:
    .\scripts\prova-rete-staccata.ps1 -Utente dimostrazione -Password ********

.EXAMPLE
    # Per provare lo script PRIMA di staccare la rete: il passo 2 fallirebbe,
    # ed e' giusto che fallisca. -IgnoraReteAttiva lo declassa ad avvertimento,
    # e il verbale riporta a chiare lettere che la prova NON e' valida.
    .\scripts\prova-rete-staccata.ps1 -Utente dimostrazione -Password ******** -IgnoraReteAttiva
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Utente,
    [Parameter(Mandatory = $true)][string]$Password,

    [string]$BaseUrl = "http://localhost:8000",

    # Prova di collaudo dello script a rete ancora attiva. Non usarlo per la
    # prova vera: il verbale la marca come NON VALIDA.
    [switch]$IgnoraReteAttiva,

    [int]$TentativiMax = 60,
    [int]$IntervalloSecondi = 2
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Radice = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Radice ".venv\Scripts\python.exe"

$Marca = Get-Date -Format "yyyyMMdd-HHmmss"
$CartellaEsiti = Join-Path $Radice "esiti-t43"
if (-not (Test-Path $CartellaEsiti)) { [void](New-Item -ItemType Directory -Path $CartellaEsiti) }

$Verbale       = Join-Path $CartellaEsiti "verbale-$Marca.txt"
$LogServerOut  = Join-Path $CartellaEsiti "server-$Marca.out.log"
$LogServerErr  = Join-Path $CartellaEsiti "server-$Marca.err.log"
$LogWorkerOut  = Join-Path $CartellaEsiti "worker-$Marca.out.log"
$LogWorkerErr  = Join-Path $CartellaEsiti "worker-$Marca.err.log"

# I tempi misurati in T-42 a rete ATTIVA, sulla stessa macchina. Sono il metro
# di paragone del passo 9: la prova di RNF-01 non e' «ha funzionato», e' «ha
# funzionato nello stesso tempo».
$RiferimentoT42 = @{
    Caricamento     = 0.95
    Indicizzazione  = 7.50
    DomandaPertinente = 13.53
}

$Riepilogo = New-Object System.Collections.ArrayList
$ProcessoServer = $null
$ProcessoWorker = $null

# Diventa $false se al passo 2 l'esterno risulta raggiungibile. Il verdetto
# finale lo legge: un'esecuzione a rete attiva puo' riuscire in tutto e non
# dimostrare NULLA di RNF-01, e il verbale deve dirlo invece di lasciar leggere
# «verificato» a chi lo apra fra un mese.
$ProvaValida = $true

$coppia = "{0}:{1}" -f $Utente, $Password
$Intestazioni = @{
    Authorization = "Basic " + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($coppia))
    Accept        = "application/json"
}


function Scrivi-Titolo {
    param([int]$Numero, [string]$Testo)
    Write-Host ""
    Write-Host ("[{0}/9] {1}" -f $Numero, $Testo) -ForegroundColor Cyan
}


function Chiudi-Passo {
    param([int]$Numero, [string]$Descrizione, [Diagnostics.Stopwatch]$Cronometro)
    $secondi = [math]::Round($Cronometro.Elapsed.TotalSeconds, 2)
    Write-Host ("       concluso in {0} s" -f $secondi) -ForegroundColor DarkGray
    [void]$Riepilogo.Add([pscustomobject]@{
            Passo = $Numero; Operazione = $Descrizione; Secondi = $secondi
        })
    return $secondi
}


function Invoke-Richiesta {
    <# Identica nella forma a quella di dimostrazione.ps1, e per la stessa
       ragione: non solleva sui codici di errore HTTP, perche' 409 e 503 sono
       esiti previsti di cui va letto il corpo. Vedi il commento esteso li'
       sul perche' $_.ErrorDetails.Message venga PRIMA dello stream. #>
    param(
        [string]$Metodo = "GET",
        [Parameter(Mandatory = $true)][string]$Percorso,
        $Corpo = $null,
        [string]$TipoContenuto,
        [int]$TimeoutSec = 60
    )
    $parametri = @{
        Uri = "$BaseUrl$Percorso"; Method = $Metodo; Headers = $Intestazioni
        TimeoutSec = $TimeoutSec; UseBasicParsing = $true
    }
    if ($null -ne $Corpo) { $parametri.Body = $Corpo }
    if ($TipoContenuto) { $parametri.ContentType = $TipoContenuto }

    try {
        $risposta = Invoke-WebRequest @parametri
        $codice = [int]$risposta.StatusCode
        # NON $risposta.Content. DRF risponde «application/json» senza charset, e
        # in assenza di charset Invoke-WebRequest di PowerShell 5.1 decodifica in
        # ISO-8859-1: «indennita'» con l'accento diventa «indennitÃ ». Misurato
        # nel collaudo di questo script il 26/07/2026. I byte grezzi sono UTF-8 e
        # vanno letti come tali.
        $flusso = $risposta.RawContentStream
        $flusso.Position = 0
        $lettore = New-Object System.IO.StreamReader($flusso, [Text.Encoding]::UTF8)
        try { $testo = $lettore.ReadToEnd() } finally { $lettore.Close() }
    }
    catch {
        $rispostaErrore = $_.Exception.Response
        if ($null -eq $rispostaErrore) { throw }
        $codice = [int]$rispostaErrore.StatusCode
        $flusso = $rispostaErrore.GetResponseStream()
        $lettore = New-Object System.IO.StreamReader($flusso, [Text.Encoding]::UTF8)
        try { $testo = $lettore.ReadToEnd() } finally { $lettore.Close() }
        # Lo stream della risposta di errore puo' essere gia' stato consumato da
        # Invoke-WebRequest (osservato in T-41): in quel caso torna vuoto e
        # l'unica copia del corpo e' in ErrorDetails, che pero' e' gia' decodificato.
        if ([string]::IsNullOrEmpty($testo)) { $testo = $_.ErrorDetails.Message }
    }
    $dati = $null
    if ($testo) { try { $dati = $testo | ConvertFrom-Json } catch { $dati = $null } }
    [pscustomobject]@{ Codice = $codice; Dati = $dati; Testo = $testo }
}


function Invoke-Caricamento {
    <# multipart costruito a mano: PowerShell 5.1 non ha -Form. Il PDF viaggia
       come stringa iso-8859-1, l'unica codifica che mappa i 256 valori di un
       byte senza perdite. #>
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
    param([Parameter(Mandatory = $true)][string]$Domanda, [int]$TimeoutSec = 300)
    $corpo = @{ domanda = $Domanda } | ConvertTo-Json -Compress
    Invoke-Richiesta -Metodo "POST" -Percorso "/api/ask/" `
        -Corpo ([Text.Encoding]::UTF8.GetBytes($corpo)) `
        -TipoContenuto "application/json; charset=utf-8" -TimeoutSec $TimeoutSec
}


function Test-PortaRaggiungibile {
    <# Un TcpClient con timeout esplicito invece di Test-NetConnection: a rete
       staccata quest'ultimo impiega decine di secondi per arrendersi, e questo
       script ne fa cinque di prove. Restituisce l'esito E il motivo, perche' il
       motivo — «host sconosciuto» contro «connessione rifiutata» — e' il dato
       che distingue una rete staccata da un servizio spento. #>
    param([string]$Host_, [int]$Porta, [int]$TimeoutMs = 3000)

    $cliente = New-Object System.Net.Sockets.TcpClient
    try {
        $operazione = $cliente.BeginConnect($Host_, $Porta, $null, $null)
        $riuscito = $operazione.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if (-not $riuscito) {
            return [pscustomobject]@{ Ok = $false; Motivo = "timeout dopo $TimeoutMs ms" }
        }
        $cliente.EndConnect($operazione)
        return [pscustomobject]@{ Ok = $true; Motivo = "connesso" }
    }
    catch {
        return [pscustomobject]@{ Ok = $false; Motivo = $_.Exception.InnerException.Message }
    }
    finally { $cliente.Close() }
}


function Cerca-ErroriDiRete {
    <# Un tentativo di uscita FALLITO non e' silenzioso: lascia un errore di
       risoluzione DNS o di connessione nel log di chi l'ha tentato. E' ciò che
       questa prova cerca, e trovarne uno sarebbe il risultato piu' importante
       dell'intera fase — direbbe che un percorso del codice prova a uscire. #>
    param([string]$Percorso, [string]$Etichetta)

    if (-not (Test-Path $Percorso)) {
        Write-Host ("       {0}: nessun file di log" -f $Etichetta) -ForegroundColor Yellow
        return @()
    }
    $sospetti = @(
        "getaddrinfo", "Name or service not known", "Temporary failure in name resolution",
        "11001", "11002", "10051", "10065",
        "NameResolutionError", "ConnectError", "ConnectTimeout", "ReadTimeout",
        "Max retries exceeded", "SSLError", "certificate", "urllib3",
        "langsmith", "api\.smith", "openai\.com", "huggingface", "langfuse"
    )
    $modello = ($sospetti -join "|")
    $trovati = @(Select-String -Path $Percorso -Pattern $modello -AllMatches -ErrorAction SilentlyContinue)
    if ($trovati.Count -eq 0) {
        Write-Host ("       {0}: nessun errore di rete" -f $Etichetta) -ForegroundColor Green
    }
    else {
        Write-Host ("       {0}: {1} RIGHE SOSPETTE" -f $Etichetta, $trovati.Count) -ForegroundColor Red
        foreach ($riga in $trovati) {
            Write-Host ("         riga {0}: {1}" -f $riga.LineNumber, $riga.Line.Trim()) -ForegroundColor Red
        }
    }
    return $trovati
}


Start-Transcript -Path $Verbale -Force | Out-Null

try {
    Write-Host ""
    Write-Host "T-43 — prova a rete staccata (RNF-01, CA-9)" -ForegroundColor White
    Write-Host ("Avviata il {0}" -f (Get-Date -Format "dd/MM/yyyy HH:mm:ss")) -ForegroundColor White
    Write-Host ("Verbale: {0}" -f $Verbale) -ForegroundColor DarkGray
    if ($IgnoraReteAttiva) {
        Write-Host ""
        Write-Host "ATTENZIONE — eseguito con -IgnoraReteAttiva: se la rete risultasse" -ForegroundColor Yellow
        Write-Host "attiva questa esecuzione NON e' una prova valida di RNF-01." -ForegroundColor Yellow
    }

    # ------------------------------------------------------------------ passo 1
    Scrivi-Titolo 1 "Fotografia delle interfacce di rete"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $schede = @(Get-NetAdapter -ErrorAction SilentlyContinue |
        Select-Object Name, InterfaceDescription, Status, LinkSpeed)
    if ($schede.Count -eq 0) {
        Write-Host "       Get-NetAdapter non ha restituito nulla" -ForegroundColor Yellow
    }
    else {
        $schede | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
    }
    $attive = @($schede | Where-Object { $_.Status -eq "Up" })
    Write-Host ("       schede in stato «Up»: {0}" -f $attive.Count) -ForegroundColor DarkGray
    # Disattivare Wi-Fi ed Ethernet non basta se resta su un TUNNEL: una VPN
    # continua a portare traffico fuori dalla macchina, ed e' proprio cio' che
    # questa prova deve escludere. Il passo 2 se ne accorgerebbe comunque —
    # prova la raggiungibilita' vera, non lo stato delle schede — ma dirlo qui
    # risparmia un giro a chi legge l'errore senza sapere da dove viene.
    $tunnel = @($attive | Where-Object {
            $_.InterfaceDescription -match "Tailscale|VPN|WireGuard|OpenVPN|TAP|Tunnel|ZeroTier"
        })
    if ($tunnel.Count -gt 0) {
        Write-Host ""
        foreach ($t in $tunnel) {
            Write-Host ("       ATTENZIONE — tunnel ancora attivo: {0} ({1})" -f $t.Name, $t.InterfaceDescription) -ForegroundColor Yellow
        }
        Write-Host "       Una VPN attiva porta traffico fuori: va disattivata anch'essa." -ForegroundColor Yellow
    }
    [void](Chiudi-Passo 1 "fotografia delle interfacce" $c)

    # ------------------------------------------------------------------ passo 2
    # E' l'evidenza su cui poggia tutto il resto. Se questi tentativi
    # riuscissero, i passi seguenti non dimostrerebbero nulla: si fermerebbe qui.
    Scrivi-Titolo 2 "L'esterno deve essere IRRAGGIUNGIBILE"
    $c = [Diagnostics.Stopwatch]::StartNew()
    # I bersagli NON sono host qualunque: sono i servizi che RNF-01 nomina, cioe'
    # quelli verso cui il testo dei documenti potrebbe uscire se una dipendenza
    # o una variabile d'ambiente rientrasse dalla finestra. LangSmith perche'
    # settings/base.py forza LANGSMITH_TRACING=false proprio per impedirgli di
    # accendersi da solo; OpenAI e HuggingFace perche' sono i due provider
    # presenti negli enum come alternative documentate e non attivabili. pypi.org
    # e 1.1.1.1 completano: il primo e' l'uscita piu' banale, il secondo si prova
    # per indirizzo e non per nome, cosi' un DNS morto non maschera una rotta
    # ancora viva.
    $bersagli = @(
        @{ Nome = "api.smith.langchain.com"; Porta = 443 },
        @{ Nome = "api.openai.com";          Porta = 443 },
        @{ Nome = "huggingface.co";          Porta = 443 },
        @{ Nome = "pypi.org";                Porta = 443 },
        @{ Nome = "1.1.1.1";                 Porta = 443 }
    )
    $raggiungibili = New-Object System.Collections.ArrayList
    foreach ($b in $bersagli) {
        $esito = Test-PortaRaggiungibile -Host_ $b.Nome -Porta $b.Porta
        if ($esito.Ok) {
            Write-Host ("       {0,-26} RAGGIUNGIBILE — {1}" -f $b.Nome, $esito.Motivo) -ForegroundColor Red
            [void]$raggiungibili.Add($b.Nome)
        }
        else {
            Write-Host ("       {0,-26} irraggiungibile — {1}" -f $b.Nome, $esito.Motivo) -ForegroundColor Green
        }
    }
    # La risoluzione DNS a parte: e' il primo anello che si spezza staccando la
    # rete, ed e' l'errore che comparirebbe nei log se qualcosa provasse a uscire.
    try {
        $dns = Resolve-DnsName -Name "api.smith.langchain.com" -DnsOnly -QuickTimeout -ErrorAction Stop
        Write-Host ("       DNS api.smith.langchain.com   RISOLTO — {0}" -f (($dns | Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress)) -ForegroundColor Red
        [void]$raggiungibili.Add("DNS")
    }
    catch {
        Write-Host ("       DNS api.smith.langchain.com   non risolto — {0}" -f $_.Exception.Message.Trim()) -ForegroundColor Green
    }

    if ($raggiungibili.Count -gt 0) {
        $ProvaValida = $false
        $elenco = $raggiungibili -join ", "
        if ($IgnoraReteAttiva) {
            Write-Host ""
            Write-Host "PROVA NON VALIDA: la rete e' ATTIVA ($elenco). Si prosegue solo" -ForegroundColor Yellow
            Write-Host "perche' e' stato chiesto -IgnoraReteAttiva: questo e' un collaudo" -ForegroundColor Yellow
            Write-Host "dello script, NON la prova di RNF-01." -ForegroundColor Yellow
        }
        else {
            throw ("La rete risulta ANCORA ATTIVA ({0}): la prova non dimostrerebbe nulla. " -f $elenco) +
                  "Disattiva tutte le interfacce e riesegui. Per collaudare lo script a rete attiva, usa -IgnoraReteAttiva."
        }
    }
    [void](Chiudi-Passo 2 "l'esterno e' irraggiungibile" $c)

    # ------------------------------------------------------------------ passo 3
    # L'altra meta' dell'argomento: localhost continua a funzionare, ed e'
    # esattamente il punto — database, Ollama e applicazione stanno tutti qui.
    Scrivi-Titolo 3 "localhost deve essere RAGGIUNGIBILE"
    $c = [Diagnostics.Stopwatch]::StartNew()
    foreach ($servizio in @(
            @{ Nome = "PostgreSQL (Docker)"; Host_ = "127.0.0.1"; Porta = 5434 },
            @{ Nome = "Ollama";              Host_ = "127.0.0.1"; Porta = 11434 })) {
        $esito = Test-PortaRaggiungibile -Host_ $servizio.Host_ -Porta $servizio.Porta
        $colore = if ($esito.Ok) { "Green" } else { "Red" }
        Write-Host ("       {0,-22} {1,-16} {2}" -f $servizio.Nome,
            $(if ($esito.Ok) { "raggiungibile" } else { "IRRAGGIUNGIBILE" }), $esito.Motivo) -ForegroundColor $colore
        if (-not $esito.Ok) {
            throw "$($servizio.Nome) non risponde sulla porta $($servizio.Porta). Staccare la rete non deve fermarlo: se l'ha fermato, il servizio non era su localhost."
        }
    }
    [void](Chiudi-Passo 3 "database e Ollama rispondono su localhost" $c)

    # ------------------------------------------------------------------ passo 4
    # --noreload: senza, il launcher del virtualenv su Windows raddoppia i
    # processi e Stop-Process ne lascerebbe uno orfano ad occupare la 8000.
    Scrivi-Titolo 4 "Avvio di server e worker"
    $c = [Diagnostics.Stopwatch]::StartNew()
    if (-not (Test-Path $Python)) { throw "Virtualenv assente: $Python" }

    # PRIMA di avviare i propri: nessun altro worker deve essere in giro.
    # Un worker gia' vivo prende i task di questa prova al posto del nostro, e
    # il suo log finisce in un ALTRO file: lo scan del passo 9 esaminerebbe un
    # file che contiene le sole righe di avvio e direbbe «nessun errore di
    # rete» senza aver guardato dove il lavoro e' avvenuto. E' successo nella
    # prova del 26/07/2026 alle 12:11, dove a indicizzare e' stato un orfano
    # delle 11:55 — l'esito reggeva, ma l'evidenza stava nel file sbagliato.
    $altriWorker = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match "db_worker|runserver" })
    if ($altriWorker.Count -gt 0) {
        $elenco = ($altriWorker | ForEach-Object { "pid $($_.ProcessId)" }) -join ", "
        throw ("Ci sono gia' {0} processi db_worker/runserver in esecuzione ({1}). " -f $altriWorker.Count, $elenco) +
              "Prenderebbero i task di questa prova al posto dei processi avviati qui, e il verbale " +
              "risulterebbe privo del log di chi ha fatto il lavoro. Fermali e riesegui: " +
              "Get-Process python | Stop-Process -Force"
    }

    $ProcessoServer = Start-Process -FilePath $Python -PassThru -NoNewWindow `
        -WorkingDirectory $Radice `
        -ArgumentList "manage.py", "runserver", "--noreload" `
        -RedirectStandardOutput $LogServerOut -RedirectStandardError $LogServerErr
    Write-Host ("       server avviato, pid {0}" -f $ProcessoServer.Id) -ForegroundColor DarkGray

    # --no-reload NON e' un dettaglio di comodita'. Senza, db_worker avvia
    # l'autoreloader, che esegue il lavoro in un processo FIGLIO: Stop-Process
    # uccide il padre e lascia vivo il figlio, che continua a consumare la coda.
    # Dieci orfani accumulati in un'ora di collaudi, il 26/07/2026, prima che il
    # controllo qui sopra li rendesse visibili. Vale anche per --noreload del
    # server, per la stessa ragione.
    $ProcessoWorker = Start-Process -FilePath $Python -PassThru -NoNewWindow `
        -WorkingDirectory $Radice `
        -ArgumentList "manage.py", "db_worker", "--no-reload" `
        -RedirectStandardOutput $LogWorkerOut -RedirectStandardError $LogWorkerErr
    Write-Host ("       worker avviato, pid {0}" -f $ProcessoWorker.Id) -ForegroundColor DarkGray

    $salute = $null
    for ($tentativo = 1; $tentativo -le 30; $tentativo++) {
        Start-Sleep -Seconds 1
        try { $salute = Invoke-Richiesta -Percorso "/health" -TimeoutSec 10; break }
        catch { if ($tentativo -eq 30) { throw "Il server non ha risposto entro 30 s: vedi $LogServerErr" } }
    }
    if ($null -eq $salute.Dati) { throw "GET /health non ha risposto JSON (codice $($salute.Codice))" }
    foreach ($voce in $salute.Dati.checks.PSObject.Properties) {
        $stato = if ($voce.Value.ok) { "ok" } else { "GUASTO" }
        $colore = if ($voce.Value.ok) { "Green" } else { "Red" }
        Write-Host ("       {0,-10} {1,-7} {2}" -f $voce.Name, $stato, $voce.Value.detail) -ForegroundColor $colore
    }
    $guaste = @($salute.Dati.checks.PSObject.Properties | Where-Object { -not $_.Value.ok })
    if ($guaste.Count -gt 0) {
        throw ("Presupposti non soddisfatti a rete staccata — " +
            (($guaste | ForEach-Object { "«$($_.Name)»: $($_.Value.detail)" }) -join " · "))
    }
    [void](Chiudi-Passo 4 "server e worker avviati, /health tutto verde" $c)

    # ------------------------------------------------------------------ passo 5
    # Il piano chiede un PDF MAI INDICIZZATO PRIMA: un 409 proverebbe soltanto
    # la deduplica. Si genera con PyMuPDF — la stessa libreria che il sistema usa
    # per leggerlo — e porta in fondo la marca temporale dell'esecuzione, cosi'
    # il checksum e' nuovo a ogni giro e la prova resta ripetibile.
    Scrivi-Titolo 5 "Generazione di un PDF mai indicizzato prima"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $PdfProva = Join-Path $CartellaEsiti "regolamento-trasferte-$Marca.pdf"
    $PdfRiscaldamento = Join-Path $CartellaEsiti "riscaldamento-$Marca.pdf"
    $generatore = Join-Path $env:TEMP "genera-pdf-t43-$Marca.py"
    # Due testi, e la differenza NON e' cosmetica. Il PDF di riscaldamento parla
    # di tutt'altro — la mensa — perche' altrimenti finirebbe fra le fonti della
    # domanda misurata al passo 7, con un punteggio quasi identico a quello del
    # documento vero: osservato nel collaudo del 26/07/2026, dove il primo posto
    # era del PDF di riscaldamento. Le fonti citate devono essere quelle che
    # rispondono, non quelle che il collaudo si e' lasciato dietro.
    $codice = @"
import sys
import pymupdf

percorso, marca, tipo = sys.argv[1], sys.argv[2], sys.argv[3]

trasferte = [
    "Regolamento trasferte e rimborsi",
    "",
    "Articolo 1 - Indennita' giornaliera.",
    "L'indennita' giornaliera di trasferta in Italia e' di 45 euro.",
    "Per le trasferte all'estero l'indennita' giornaliera e' di 80 euro.",
    "",
    "Articolo 2 - Rimborso chilometrico.",
    "Il rimborso chilometrico e' fissato in 0,42 euro al chilometro.",
    "",
    "Articolo 3 - Anticipo.",
    "Su richiesta e' concesso un anticipo pari al 70 per cento della spesa prevista.",
]
mensa = [
    "Regolamento del servizio mensa",
    "",
    "Articolo 1 - Orario.",
    "La mensa aziendale e' aperta dalle 12:15 alle 14:30 nei giorni feriali.",
    "",
    "Articolo 2 - Prenotazione.",
    "La prenotazione del pasto va effettuata entro le ore 10:00 del giorno stesso.",
    "",
    "Documento di solo riscaldamento dei modelli: nessuna domanda lo riguarda.",
]

righe = list(trasferte if tipo == "trasferte" else mensa)
righe += ["", "Generato per la prova a rete staccata T-43, esecuzione " + marca + "."]

documento = pymupdf.open()
pagina = documento.new_page()
y = 90
for riga in righe:
    pagina.insert_text((72, y), riga, fontsize=11)
    y += 18
documento.save(percorso)
documento.close()
print(percorso)
"@
    Set-Content -Path $generatore -Value $codice -Encoding UTF8
    & $Python $generatore $PdfProva $Marca "trasferte" | Out-Null
    & $Python $generatore $PdfRiscaldamento $Marca "mensa" | Out-Null
    Remove-Item $generatore -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path $PdfProva)) { throw "Generazione del PDF fallita: $PdfProva" }
    Write-Host ("       {0} — {1} byte" -f (Split-Path $PdfProva -Leaf), (Get-Item $PdfProva).Length) -ForegroundColor DarkGray
    [void](Chiudi-Passo 5 "PDF di prova generato" $c)

    # ------------------------------------------------------- riscaldamento
    # NON e' cortesia verso i numeri: senza, il confronto del passo 9 non regge.
    # Nel collaudo del 26/07/2026 la prima indicizzazione e' costata 25,24 s
    # contro i 7,50 s misurati in T-42 — tutta differenza di caricamento di
    # bge-m3 in memoria, ma un tempo triplo e' ESATTAMENTE cio' che produrrebbe
    # un timeout verso un servizio remoto irraggiungibile. Un confronto che
    # confonde le due cause non prova nulla. Qui si caricano entrambi i modelli
    # con un giro completo buttato via, e si misura il giro dopo: caldo contro
    # caldo, come i numeri di T-42.
    Scrivi-Titolo 5 "Riscaldamento dei modelli (giro non misurato)"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $riscaldamento = Invoke-Caricamento -Percorso $PdfRiscaldamento
    if ($riscaldamento.Codice -ne 202) {
        throw "Riscaldamento: atteso 202, ricevuto $($riscaldamento.Codice). Corpo: $($riscaldamento.Testo)"
    }
    $idRiscaldamento = $riscaldamento.Dati.id
    for ($tentativo = 1; $tentativo -le $TentativiMax; $tentativo++) {
        $r = Invoke-Richiesta -Percorso "/api/documents/$idRiscaldamento/" -TimeoutSec 30
        if ($r.Dati.status -in @("indexed", "failed")) { break }
        Start-Sleep -Seconds $IntervalloSecondi
    }
    Write-Host ("       documento {0}: «{1}» — bge-m3 caricato" -f $idRiscaldamento, $r.Dati.status) -ForegroundColor DarkGray
    $scarto = Invoke-Domanda -Domanda "A che ora apre la mensa aziendale?"
    Write-Host ("       domanda di scarto: {0} — qwen2.5 caricato" -f $scarto.Codice) -ForegroundColor DarkGray
    [void](Chiudi-Passo 5 "riscaldamento (tempo NON confrontabile, per progetto)" $c)

    # ------------------------------------------------------------------ passo 6
    Scrivi-Titolo 6 "Caricamento e indicizzazione"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $caricamento = Invoke-Caricamento -Percorso $PdfProva
    if ($caricamento.Codice -ne 202) {
        throw "Caricamento: atteso 202, ricevuto $($caricamento.Codice). Il PDF doveva essere nuovo. Corpo: $($caricamento.Testo)"
    }
    $idDocumento = $caricamento.Dati.id
    Write-Host ("       202 Accepted — documento {0}, accodato" -f $idDocumento) -ForegroundColor Green
    $secondiCaricamento = Chiudi-Passo 6 "POST /api/documents/ → 202" $c

    $c = [Diagnostics.Stopwatch]::StartNew()
    $documento = $null
    for ($tentativo = 1; $tentativo -le $TentativiMax; $tentativo++) {
        $risposta = Invoke-Richiesta -Percorso "/api/documents/$idDocumento/" -TimeoutSec 30
        if ($risposta.Codice -ne 200) { throw "GET /api/documents/$idDocumento/ → $($risposta.Codice)" }
        $documento = $risposta.Dati
        if ($documento.status -in @("indexed", "failed")) { break }
        Start-Sleep -Seconds $IntervalloSecondi
    }
    if ($documento.status -ne "indexed") {
        throw "Il documento $idDocumento e' in stato «$($documento.status)»: $($documento.error_message)"
    }
    Write-Host ("       indicizzato: {0} pagine, {1} segmenti" -f
        $documento.page_count, $documento.chunk_count) -ForegroundColor Green
    $secondiIndicizzazione = Chiudi-Passo 6 "attesa dell'indicizzazione (embedding LOCALI)" $c

    # ------------------------------------------------------------------ passo 7
    Scrivi-Titolo 7 "Domanda pertinente"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $domandaPertinente = "Qual e' l'indennita' giornaliera di trasferta in Italia?"
    Write-Host "       « $domandaPertinente »" -ForegroundColor White
    $pertinente = Invoke-Domanda -Domanda $domandaPertinente
    if ($pertinente.Codice -ne 200) { throw "POST /api/ask/ → $($pertinente.Codice): $($pertinente.Testo)" }
    Write-Host "       $($pertinente.Dati.risposta)"
    Write-Host ("       recupero {0} ms · generazione {1} ms · pipeline «{2}»" -f
        $pertinente.Dati.retrieval_ms, $pertinente.Dati.generation_ms, $pertinente.Dati.pipeline) -ForegroundColor DarkGray
    $fonti = @($pertinente.Dati.fonti)
    foreach ($fonte in $fonti) {
        Write-Host ("       fonte: {0} p.{1} · punteggio {2}" -f $fonte.documento, $fonte.pagina, $fonte.punteggio) -ForegroundColor DarkGray
    }
    if ($fonti.Count -eq 0) { throw "Nessuna fonte citata: CA-3 non e' dimostrato a rete staccata." }
    $secondiDomanda = Chiudi-Passo 7 "risposta con $($fonti.Count) fonti" $c

    # ------------------------------------------------------------------ passo 8
    Scrivi-Titolo 8 "Domanda fuori tema"
    $c = [Diagnostics.Stopwatch]::StartNew()
    $domandaFuoriTema = "Qual e' la capitale dell'Australia?"
    Write-Host "       « $domandaFuoriTema »" -ForegroundColor White
    $fuoriTema = Invoke-Domanda -Domanda $domandaFuoriTema
    if ($fuoriTema.Codice -ne 200) { throw "POST /api/ask/ → $($fuoriTema.Codice): $($fuoriTema.Testo)" }
    Write-Host "       $($fuoriTema.Dati.risposta)"
    $dichiarata = $fuoriTema.Dati.risposta -like "*Non dispongo di questa informazione*"
    if (-not $fuoriTema.Dati.generata) {
        Write-Host "       nessun segmento recuperato: dichiarazione senza interrogare l'LLM (RF-14)" -ForegroundColor Green
    }
    elseif ($dichiarata) {
        Write-Host "       segmenti passati all'LLM, che ha dichiarato di non sapere (lo regge il prompt)" -ForegroundColor Green
    }
    else {
        Write-Host "       RISPOSTA INVENTATA: CA-4 non e' dimostrato in questa esecuzione" -ForegroundColor Red
    }
    [void](Chiudi-Passo 8 "domanda fuori tema" $c)

    # ------------------------------------------------------------------ passo 9
    Scrivi-Titolo 9 "Arresto, log e confronto dei tempi"
    Write-Host "       arresto di server e worker…" -ForegroundColor DarkGray
    foreach ($p in @($ProcessoServer, $ProcessoWorker)) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    $ProcessoServer = $null; $ProcessoWorker = $null
    Start-Sleep -Seconds 2

    # Il log del worker deve contenere il lavoro di QUESTA prova. Se non lo
    # contiene, l'assenza di errori di rete al suo interno non significa nulla:
    # e' l'assenza di qualunque cosa. Senza questo controllo il verbale
    # dichiarerebbe «nessun errore» avendo letto un file di sole tre righe.
    Write-Host ""
    $lavoroSvolto = @(Select-String -Path $LogWorkerErr -Pattern "Ingestione completata" -ErrorAction SilentlyContinue)
    if ($lavoroSvolto.Count -eq 0) {
        throw "Il log del worker di questa esecuzione non contiene alcuna ingestione completata: " +
              "a indicizzare e' stato un ALTRO processo, e il suo log non e' fra gli artefatti di questa prova. " +
              "Il verbale sarebbe privo dell'evidenza che serve. Ferma ogni processo python e riesegui."
    }
    Write-Host ("       il worker di questa prova ha svolto {0} ingestioni: l'evidenza e' nei suoi log" -f $lavoroSvolto.Count) -ForegroundColor Green

    Write-Host ""
    Write-Host "       Ricerca di errori di rete nei log:" -ForegroundColor White
    $sospetti = @()
    $sospetti += Cerca-ErroriDiRete -Percorso $LogServerErr -Etichetta "server (stderr)"
    $sospetti += Cerca-ErroriDiRete -Percorso $LogServerOut -Etichetta "server (stdout)"
    $sospetti += Cerca-ErroriDiRete -Percorso $LogWorkerErr -Etichetta "worker (stderr)"
    $sospetti += Cerca-ErroriDiRete -Percorso $LogWorkerOut -Etichetta "worker (stdout)"

    Write-Host ""
    Write-Host "       Confronto con i tempi misurati a rete ATTIVA in T-42:" -ForegroundColor White
    $confronto = @(
        [pscustomobject]@{ Passo = "caricamento (202)";  "T-42 (rete attiva)" = $RiferimentoT42.Caricamento;       "T-43 (rete staccata)" = $secondiCaricamento }
        [pscustomobject]@{ Passo = "indicizzazione";     "T-42 (rete attiva)" = $RiferimentoT42.Indicizzazione;    "T-43 (rete staccata)" = $secondiIndicizzazione }
        [pscustomobject]@{ Passo = "domanda pertinente"; "T-42 (rete attiva)" = $RiferimentoT42.DomandaPertinente; "T-43 (rete staccata)" = $secondiDomanda }
    )
    $confronto | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
    Write-Host "       Se il sistema chiamasse un servizio remoto, staccare la rete lo" -ForegroundColor DarkGray
    Write-Host "       farebbe attendere un timeout: e' il confronto, non il solo" -ForegroundColor DarkGray
    Write-Host "       successo, a rendere l'argomento stringente." -ForegroundColor DarkGray

    Write-Host ""
    $Riepilogo | Format-Table -AutoSize | Out-String -Width 200 | Write-Host

    Write-Host ""
    if (-not $ProvaValida) {
        # Il caso piu' pericoloso di tutti: un'esecuzione riuscita in ogni passo
        # e priva di valore probatorio. Senza questo ramo il verbale direbbe
        # «VERIFICATI» a chi lo aprisse fra un mese senza ricordare con quali
        # parametri era stato prodotto.
        Write-Host "ESITO: NESSUNA PROVA DI RNF-01." -ForegroundColor Yellow
        Write-Host "Il ciclo e' riuscito, ma al passo 2 la rete risultava ATTIVA: questa" -ForegroundColor Yellow
        Write-Host "esecuzione e' un collaudo dello script, non la verifica di CA-9." -ForegroundColor Yellow
        Write-Host "Per la prova vera: disattivare tutte le interfacce, tunnel VPN" -ForegroundColor Yellow
        Write-Host "compresi, e rieseguire SENZA -IgnoraReteAttiva." -ForegroundColor Yellow
        $codiceUscita = 3
    }
    elseif ($sospetti.Count -eq 0) {
        Write-Host "ESITO: il ciclo completo e' riuscito a rete staccata, e nessun log" -ForegroundColor Green
        Write-Host "contiene errori di risoluzione DNS o di connessione verso l'esterno." -ForegroundColor Green
        Write-Host "RNF-01 e CA-9: VERIFICATI." -ForegroundColor Green
        $codiceUscita = 0
    }
    else {
        Write-Host ("ESITO: il ciclo e' riuscito, ma i log contengono {0} righe sospette" -f $sospetti.Count) -ForegroundColor Red
        Write-Host "elencate sopra. Vanno lette una per una prima di dichiarare RNF-01." -ForegroundColor Red
        $codiceUscita = 2
    }
    Write-Host ""
    Write-Host ("Verbale: {0}" -f $Verbale) -ForegroundColor White
    Write-Host ("Log:     {0}" -f $CartellaEsiti) -ForegroundColor White
    Write-Host ""
    Write-Host "Ora si puo' riattaccare la rete." -ForegroundColor White
}
catch {
    Write-Host ""
    Write-Host "PROVA FALLITA: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Ora si puo' riattaccare la rete: il verbale e i log restano su disco." -ForegroundColor White
    $codiceUscita = 1
}
finally {
    # Anche in caso di eccezione i due processi non devono restare in giro: la
    # 8000 occupata da un runserver orfano si manifesterebbe alla prossima
    # esecuzione come un errore che non c'entra nulla con questa.
    foreach ($p in @($ProcessoServer, $ProcessoWorker)) {
        if ($p -and -not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            Write-Host ("       processo {0} fermato dalla clausola finally" -f $p.Id) -ForegroundColor DarkGray
        }
    }
    Stop-Transcript | Out-Null
}

exit $codiceUscita
