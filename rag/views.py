"""Viste di servizio. Le API del RAG arrivano in P4 (T-28 → T-31)."""

import httpx
from django.conf import settings
from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _check_database() -> tuple[bool, str]:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - l'health check riporta, non gestisce
        return False, str(exc)


def _check_pgvector() -> tuple[bool, str]:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cur.fetchone()
        if row:
            return True, f"vector {row[0]}"
        return False, "estensione 'vector' non installata"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _check_ollama() -> tuple[bool, str]:
    try:
        resp = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return True, f"{len(models)} modelli disponibili"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    checks = {
        "database": _check_database(),
        "pgvector": _check_pgvector(),
        "ollama": _check_ollama(),
    }
    healthy = all(ok for ok, _ in checks.values())
    return Response(
        {
            "status": "ok" if healthy else "degraded",
            "checks": {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()},
        },
        status=200 if healthy else 503,
    )
