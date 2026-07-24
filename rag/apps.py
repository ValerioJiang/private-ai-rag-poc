from django.apps import AppConfig


class RagConfig(AppConfig):
    name = "rag"
    verbose_name = "Sistema RAG"

    def ready(self) -> None:
        # L'import ha come solo scopo la registrazione dei @receiver.
        from . import signals  # noqa: F401
