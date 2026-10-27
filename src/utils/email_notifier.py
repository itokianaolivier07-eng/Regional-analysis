"""
Notifications SMTP vers l'admin.

Envoie un e-mail pour :
  - démarrage du système (vue d'ensemble config + paramètres run)
  - fin d'une analyse (pipeline terminé) avec rapport détaillé
  - erreurs bloquantes (crash, 429, JSON illisible, etc.) avec détails précis

Si SMTP_ENABLED=false ou si la config est incomplète, les appels
sont silencieusement ignorés (log warning uniquement) pour ne jamais
faire planter le pipeline à cause de l'e-mail.
"""
from __future__ import annotations

import html
import smtplib
import socket
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

from config import settings


# ---------------------------------------------------------------------------
# SMTP bas niveau
# ---------------------------------------------------------------------------

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
    html_body: Optional[str] = None,
) -> bool:
    """
    Envoie un e-mail à tous les destinataires listés dans ADMIN_EMAIL
    (adresses séparées par des virgules).
    Retourne True si l'envoi a réussi, False sinon.
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
                "SMTP désactivé ou config incomplète - e-mail non envoyé: %s",
                subject,
            )
        return False

    recipients = [
        addr.strip()
        for addr in settings.ADMIN_EMAIL.split(",")
        if addr.strip()
    ]
    if not recipients:
        if logger:
            logger.warning("ADMIN_EMAIL vide - e-mail non envoyé: %s", subject)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

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
                recipients,
                msg.as_string(),
            )

        if logger:
            logger.info(
                "E-mail admin envoyé: %s - %s",
                subject,
                ", ".join(recipients),
            )
        return True

    except (smtplib.SMTPException, socket.error, OSError, TimeoutError) as exc:
        if logger:
            logger.warning("Échec envoi e-mail admin (%s): %s", subject, exc)
        return False
    except Exception as exc:
        if logger:
            logger.warning("Erreur inattendue SMTP (%s): %s", subject, exc)
        return False


# ---------------------------------------------------------------------------
# Helpers formatage
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _esc(value: Any) -> str:
    return html.escape(str(value) if value is not None else "—")


def _fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "—"
    if s < 60:
        return f"{s:.1f} s"
    m, sec = divmod(int(round(s)), 60)
    if m < 60:
        return f"{m} min {sec:02d} s"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min {sec:02d} s"


def _llm_model_label() -> str:
    provider = (getattr(settings, "LLM_PROVIDER", "auto") or "auto").lower()
    if provider == "google":
        return f"Google · {getattr(settings, 'GOOGLE_AI_MODEL', '?')}"
    if provider == "openrouter":
        return f"OpenRouter · {getattr(settings, 'OPENROUTER_MODEL', '?')}"
    return (
        f"auto (Google: {getattr(settings, 'GOOGLE_AI_MODEL', '?')} "
        f"/ OpenRouter: {getattr(settings, 'OPENROUTER_MODEL', '?')})"
    )


def _wrap_html(title: str, accent: str, sections_html: str) -> str:
    """Template HTML minimal, pro, compatible clients mail."""
    return f"""\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(title)}</title>
</head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb;">
          <tr>
            <td style="background:{accent};padding:18px 24px;">
              <div style="font-size:13px;letter-spacing:0.04em;text-transform:uppercase;color:rgba(255,255,255,0.85);">Pipeline Analyse Territoriale</div>
              <div style="font-size:20px;font-weight:600;color:#ffffff;margin-top:4px;">{_esc(title)}</div>
            </td>
          </tr>
          <tr>
            <td style="padding:24px;">
              {sections_html}
            </td>
          </tr>
          <tr>
            <td style="padding:14px 24px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280;">
              Envoyé automatiquement · {_esc(_now())} · hôte {_esc(socket.gethostname())}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _kv_table(rows: List[Tuple[str, str]]) -> str:
    cells = []
    for label, value in rows:
        cells.append(
            f'<tr>'
            f'<td style="padding:6px 12px 6px 0;color:#6b7280;vertical-align:top;white-space:nowrap;">{_esc(label)}</td>'
            f'<td style="padding:6px 0;font-weight:500;vertical-align:top;">{value}</td>'
            f'</tr>'
        )
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;font-size:14px;border-collapse:collapse;">'
        + "".join(cells)
        + "</table>"
    )


def _section(title: str, body_html: str) -> str:
    return (
        f'<div style="margin-bottom:20px;">'
        f'<div style="font-size:12px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:#6b7280;margin-bottom:8px;">{_esc(title)}</div>'
        f'{body_html}'
        f'</div>'
    )


