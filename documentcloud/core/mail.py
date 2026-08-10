# Django
from django.conf import settings
from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import render_to_string

# Standard Library
import logging
from email.utils import parseaddr

# Third Party
from html2text import html2text

logger = logging.getLogger(__name__)


class Email(EmailMultiAlternatives):
    """Custom email class to handle our transactional email"""

    template = None

    def __init__(self, **kwargs):
        user = kwargs.pop("user", None)
        extra_context = kwargs.pop("extra_context", {})
        template = kwargs.pop("template", self.template)
        from_email = kwargs.pop("from_email", None)
        super().__init__(from_email=from_email or settings.DEFAULT_FROM_EMAIL, **kwargs)

        # MAILGUN_SENDER_DOMAIN pins the sending domain globally, ignoring the
        # From address - override it only when sending as somebody else
        if from_email:
            self.envelope_sender = from_email

        # set up who we are sending the email to
        if user:
            self.to.append(user.email)

        if not self.to:
            logger.warning(
                "Email created with no receipients - User: %s, Subject: %s",
                user,
                self.subject,
            )
        # always BCC diagnostics
        self.bcc.append("diagnostics@muckrock.com")

        # brand the email to match whoever it is being sent as, so an Add-On
        # sending under its own address does not look like it came from us
        from_name, contact_email = parseaddr(self.from_email)
        context = {
            "base_url": settings.DOCCLOUD_URL,
            "subject": self.subject,
            "user": user,
            "from_name": from_name or contact_email,
            "contact_email": contact_email,
        }
        context.update(extra_context)
        html = render_to_string(template, context)
        plain = html2text(html)
        self.body = plain
        self.attach_alternative(html, "text/html")

    def send(self, fail_silently=False):
        if self.to:
            super().send(fail_silently)
        else:
            logger.warning(
                "Refusing to send email with no recipients: %s", self.subject
            )


def send_mail(**kwargs):
    email = Email(**kwargs)
    email.send()
