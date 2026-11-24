"""Invite-only onboarding: the admin creates a user, the user sets their own password."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def invite_link(request, user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    return request.build_absolute_uri(path)


def send_invite(request, user) -> None:
    context = {"user": user, "link": invite_link(request, user)}
    subject = render_to_string("accounts/invite_subject.txt", context).strip()
    body = render_to_string("accounts/invite_email.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
