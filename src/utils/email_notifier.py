"""
Notifications SMTP vers l'admin.

Envoie un e-mail pour :
  - démarrage du système
  - fin d'une analyse (pipeline terminé)
  - erreurs bloquantes (crash, 429, JSON illisible, etc.)

Si SMTP_ENABLED=false ou si la config est incomplète, les appels
sont silencieusement ignorés (log warning uniquement) pour ne jamais
faire planter le pipeline à cause de l'e-mail.
"""
from __future__ import annotations

import smtplib
import socket
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from config import settings


def _smtp_ready() -> bool:
    if not getattr(settings, "SMTP_ENABLED", False):
        return False
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_PORT
        and settings.ADMIN_EMAIL
        and settings.SMTP_FROM
    )


def send_admin_email(
    subject: str,
    body: str,
    *,
    html: Optional[str] = None,
) -> bool:
    """
    Envoie un e-mail à ADMIN_EMAIL.
    Retourne True si l'envoi a réussi, False sinon (jamais d'exception
    propagée vers l'appelant).
    """
    logger = None
    try:
        from src.utils.logger import get_logger
        logger = get_logger()
    except Exception:
        pass

    if not _smtp_ready():
        if logger:
            logger.debug(
                "SMTP désactivé ou config incomplète — e-mail non envoyé: %s",
                subject,
            )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = settings.ADMIN_EMAIL
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if settings.SMTP_USE_SSL:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT,
            )
        else:
            server = smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT,
            )
            if settings.SMTP_USE_TLS:
                server.starttls()

        with server:
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(
                settings.SMTP_FROM,
                [settings.ADMIN_EMAIL],
                msg.as_string(),
            )

        if logger:
            logger.info("E-mail admin envoyé: %s → %s", subject, settings.ADMIN_EMAIL)
        return True

    except (smtplib.SMTPException, socket.error, OSError, TimeoutError) as exc:
        if logger:
            logger.warning("Échec envoi e-mail admin (%s): %s", subject, exc)
        return False
    except Exception as exc:
        if logger:
            logger.warning("Erreur inattendue SMTP (%s): %s", subject, exc)
        return False


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def notify_startup(
    *,
    stage: str = "all",
    mois: Optional[str] = None,
    departement: Optional[str] = None,
    force_update: bool = False,
) -> bool:
    """Notification au démarrage du système / du pipeline."""
    host = socket.gethostname()
    mois = mois or getattr(settings, "MOIS_CIBLE", "?")
    subject = f"[Pipeline Corse] Démarrage — mois {mois}"
    body = (
        f"Le pipeline d'analyse territoriale Corse a démarré.\n\n"
        f"Horodatage : {_now()}\n"
        f"Hôte       : {host}\n"
        f"Stage      : {stage}\n"
        f"Mois       : {mois}\n"
        f"Département: {departement or 'Corse (pipeline unique)'}\n"
        f"Force update: {force_update}\n"
        f"Provider LLM: {getattr(settings, 'LLM_PROVIDER', '?')}\n"
    )
    return send_admin_email(subject, body)


def notify_analysis_done(
    results: Optional[dict] = None,
    *,
    mois: Optional[str] = None,
    run_id: Optional[str] = None,
    stage: str = "all",
) -> bool:
    """Notification à la fin d'une analyse réussie."""
    mois = mois or (results or {}).get("mois") or getattr(settings, "MOIS_CIBLE", "?")
    run_id = run_id or (results or {}).get("run_id") or "?"
    subject = f"[Pipeline Corse] Analyse terminée — mois {mois} (run {run_id})"

    lines = [
        "L'analyse territoriale Corse s'est terminée avec succès.",
        "",
        f"Horodatage : {_now()}",
        f"Mois       : {mois}",
        f"Run ID     : {run_id}",
        f"Stage      : {stage}",
    ]

    if results:
        territoires = results.get("territoires") or {}
        for name, info in territoires.items():
            if isinstance(info, dict) and info.get("skipped"):
                lines.append(f"  - {name}: déjà traité (skip)")
            else:
                lines.append(f"  - {name}: exécuté")

    body = "\n".join(lines) + "\n"
    return send_admin_email(subject, body)


def notify_error(
    error: Any,
    *,
    context: str = "pipeline",
    mois: Optional[str] = None,
    stage: Optional[str] = None,
    run_id: Optional[str] = None,
    extra: Optional[str] = None,
) -> bool:
    """Notification pour une erreur bloquante (crash, 429, JSON, etc.)."""
    mois = mois or getattr(settings, "MOIS_CIBLE", "?")
    err_type = type(error).__name__ if isinstance(error, BaseException) else "Error"
    err_msg = str(error)

    lower = err_msg.lower()
    tag = "ERREUR"
    if "429" in err_msg or "quota" in lower or "rate limit" in lower:
        tag = "QUOTA/429"
    elif "json" in lower or "parse" in lower:
        tag = "JSON"
    elif isinstance(error, KeyboardInterrupt):
        tag = "INTERRUPT"
    elif "timeout" in lower:
        tag = "TIMEOUT"

    subject = f"[Pipeline Corse] {tag} — {context} (mois {mois})"

    tb = ""
    if isinstance(error, BaseException):
        tb = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )

    lines = [
        f"Une erreur bloquante a interrompu le système.",
        "",
        f"Horodatage : {_now()}",
        f"Contexte   : {context}",
        f"Type       : {err_type}",
        f"Message    : {err_msg}",
        f"Mois       : {mois}",
        f"Stage      : {stage or '?'}",
        f"Run ID     : {run_id or '?'}",
    ]
    if extra:
        lines.append(f"Détails    : {extra}")
    if tb:
        lines.extend(["", "--- Traceback ---", tb])

    body = "\n".join(lines)
    return send_admin_email(subject, body)