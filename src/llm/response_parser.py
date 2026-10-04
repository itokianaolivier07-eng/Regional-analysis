"""
Parse les réponses JSON du LLM.

NB (correctif) : ce fichier contenait auparavant des fonctions
parse_stage1_response ... parse_stage5_response, avec des noms de champs
("resume_court", "gravite", "bilan_executif", "statut_urgency"...) qui ne
correspondaient à AUCUN schéma réellement utilisé par ce pipeline (voir
src/schema/schemas.py et src/llm/prompts/user_prompts.md, qui utilisent
"preoccupations_recurrentes", "tendances_dominantes", "statut_urgence",
etc.). Elles n'étaient appelées nulle part dans le code — un reliquat du
projet "analysis_entreprises" copié-collé lors de la création de ce
pipeline. Elles ont été supprimées pour éviter toute confusion ; la seule
fonction réellement utilisée par le pipeline est parse_json_response,
combinée à src.schema.schemas.validate_and_fill pour le remplissage des
valeurs par défaut.

Correctif supplémentaire : certains modèles open-weight (Llama via Groq/
OpenRouter notamment) laissent parfois une virgule finale avant `}` ou `]`,
ce qui est invalide en JSON strict et faisait échouer json.loads() pour
rien, consommant un retry LLM complet (donc un appel réseau/quota) alors
qu'une simple regex aurait suffi à réparer le texte localement.
"""
import json
import re


def _clean_json_text(raw_response: str) -> str:
    cleaned = raw_response.strip()

    # 1. Si format ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    else:
        # 2. Chercher le premier '{' ou '[' et le dernier '}' ou ']'
        #    si la réponse est tronquée, on garde au moins le bloc JSON
        #    commencé mais sans garantir qu'il est complet.
        first_brace = cleaned.find("{")
        first_bracket = cleaned.find("[")
        first_json = min(
            [idx for idx in (first_brace, first_bracket) if idx != -1],
            default=-1,
        )
        if first_json != -1:
            last_brace = cleaned.rfind("}")
            last_bracket = cleaned.rfind("]")
            last_json = max(
                [idx for idx in (last_brace, last_bracket) if idx != -1],
                default=-1,
            )
            if last_json > first_json:
                cleaned = cleaned[first_json : last_json + 1].strip()
            else:
                cleaned = cleaned[first_json:].strip()

    return cleaned


def _strip_trailing_commas(text: str) -> str:
    """Supprime les virgules juste avant `}` ou `]` (JSON invalide mais
    fréquent chez certains modèles). N'agit pas sur les virgules à
    l'intérieur de chaînes grâce à une regex conservatrice limitée aux
    espaces/retours à la ligne entre la virgule et le délimiteur fermant."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _repair_truncated_json(text: str) -> str:
    """Restaure un JSON tronqué à la fin d'un élément partiellement écrit.

    Exemple typique :
      {"document_ids": ["a", "b", "adc40}
    devient
      {"document_ids": ["a", "b"]}
    en supprimant la dernière valeur incomplète puis en fermant les
    conteneurs ouverts.
    """
    candidate = _strip_trailing_commas(text).strip()
    if not candidate:
        return candidate

    # Si la chaîne se termine avec un tableau/objet ouverte, on enlève le
    # dernier fragment partiel dès qu'un des champs est resté inachevé.
    quote_positions = []
    escaped = False
    for idx, ch in enumerate(candidate):
        if ch == "\\" and not escaped:
            escaped = True
            continue
        if ch == '"' and not escaped:
            quote_positions.append(idx)
        escaped = False

    if len(quote_positions) % 2 == 1:
        last_quote = quote_positions[-1]
        last_comma = candidate.rfind(",", 0, last_quote)
        if last_comma != -1:
            candidate = candidate[:last_comma].rstrip()
        else:
            candidate = candidate[:last_quote].rstrip()

    stack: list[str] = []
    quote: str | None = None
    escaped = False
    for ch in candidate:
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue

        if ch in ('"', "'"):
            quote = ch
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()

    while stack:
        candidate += stack.pop()

    return candidate


def parse_json_response(raw_response: str) -> dict:
    """Parse générique d'une réponse LLM en JSON (utilisé par tous les stages)."""
    if not raw_response:
        return {}
    cleaned = _clean_json_text(raw_response)

    for candidate in (
        cleaned,
        _strip_trailing_commas(cleaned),
        _repair_truncated_json(cleaned),
    ):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list) and data:
            data = data[0]
        if not isinstance(data, dict):
            return {}
        return data

    return {}
