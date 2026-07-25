"""Interrogazione da riga di comando (T-27, RF-28).

Il gemello di `manage.py ingest` sul lato lettura. Serve alle stesse due cose:
automazione, e prova senza browser — che in P3 vuol dire prima che le API di
P4 esistano.

Sostituisce scripts/spike_rag.py, che viene cancellato con questa fase: da qui
in avanti non esiste piu' alcun percorso che risponda a una domanda con
parametri scritti nel codice.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from rag.services.exceptions import QueryError
from rag.services.query import rispondi


class Command(BaseCommand):
    help = "Interroga la base di conoscenza usando una pipeline configurata."

    def add_arguments(self, parser):
        parser.add_argument("domanda", help="La domanda, fra virgolette.")
        parser.add_argument(
            "--pipeline",
            dest="pipeline",
            default=None,
            help=(
                "Nome o id della pipeline da usare. Se omesso si usa quella "
                "predefinita (RF-15, RF-26)."
            ),
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Stampa l'esito completo in JSON, per l'automazione.",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "L'interrogazione e' sincrona. Il primo embedding e la prima "
                "generazione dopo l'avvio possono richiedere alcune decine di "
                "secondi per il caricamento dei modelli in VRAM."
            )
        )
        try:
            esito = rispondi(options["domanda"], pipeline=options["pipeline"])
        except QueryError as exc:
            # Il QueryLog e' gia' stato scritto: al comando resta da riportarlo
            # in modo leggibile, esattamente come fa `ingest` con lo stato
            # «Fallito».
            raise CommandError(str(exc)) from exc

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "domanda": esito.domanda,
                        "risposta": esito.risposta,
                        "pipeline": esito.pipeline_nome,
                        "generata": esito.generata,
                        "fonti": esito.fonti,
                        "retrieval_ms": esito.retrieval_ms,
                        "generation_ms": esito.generation_ms,
                        "latency_ms": esito.latency_ms,
                        "query_log_id": esito.query_log_id,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"D: {esito.domanda}"))
        self.stdout.write(f"R: {esito.risposta}")
        self.stdout.write("")
        if esito.fonti:
            self.stdout.write("Fonti:")
            for posizione, fonte in enumerate(esito.fonti, start=1):
                self.stdout.write(
                    f"  {posizione}. {fonte['documento']}, pagina "
                    f"{fonte['pagina']} — punteggio {fonte['punteggio']}"
                )
                self.stdout.write(f"     {fonte['estratto']}")
        else:
            # Non e' un errore: e' RF-14, e va detto invece di lasciare un
            # vuoto che somiglia a un guasto.
            self.stdout.write(
                "Nessuna fonte: nessun segmento ha superato la soglia di "
                "pertinenza configurata (RF-14)."
            )
        self.stdout.write("")
        self.stdout.write(
            f"Pipeline «{esito.pipeline_nome}» — recupero {esito.retrieval_ms} ms, "
            f"generazione {esito.generation_ms} ms, totale {esito.latency_ms} ms "
            f"(interrogazione {esito.query_log_id})"
        )
