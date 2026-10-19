"""
Test rapide SMTP — envoie un seul e-mail de test à ADMIN_EMAIL.
Usage :
    python test_smtp.py
"""
from config import settings
from src.utils.email_notifier import send_admin_email, _smtp_ready


def main():
    print("--- Config SMTP ---")
    print(f"  SMTP_ENABLED : {settings.SMTP_ENABLED}")
    print(f"  SMTP_HOST    : {settings.SMTP_HOST or '(vide)'}")
    print(f"  SMTP_PORT    : {settings.SMTP_PORT}")
    print(f"  SMTP_USER    : {settings.SMTP_USER or '(vide)'}")
    print(f"  SMTP_FROM    : {settings.SMTP_FROM or '(vide)'}")
    print(f"  ADMIN_EMAIL  : {settings.ADMIN_EMAIL or '(vide)'}")
    print(f"  TLS / SSL    : {settings.SMTP_USE_TLS} / {settings.SMTP_USE_SSL}")
    print()

    if not _smtp_ready():
        print("ERREUR : config SMTP incomplète ou SMTP_ENABLED=false.")
        print("Vérifie le fichier .env (SMTP_ENABLED, SMTP_HOST, SMTP_FROM, ADMIN_EMAIL).")
        return 1

    print("Envoi d'un e-mail de test...")
    ok = send_admin_email(
        subject="[Pipeline Corse] Test SMTP OK",
        body=(
            "Ceci est un e-mail de test.\n\n"
            "Si tu reçois ce message, la configuration SMTP fonctionne.\n"
            "Le pipeline pourra notifier démarrage, fin d'analyse et erreurs.\n"
        ),
    )

    if ok:
        print("SUCCÈS : e-mail envoyé. Vérifie ta boîte (et les spams).")
        return 0
    else:
        print("ÉCHEC : voir le message d'erreur ci-dessus.")
        print("Causes fréquentes : mauvais mot de passe d'application,")
        print("2FA non activée, ou SMTP_USER / SMTP_PASSWORD incorrects.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())