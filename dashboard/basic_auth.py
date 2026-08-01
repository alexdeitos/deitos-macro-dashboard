import base64
import binascii
import hmac
import os

from django.http import HttpResponse


class DashboardBasicAuthMiddleware:
    """
    Protege o dashboard e as APIs usando usuário e senha
    armazenados nas variáveis de ambiente da Vercel.
    """

    EXEMPT_PATHS = {
        "/health/",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in self.EXEMPT_PATHS:
            return self.get_response(request)

        expected_username = os.getenv("DASHBOARD_USERNAME", "").strip()
        expected_password = os.getenv("DASHBOARD_PASSWORD", "").strip()

        if not expected_username or not expected_password:
            return HttpResponse(
                "Autenticação do dashboard não configurada.",
                status=503,
                content_type="text/plain; charset=utf-8",
            )

        authorization = request.headers.get("Authorization", "")

        if not authorization.startswith("Basic "):
            return self._unauthorized()

        try:
            encoded_credentials = authorization.split(" ", 1)[1]
            decoded_credentials = base64.b64decode(
                encoded_credentials,
                validate=True,
            ).decode("utf-8")

            username, password = decoded_credentials.split(":", 1)

        except (
            ValueError,
            UnicodeDecodeError,
            binascii.Error,
        ):
            return self._unauthorized()

        username_valid = hmac.compare_digest(
            username,
            expected_username,
        )

        password_valid = hmac.compare_digest(
            password,
            expected_password,
        )

        if not username_valid or not password_valid:
            return self._unauthorized()

        return self.get_response(request)

    @staticmethod
    def _unauthorized():
        response = HttpResponse(
            "Autenticação necessária.",
            status=401,
            content_type="text/plain; charset=utf-8",
        )

        response["WWW-Authenticate"] = (
            'Basic realm="Macro Dashboard", charset="UTF-8"'
        )

        response["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, private"
        )

        return response
