"""Notifications sortantes vers l'abonné : e-mail (Gmail SMTP), SMS et WhatsApp.

Chaque canal n'est utilisé que s'il est configuré (variables d'environnement) et
si l'abonné a renseigné la coordonnée correspondante. Un canal absent est
signalé « non configuré » : aucun envoi n'est jamais simulé comme réussi.

- E-mail : SMTP Django (Gmail par défaut, mot de passe d'application).
- SMS : API REST Twilio.
- WhatsApp : Meta Cloud API si ``WHATSAPP_CLOUD_TOKEN`` est défini, sinon
  Twilio WhatsApp si ``TWILIO_WHATSAPP_FROM`` est défini.
"""
import base64
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
META_MESSAGES_URL = "https://graph.facebook.com/{version}/{phone_id}/messages"
CHANNELS = ("email", "sms", "whatsapp")
# Types d'alerte poussés vers l'abonné hors de l'application.
NOTIFIED_PREFIXES = ("CREDIT_SEUIL_", "SOLDE_EPUISE")


def to_e164(raw: str) -> str:
    """Numéro au format international « +243… ». Chaîne vide si le numéro est inexploitable.

    Les numéros locaux RDC (0993…, 993…) reçoivent l'indicatif 243 ; un numéro
    déjà international (+250…, 00250…) est conservé.
    """
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if text.startswith("+"):
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        digits = "243" + digits[1:]
    elif len(digits) == 9:
        digits = "243" + digits
    return f"+{digits}" if 10 <= len(digits) <= 15 else ""


def _post(url: str, headers: dict, data: bytes, timeout: int = 15) -> tuple[int, dict]:
    """POST sans dépendance externe. Retourne (statut HTTP, corps JSON)."""
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"message": str(exc.reason)}
        return exc.code, body


def _twilio_configured() -> bool:
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"))


def _twilio_send(sender: str, recipient: str, body: str) -> None:
    sid, token = os.getenv("TWILIO_ACCOUNT_SID", ""), os.getenv("TWILIO_AUTH_TOKEN", "")
    credentials = base64.b64encode(f"{sid}:{token}".encode()).decode("ascii")
    status_code, response = _post(
        TWILIO_MESSAGES_URL.format(sid=sid),
        {"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
        urllib.parse.urlencode({"From": sender, "To": recipient, "Body": body}).encode("utf-8"),
    )
    if status_code >= 300:
        raise RuntimeError(f"Twilio HTTP {status_code} : {response.get('message', 'envoi refusé')}")


def _meta_whatsapp_send(recipient: str, body: str) -> None:
    token = os.getenv("WHATSAPP_CLOUD_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    template = os.getenv("WHATSAPP_TEMPLATE_NAME", "")
    message = {"messaging_product": "whatsapp", "to": recipient.lstrip("+")}
    if template:
        # Hors de la fenêtre de 24 h, Meta n'accepte qu'un modèle approuvé : le texte de
        # l'alerte est passé comme unique paramètre du corps du modèle.
        message.update({
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": os.getenv("WHATSAPP_TEMPLATE_LANG", "fr")},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": body}]}],
            },
        })
    else:
        message.update({"type": "text", "text": {"body": body}})
    status_code, response = _post(
        META_MESSAGES_URL.format(version=os.getenv("WHATSAPP_API_VERSION", "v21.0"), phone_id=phone_id),
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json.dumps(message).encode("utf-8"),
    )
    if status_code >= 300:
        detail = (response.get("error") or {}).get("message", "envoi refusé") if isinstance(response, dict) else "envoi refusé"
        raise RuntimeError(f"WhatsApp Cloud API HTTP {status_code} : {detail}")


def _whatsapp_provider() -> str:
    if os.getenv("WHATSAPP_CLOUD_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
        return "meta"
    if _twilio_configured() and os.getenv("TWILIO_WHATSAPP_FROM"):
        return "twilio"
    return ""


def configured_channels() -> dict:
    """Canaux utilisables côté serveur (indépendamment des coordonnées de l'abonné)."""
    return {
        "email": bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD),
        "sms": _twilio_configured() and bool(os.getenv("TWILIO_SMS_FROM")),
        "whatsapp": bool(_whatsapp_provider()),
    }


def notification_channels(meter) -> dict:
    """État de chaque canal pour un abonné : ``ready``, ``no_contact`` ou ``not_configured``."""
    configured = configured_channels()
    has_contact = {
        "email": bool(meter.subscriber_email),
        "sms": bool(to_e164(meter.subscriber_phone)),
        "whatsapp": bool(to_e164(meter.subscriber_phone)),
    }
    return {
        channel: "not_configured" if not configured[channel] else "ready" if has_contact[channel] else "no_contact"
        for channel in CHANNELS
    }


def send_notification(meter, subject: str, body: str) -> dict:
    """Envoie le message sur chaque canal prêt. Retourne le résultat par canal.

    Valeurs : ``sent``, ``not_configured``, ``no_contact`` ou ``error: <détail>``.
    L'échec d'un canal n'empêche pas les autres.
    """
    results = notification_channels(meter)
    phone = to_e164(meter.subscriber_phone)
    senders = {
        "email": lambda: send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [meter.subscriber_email], fail_silently=False),
        "sms": lambda: _twilio_send(os.getenv("TWILIO_SMS_FROM", ""), phone, body),
        "whatsapp": lambda: (
            _meta_whatsapp_send(phone, body) if _whatsapp_provider() == "meta"
            else _twilio_send(f"whatsapp:{os.getenv('TWILIO_WHATSAPP_FROM', '').removeprefix('whatsapp:')}", f"whatsapp:{phone}", body)
        ),
    }
    for channel in CHANNELS:
        if results[channel] != "ready":
            continue
        try:
            senders[channel]()
            results[channel] = "sent"
        except Exception as exc:  # un canal en panne ne bloque ni les autres ni la télémétrie
            results[channel] = f"error: {exc}"
            logger.warning("Notification %s en échec pour le compteur %s : %s", channel, meter.meter_id, exc)
    return results


def alert_message(meter, alert) -> tuple[str, str]:
    name = f"{meter.subscriber_first_name} {meter.subscriber_last_name}".strip() or "abonné"
    subject = f"Virunga Smart Energy — alerte crédit (compteur {meter.meter_id})"
    body = (
        f"Bonjour {name},\n{alert.message}\n"
        f"Compteur {meter.meter_id}. Rechargez depuis votre espace abonné pour éviter la coupure.\n"
        "Virunga Smart Energy"
    )
    return subject, body


def dispatch_alerts(meter, alerts) -> None:
    """Pousse vers l'abonné les alertes de crédit qui viennent d'être créées.

    Les envois partent dans un fil séparé : un prestataire lent ne doit jamais
    retarder la réponse de télémétrie attendue par le compteur.
    """
    to_send = [alert for alert in alerts if alert.kind.startswith(NOTIFIED_PREFIXES)]
    if not to_send:
        return

    def run():
        for alert in to_send:
            results = send_notification(meter, *alert_message(meter, alert))
            logger.info("Alerte %s (compteur %s) : %s", alert.kind, meter.meter_id, results)

    if settings.TESTING:
        run()
    else:
        threading.Thread(target=run, name=f"alertes-{meter.meter_id}", daemon=True).start()
