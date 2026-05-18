"""
Custom email backend that bypasses SSL certificate verification for local testing.
WARNING: Only use this for local development. Never use in production!
"""
import ssl
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend


class NoSSLVerificationEmailBackend(SMTPEmailBackend):
    """
    SMTP backend that disables SSL certificate verification.
    Use only for local development/testing.
    """
    def open(self):
        """
        Attempt to open a connection to the mail server.
        Override to use unverified SSL context.
        """
        if self.use_tls:
            # Create an unverified SSL context for development
            self.ssl_context = ssl._create_unverified_context()
        
        return super().open()