def _badge(text: str, bg: str, fg: str = "#fff") -> str:
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'background:{bg};color:{fg};font-size:12px;font-weight:600;">{_esc(text)}</span>'
    )


# ---------------------------------------------------------------------------
# Extraction stats depuis results
# ---------------------------------------------------------------------------

_STAGE_LABELS = {
    "0": "Stage 0 · Normalisation",
    "1": "Stage 1 · Micro (L1)",
    "2": "Stage 2 · Méso (L2)",
    "3": "Stage 3 · Bilan (L3)",
    "4": "Stage 4 · Finale régionale",
}


def _collect_stage_rows(results: Optional[dict]) -> List[Dict[str, Any]]:
    """Aplatit les résultats de stages pour le rapport."""
    rows: List[Dict[str, Any]] = []
    if not results:
        return rows
    territoires = results.get("territoires") or {}
    for territoire, stage_map in territoires.items():
        if not isinstance(stage_map, dict):
            continue
        if stage_map.get("skipped"):
            rows.append({
                "territoire": territoire,
                "stage": "—",
                "label": "Territoire déjà traité (skip)",
                "docs": None,
                "lots": None,
                "succes": None,
                "skipped": None,
                "erreurs": None,
                "duree": None,
                "error": None,
                "skipped_territory": True,
            })
            continue
        for stage_key in sorted(stage_map.keys(), key=lambda x: str(x)):
            res = stage_map[stage_key]
            if not isinstance(res, dict):
                continue
            docs = (
                res.get("docs_llm")
                if res.get("docs_llm") is not None
                else res.get("nb_docs")
                if res.get("nb_docs") is not None
                else res.get("nb_bilans_l3")
                if res.get("nb_bilans_l3") is not None
                else res.get("documents")
            )
            rows.append({
                "territoire": territoire,
                "stage": str(stage_key),
                "label": _STAGE_LABELS.get(str(stage_key), f"Stage {stage_key}"),
                "docs": docs,
                "lots": res.get("lots_total"),
                "succes": res.get("succes"),
                "skipped": res.get("skipped"),
                "erreurs": res.get("erreurs"),
                "duree": res.get("duree_secondes"),
                "error": res.get("error"),
                "skipped_territory": False,
            })
    return rows


def _sum_metric(rows: List[Dict[str, Any]], key: str) -> Optional[int]:
    total = 0
    found = False
    for r in rows:
        v = r.get(key)
        if v is not None:
            try:
                total += int(v)
                found = True
            except (TypeError, ValueError):
                pass
    return total if found else None


def _build_report_plain(results: Optional[dict], duree_totale: Optional[float] = None) -> str:
    lines: List[str] = []
    rows = _collect_stage_rows(results)
    if not rows:
        lines.append("Aucun détail de stage disponible.")
        return "\n".join(lines)

    lines.append("── Rapport par stage ──────────────────────────────────")
    for r in rows:
        if r.get("skipped_territory"):
            lines.append(f"  [{r['territoire']}] déjà traité (skip)")
            continue
        parts = [f"  [{r['territoire']}] {r['label']}"]
        meta = []
        if r["docs"] is not None:
            meta.append(f"docs={r['docs']}")
        if r["lots"] is not None:
            meta.append(f"lots={r['lots']}")
        if r["succes"] is not None:
            meta.append(f"ok={r['succes']}")
        if r["skipped"] is not None:
            meta.append(f"skip={r['skipped']}")
        if r["erreurs"] is not None:
            meta.append(f"err={r['erreurs']}")
        if r["duree"] is not None:
            meta.append(f"durée={_fmt_duration(r['duree'])}")
        if meta:
            parts.append(" · ".join(meta))
        if r.get("error"):
            parts.append(f"  ⚠ {r['error']}")
        lines.append("\n".join(parts) if len(parts) > 1 else parts[0])

    total_succes = _sum_metric(rows, "succes")
    total_erreurs = _sum_metric(rows, "erreurs")
    total_skipped = _sum_metric(rows, "skipped")
    lines.append("")
    lines.append("── Totaux ────────────────────────────────────────────")
    if total_succes is not None:
        lines.append(f"  Succès   : {total_succes}")
    if total_skipped is not None:
        lines.append(f"  Skipped  : {total_skipped}")
    if total_erreurs is not None:
        lines.append(f"  Erreurs  : {total_erreurs}")
    if duree_totale is not None:
        lines.append(f"  Durée    : {_fmt_duration(duree_totale)}")
    return "\n".join(lines)


