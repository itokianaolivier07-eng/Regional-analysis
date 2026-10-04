# User Prompts — Pipeline territorial Corse (format compact)

## DEPARTEMENT_L1

Analyse le lot suivant pour {territoire} pendant {mois}.
Tranche le domaine critique (secteur vraiment mis en avant, cohérent avec les faits).

LOT_ID: {lot_id}
DOMAINE_IMPOSE: {domaine}

SIGNAUX :
{signaux_json}

Retourne exactement :
{{
  "lot_id": "{lot_id}",
  "type": "synthese_l1",
  "mois": "{mois}",
  "source_territoire": "{territoire}",
  "region": "Corse",
  "domaine_critique": "",
  "gravite": "critique|eleve|grave|modere|faible",
  "problematique": "",
  "cause": "",
  "preuve": "",
  "consequence": "",
  "solution": "",
  "chiffres_cles": [],
  "resume": "",
  "document_ids": [],
  "meta": {{}}
}}

## DEPARTEMENT_L2

Consolide les micro-synthèses L1 suivantes pour {territoire}, mois {mois}.
Tranche le domaine critique dominant.

LOT_ID: {lot_id}
DOMAINE_IMPOSE: {domaine}

MICRO-SYNTHESES :
{syntheses_json}

Retourne exactement :
{{
  "lot_id": "{lot_id}",
  "type": "synthese_l2",
  "mois": "{mois}",
  "source_territoire": "{territoire}",
  "region": "Corse",
  "domaine_critique": "",
  "gravite": "critique|eleve|grave|modere|faible",
  "problematique": "",
  "cause": "",
  "preuve": "",
  "consequence": "",
  "solution": "",
  "chiffres_cles": [],
  "resume": "",
  "analyses_sources": [],
  "document_ids": [],
  "meta": {{}}
}}

## DEPARTEMENT_L3

Produis le bilan transversal pour {territoire}, mois {mois}.
Tranche le domaine critique du territoire.

LOT_ID: {lot_id}
DOMAINE_IMPOSE: {domaine}

MESO-SYNTHESES :
{syntheses_json}

Retourne exactement :
{{
  "lot_id": "{lot_id}",
  "type": "synthese_l3",
  "mois": "{mois}",
  "source_territoire": "{territoire}",
  "region": "Corse",
  "domaine_critique": "",
  "gravite": "critique|eleve|grave|modere|faible",
  "problematique": "",
  "cause": "",
  "preuve": "",
  "consequence": "",
  "solution": "",
  "chiffres_cles": [],
  "resume": "",
  "analyses_sources": [],
  "meta": {{}}
}}

## DEPARTEMENT_L4

Produis l'arbitrage final de {territoire}, mois {mois}.
Le domaine critique est imposé. Rédige problématique, cause, preuve, conséquence, solution et un verdict de décision (2-4 phrases).

DOMAINE_IMPOSE: {domaine}

BILANS L3 (ce domaine uniquement) :
{bilans_json}

AUTRES_DOMAINES (contexte) :
{autres_domaines_json}

ARBITRAGE (résultat du calcul Python) :
{arbitrage_json}

INDICATEURS PYTHON :
{indicateurs_json}

Retourne exactement :
{{
  "type": "synthese_finale_region",
  "mois": "{mois}",
  "source_territoire": "{territoire}",
  "region": "Corse",
  "domaine_critique": "{domaine}",
  "statut_urgence": "critique|eleve|grave|modere|faible",
  "gravite": "critique|eleve|grave|modere|faible",
  "problematique": "",
  "cause": "",
  "preuve": "",
  "consequence": "",
  "solution": "",
  "verdict": "",
  "priorites": [],
  "chiffres_cles": [],
  "analyses_sources": [],
  "meta": {{}}
}}

## REGION

Produis l'arbitrage régional de {region} pour {mois}.
Territoires : {territoires}.
Tranche le domaine critique régional.

SYNTHESES FINALES :
{finales_json}

Retourne exactement :
{{
  "type": "synthese_finale_region",
  "mois": "{mois}",
  "region": "{region}",
  "territoires_sources": [],
  "domaine_critique": "",
  "statut_urgence": "critique|eleve|grave|modere|faible",
  "gravite": "critique|eleve|grave|modere|faible",
  "problematique": "",
  "cause": "",
  "preuve": "",
  "consequence": "",
  "solution": "",
  "verdict": "",
  "priorites": [],
  "convergences": [],
  "divergences": [],
  "chiffres_cles": [],
  "analyses_sources": [],
  "meta": {{}}
}}