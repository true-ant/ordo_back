from django.dispatch import receiver
from django_rest_passwordreset.signals import reset_password_token_created

from .tasks import send_forgot_password_mail


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, *args, **kwargs):
    send_forgot_password_mail.delay(user_id=reset_password_token.user.id, token=reset_password_token.key)