def _build_report_html(results: Optional[dict], duree_totale: Optional[float] = None) -> str:
    rows = _collect_stage_rows(results)
    if not rows:
        return "<p style='color:#6b7280;font-size:14px;'>Aucun détail de stage disponible.</p>"

    header = (
        "<tr style='background:#f9fafb;font-size:12px;color:#6b7280;text-align:left;'>"
        "<th style='padding:8px 10px;'>Stage</th>"
        "<th style='padding:8px 10px;'>Docs / lots</th>"
        "<th style='padding:8px 10px;'>Succès</th>"
        "<th style='padding:8px 10px;'>Skip</th>"
        "<th style='padding:8px 10px;'>Err.</th>"
        "<th style='padding:8px 10px;'>Durée</th>"
        "</tr>"
    )
    body_rows = []
    for r in rows:
        if r.get("skipped_territory"):
            body_rows.append(
                f"<tr><td colspan='6' style='padding:10px;color:#6b7280;font-size:13px;'>"
                f"{_esc(r['territoire'])} — déjà traité (skip)</td></tr>"
            )
            continue
        docs_lots = []
        if r["docs"] is not None:
            docs_lots.append(f"{r['docs']} doc(s)")
        if r["lots"] is not None:
            docs_lots.append(f"{r['lots']} lot(s)")
        docs_cell = " · ".join(docs_lots) if docs_lots else "—"
        err_style = "color:#b91c1c;font-weight:600;" if (r.get("erreurs") or 0) else ""
        err_cell = f"<span style='{err_style}'>{_esc(r['erreurs'] if r['erreurs'] is not None else '—')}</span>"
        error_note = (
            f"<div style='font-size:12px;color:#b91c1c;margin-top:2px;'>{_esc(r['error'])}</div>"
            if r.get("error")
            else ""
        )
        body_rows.append(
            f"<tr style='border-top:1px solid #f3f4f6;font-size:13px;'>"
            f"<td style='padding:10px;'><strong>{_esc(r['label'])}</strong>"
            f"<div style='color:#9ca3af;font-size:11px;'>{_esc(r['territoire'])}</div>{error_note}</td>"
            f"<td style='padding:10px;'>{_esc(docs_cell)}</td>"
            f"<td style='padding:10px;'>{_esc(r['succes'] if r['succes'] is not None else '—')}</td>"
            f"<td style='padding:10px;'>{_esc(r['skipped'] if r['skipped'] is not None else '—')}</td>"
            f"<td style='padding:10px;'>{err_cell}</td>"
            f"<td style='padding:10px;'>{_esc(_fmt_duration(r['duree']))}</td>"
            f"</tr>"
        )

    table = (
        "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' "
        "style='border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;border-collapse:collapse;'>"
        f"{header}{''.join(body_rows)}</table>"
    )

    totals = []
    for label, key in (("Succès", "succes"), ("Skipped", "skipped"), ("Erreurs", "erreurs")):
        v = _sum_metric(rows, key)
        if v is not None:
            color = "#b91c1c" if key == "erreurs" and v > 0 else "#111827"
            totals.append(
                f"<span style='margin-right:16px;font-size:13px;'>"
                f"<span style='color:#6b7280;'>{label}</span> "
                f"<strong style='color:{color};'>{v}</strong></span>"
            )
    if duree_totale is not None:
        totals.append(
            f"<span style='font-size:13px;'>"
            f"<span style='color:#6b7280;'>Durée totale</span> "
            f"<strong>{_esc(_fmt_duration(duree_totale))}</strong></span>"
        )
    totals_html = (
        f"<div style='margin-top:12px;padding:10px 12px;background:#f9fafb;"
        f"border-radius:6px;border:1px solid #e5e7eb;'>{''.join(totals)}</div>"
        if totals
        else ""
    )
    return table + totals_html


# ---------------------------------------------------------------------------
# Notifications publiques
# ---------------------------------------------------------------------------

