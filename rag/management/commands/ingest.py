"""Ingestione da riga di comando (T-18, RF-28).

Serve a due cose che l'admin non copre: automazione, e prova senza browser
durante lo sviluppo. Il percorso passato non viene indicizzato «in loco»: il
file viene COPIATO in MEDIA_ROOT come qualunque altro caricamento, perche' un
Document deve possedere il proprio file (l'admin ne offre il download, CA-2).
"""

from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from rag.models import Document, KnowledgeBase, RagPipeline
from rag.services.exceptions import IngestionError
from rag.services.ingestion import compute_checksum, ingest_document, trova_duplicato


class Command(BaseCommand):
    help = "Carica un PDF in una base di conoscenza e lo indicizza."

    def add_arguments(self, parser):
        # nargs="?" perche' con --reindex il file e' gia' quello del documento:
        # obbligare a ripeterne il percorso sarebbe un argomento ignorato.
        parser.add_argument(
            "path", nargs="?", default=None, help="Percorso del file PDF da indicizzare."
        )
        parser.add_argument(
            "--kb",
            dest="kb",
            default=None,
            help=(
                "Nome o id della base di conoscenza. Se omesso, si usa quella "
                "della pipeline predefinita (RF-26)."
            ),
        )
        parser.add_argument(
            "--reindex",
            dest="reindex",
            type=int,
            default=None,
            metavar="ID",
            help="Reindicizza un documento esistente invece di caricarne uno nuovo.",
        )
        parser.add_argument(
            "--async",
            dest="asincrono",
            action="store_true",
            help=(
                "Accoda l'indicizzazione invece di eseguirla, e termina subito. "
                "Richiede un worker in esecuzione (manage.py db_worker)."
            ),
        )

    def handle(self, *args, **options):
        if options["reindex"] is not None:
            documento = self._documento_esistente(options["reindex"])
        elif options["path"] is None:
            raise CommandError(
                "Indicare il percorso di un PDF, oppure --reindex ID per "
                "reindicizzare un documento gia' caricato."
            )
        else:
            documento = self._crea_documento(options["path"], options["kb"])

        if options["asincrono"]:
            # Il comando resta SINCRONO per difetto, ed e' una scelta: RNF-03
            # parla del ciclo richiesta/risposta HTTP, di cui un comando di
            # gestione non fa parte, e le prove di consegna (T-42 su ambiente
            # pulito, T-43 a rete staccata) devono poter girare senza un
            # secondo processo. --async serve a provare la coda senza passare
            # da HTTP.
            from rag.tasks import accoda_indicizzazione

            task_id = accoda_indicizzazione(documento)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Documento {documento.pk} accodato (task {task_id}). "
                    f"Lo esegue il worker: manage.py db_worker"
                )
            )
            return

        self.stdout.write(
            f"Indicizzazione del documento {documento.pk} "
            f"nella base «{documento.knowledge_base.name}»…"
        )
        self.stdout.write(
            self.style.WARNING(
                "Questo comando indicizza in linea e attende: il primo "
                "embedding puo' richiedere fino a ~20 s per il caricamento del "
                "modello in VRAM. Per accodare e tornare subito: --async."
            )
        )
        try:
            esito = ingest_document(documento)
        except IngestionError as exc:
            # Lo stato «Fallito» e il motivo sono gia' persistiti sul
            # documento: al comando resta da riportarlo in modo leggibile.
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Fatto — {esito}"))

    def _documento_esistente(self, pk: int) -> Document:
        documento = Document.objects.filter(pk=pk).first()
        if documento is None:
            raise CommandError(f"Nessun documento con id {pk}.")
        return documento

    def _crea_documento(self, path: str, kb_arg: str | None) -> Document:
        percorso = Path(path)
        if not percorso.is_file():
            raise CommandError(f"File non trovato: {percorso}")

        kb = self._base_di_conoscenza(kb_arg)

        # La deduplica si verifica PRIMA di copiare il file in MEDIA_ROOT:
        # rifiutare dopo la copia lascerebbe un file orfano sul disco.
        with percorso.open("rb") as f:
            checksum = compute_checksum(File(f))
        esistente = trova_duplicato(kb.pk, checksum)
        if esistente is not None:
            raise CommandError(
                f"Questo file e' gia' presente nella base «{kb.name}» come "
                f"documento {esistente.pk}. Per rifarne l'indice: "
                f"manage.py ingest --reindex {esistente.pk}"
            )

        documento = Document(knowledge_base=kb, original_filename=percorso.name)
        with percorso.open("rb") as f:
            documento.file.save(percorso.name, File(f), save=False)
        documento.save()
        return documento

    def _base_di_conoscenza(self, kb_arg: str | None) -> KnowledgeBase:
        if kb_arg is None:
            pipeline = RagPipeline.objects.filter(is_default=True).first()
            if pipeline is None:
                raise CommandError(
                    "Nessuna pipeline predefinita: indicare la base di "
                    "conoscenza con --kb."
                )
            return pipeline.knowledge_base
        if kb_arg.isdigit():
            kb = KnowledgeBase.objects.filter(pk=int(kb_arg)).first()
        else:
            kb = KnowledgeBase.objects.filter(name=kb_arg).first()
        if kb is None:
            disponibili = ", ".join(KnowledgeBase.objects.values_list("name", flat=True))
            raise CommandError(
                f"Base di conoscenza «{kb_arg}» inesistente. Disponibili: {disponibili}"
            )
        return kb
