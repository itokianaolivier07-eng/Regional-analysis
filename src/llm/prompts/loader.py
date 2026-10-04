"""
Charge les system prompts et user templates depuis les fichiers .md
centralisés (system_prompts.md, user_prompts.md), pour que les prompts
métier soient éditables sans toucher au code Python.
"""
import os
import re
from functools import lru_cache

_DIR = os.path.dirname(os.path.abspath(__file__))
SYSTEM_PROMPTS_FILE = os.path.join(_DIR, "system_prompts.md")
USER_PROMPTS_FILE = os.path.join(_DIR, "user_prompts.md")


def _parse_sections(filepath: str) -> dict:
    """Découpe un .md en sections par titre '## NOM' -> texte."""
    with open(filepath, "r", encoding="utf-8") as fh:
        content = fh.read()

    sections = {}
    parts = re.split(r"^##\s+(.+)$", content, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1].strip()
        sections[name] = body
    return sections


@lru_cache(maxsize=1)
def _system_sections() -> dict:
    return _parse_sections(SYSTEM_PROMPTS_FILE)


@lru_cache(maxsize=1)
def _user_sections() -> dict:
    return _parse_sections(USER_PROMPTS_FILE)


def load_system_prompt(name: str) -> str:
    """Retourne le SYSTEM_PROMPT de la section `name` (ex: 'DEPARTEMENT_L1', 'REGION')."""
    sections = _system_sections()
    if name not in sections:
        raise KeyError(
            f"Section '{name}' introuvable dans {SYSTEM_PROMPTS_FILE}. "
            f"Sections disponibles : {list(sections.keys())}"
        )
    return sections[name]


def load_user_template(name: str) -> str:
    """Retourne le USER_TEMPLATE de la section `name` (ex: 'DEPARTEMENT_L1', 'REGION')."""
    sections = _user_sections()
    if name not in sections:
        raise KeyError(
            f"Section '{name}' introuvable dans {USER_PROMPTS_FILE}. "
            f"Sections disponibles : {list(sections.keys())}"
        )
    return sections[name]


def load_prompts(name: str) -> tuple:
    """Retourne (system_prompt, user_template) de la section `name`."""
    return load_system_prompt(name), load_user_template(name)