def notify_startup(
    *,
    stage: str = "all",
    mois: Optional[str] = None,
    departement: Optional[str] = None,
    force_update: bool = False,
) -> bool:
    """Notification au démarrage — vue d'ensemble config + paramètres du run."""
    host = socket.gethostname()
    mois = mois or "?"
    region = getattr(settings, "REGION_NAME", "Corse")
    subject = f"[Pipeline {region}] ▶ Démarrage — mois {mois}"

    max_docs = getattr(settings, "MAX_DOCS_PER_RUN", 0) or "illimité"
    plain_lines = [
        f"Le pipeline d'analyse territoriale {region} a démarré.",
        "",
        "── Run ────────────────────────────────────────────────",
        f"  Horodatage   : {_now()}",
        f"  Hôte         : {host}",
        f"  Stage        : {stage}",
        f"  Mois         : {mois}",
        f"  Département  : {departement or f'{region} (pipeline unique)'}",
        f"  Force update : {'OUI' if force_update else 'non'}",
        "",
        "── Configuration ──────────────────────────────────────",
        f"  LLM provider : {getattr(settings, 'LLM_PROVIDER', '?')}",
        f"  Modèle       : {_llm_model_label()}",
        f"  Batch size   : {getattr(settings, 'BATCH_SIZE', '?')}",
        f"  Max workers  : {getattr(settings, 'MAX_WORKERS', '?')}",
        f"  Max docs/run : {max_docs}",
        f"  Pause LLM    : {getattr(settings, 'PAUSE_SECONDES', '?')} s",
        f"  Timeout LLM  : {getattr(settings, 'LLM_TIMEOUT_SECONDES', '?')} s",
        f"  DB Mongo     : {getattr(settings, 'MONGO_DB_NAME', '?')}",
        f"  Collection   : {getattr(settings, 'MONGO_REGION_SYNTHESIS', '?')}",
        "",
    ]
    body = "\n".join(plain_lines)

    run_rows = [
        ("Horodatage", _esc(_now())),
        ("Hôte", _esc(host)),
        ("Stage demandé", _esc(stage)),
        ("Mois cible", f"<strong>{_esc(mois)}</strong>"),
        ("Territoire", _esc(departement or f"{region} (pipeline unique)")),
        (
            "Force update",
            _badge("OUI", "#b45309") if force_update else _badge("non", "#e5e7eb", "#374151"),
        ),
    ]
    cfg_rows = [
        ("Provider LLM", _esc(getattr(settings, "LLM_PROVIDER", "?"))),
        ("Modèle", _esc(_llm_model_label())),
        ("Batch size", _esc(getattr(settings, "BATCH_SIZE", "?"))),
        ("Workers parallèles", _esc(getattr(settings, "MAX_WORKERS", "?"))),
        ("Max docs / run", _esc(max_docs)),
        ("Pause entre appels", f"{_esc(getattr(settings, 'PAUSE_SECONDES', '?'))} s"),
        ("Timeout LLM", f"{_esc(getattr(settings, 'LLM_TIMEOUT_SECONDES', '?'))} s"),
        ("Base MongoDB", _esc(getattr(settings, "MONGO_DB_NAME", "?"))),
        ("Synthèse finale", _esc(getattr(settings, "MONGO_REGION_SYNTHESIS", "?"))),
    ]
    sections = (
        _section("Paramètres du run", _kv_table(run_rows))
        + _section("Configuration pipeline", _kv_table(cfg_rows))
    )
    html_body = _wrap_html(
        f"Démarrage — mois {mois}",
        accent="#2563eb",
        sections_html=sections,
    )
    return send_admin_email(subject, body, html_body=html_body)


def notify_analysis_done(
    results: Optional[dict] = None,
    *,
    mois: Optional[str] = None,
    run_id: Optional[str] = None,
    stage: str = "all",
    duree_secondes: Optional[float] = None,
    statut: str = "complete",
) -> bool:
    """
    Notification à la fin d'une analyse avec petit rapport détaillé
    (docs, lots, succès / skip / erreurs par stage, durée).
    """
    region = getattr(settings, "REGION_NAME", "Corse")
    mois = mois or (results or {}).get("mois") or "?"
    run_id = run_id or (results or {}).get("run_id") or "?"

    is_ok = statut == "complete"
    icon = "✓" if is_ok else "⚠"
    subject = (
        f"[Pipeline {region}] {icon} Analyse terminée — mois {mois} (run {run_id})"
    )

    plain = [
        f"L'analyse territoriale {region} s'est terminée"
        + (" avec succès." if is_ok else f" avec le statut « {statut} »."),
        "",
        "── Identifiants ───────────────────────────────────────",
        f"  Horodatage : {_now()}",
        f"  Mois       : {mois}",
        f"  Run ID     : {run_id}",
        f"  Stage      : {stage}",
        f"  Statut     : {statut}",
    ]
    if duree_secondes is not None:
        plain.append(f"  Durée      : {_fmt_duration(duree_secondes)}")
    plain.append("")
    plain.append(_build_report_plain(results, duree_totale=duree_secondes))
    body = "\n".join(plain) + "\n"

    status_badge = (
        _badge("COMPLET", "#15803d")
        if is_ok
        else _badge(statut.upper(), "#b45309")
    )
    id_rows = [
        ("Horodatage", _esc(_now())),
        ("Mois", f"<strong>{_esc(mois)}</strong>"),
        ("Run ID", f"<code style='font-size:13px;'>{_esc(run_id)}</code>"),
        ("Stage demandé", _esc(stage)),
        ("Statut", status_badge),
        ("Durée totale", _esc(_fmt_duration(duree_secondes))),
        (
            "Collection finale",
            _esc(getattr(settings, "MONGO_REGION_SYNTHESIS", "?")),
        ),
    ]
    sections = (
        _section("Identifiants du run", _kv_table(id_rows))
        + _section("Rapport détaillé", _build_report_html(results, duree_totale=duree_secondes))
    )
    html_body = _wrap_html(
        f"Analyse terminée — mois {mois}",
        accent="#15803d" if is_ok else "#b45309",
        sections_html=sections,
    )
    return send_admin_email(subject, body, html_body=html_body)


