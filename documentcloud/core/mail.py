# Django
from django.conf import settings
from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import render_to_string

# Standard Library
import logging

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
        super().__init__(**kwargs)
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

        context = {
            "base_url": settings.DOCCLOUD_URL,
            "subject": self.subject,
            "user": user,
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