def notify_error(
    error: Any,
    *,
    context: str = "pipeline",
    mois: Optional[str] = None,
    stage: Optional[str] = None,
    run_id: Optional[str] = None,
    extra: Optional[str] = None,
    duree_secondes: Optional[float] = None,
) -> bool:
    """Notification pour une erreur bloquante (crash, 429, JSON, etc.)."""
    region = getattr(settings, "REGION_NAME", "Corse")
    mois = mois or "?"
    err_type = type(error).__name__ if isinstance(error, BaseException) else "Error"
    err_msg = str(error)

    lower = err_msg.lower()
    tag = "ERREUR"
    if "429" in err_msg or "quota" in lower or "rate limit" in lower:
        tag = "QUOTA / 429"
    elif "json" in lower or "parse" in lower or "illisible" in lower:
        tag = "JSON / PARSE"
    elif isinstance(error, KeyboardInterrupt):
        tag = "INTERRUPT"
    elif "timeout" in lower:
        tag = "TIMEOUT"
    elif "mongo" in lower or "pymongo" in lower:
        tag = "MONGODB"
    elif "run incomplet" in lower or "partial" in lower:
        tag = "RUN PARTIEL"

    subject = f"[Pipeline {region}] ✖ {tag} — {context} (mois {mois})"

    tb = ""
    if isinstance(error, BaseException):
        tb = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )

    plain_lines = [
        "Une erreur bloquante a interrompu le système.",
        "",
        "── Diagnostic ─────────────────────────────────────────",
        f"  Horodatage : {_now()}",
        f"  Tag        : {tag}",
        f"  Contexte   : {context}",
        f"  Type       : {err_type}",
        f"  Message    : {err_msg}",
        f"  Mois       : {mois}",
        f"  Stage      : {stage or '?'}",
        f"  Run ID     : {run_id or '?'}",
    ]
    if duree_secondes is not None:
        plain_lines.append(f"  Durée      : {_fmt_duration(duree_secondes)}")
    if extra:
        plain_lines.append(f"  Détails    : {extra}")
    if tb:
        plain_lines.extend(["", "── Traceback ─────────────────────────────────────────", tb.rstrip()])
    body = "\n".join(plain_lines)

    diag_rows = [
        ("Horodatage", _esc(_now())),
        ("Catégorie", _badge(tag, "#b91c1c")),
        ("Contexte", _esc(context)),
        ("Type Python", f"<code>{_esc(err_type)}</code>"),
        ("Message", f"<strong style='color:#b91c1c;'>{_esc(err_msg)}</strong>"),
        ("Mois", _esc(mois)),
        ("Stage", _esc(stage or "?")),
        ("Run ID", _esc(run_id or "?")),
    ]
    if duree_secondes is not None:
        diag_rows.append(("Durée avant échec", _esc(_fmt_duration(duree_secondes))))
    if extra:
        diag_rows.append(("Détails", _esc(extra)))

    sections = _section("Diagnostic", _kv_table(diag_rows))
    if tb:
        sections += _section(
            "Traceback",
            f"<pre style='margin:0;padding:12px;background:#111827;color:#e5e7eb;"
            f"border-radius:6px;font-size:11px;line-height:1.45;overflow-x:auto;"
            f"white-space:pre-wrap;word-break:break-word;'>{_esc(tb)}</pre>",
        )
    html_body = _wrap_html(
        f"{tag} — {context}",
        accent="#b91c1c",
        sections_html=sections,
    )
    return send_admin_email(subject, body, html_body=html_body)