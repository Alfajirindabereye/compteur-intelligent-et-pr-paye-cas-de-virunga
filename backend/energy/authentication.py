import os
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


def jwt_secret() -> str:
    return os.getenv("JWT_SECRET") or settings.SECRET_KEY


class VirungaJWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        # Sans cet en-tête, DRF répond 403 à un jeton expiré : le client ne saurait pas
        # distinguer « session à renouveler » (401) de « accès interdit » (403).
        return 'Bearer realm="api"'

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"], options={"require": ["exp", "sub"]})
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed("JWT invalide ou expiré.") from exc
        # Un refresh token (7 jours) ne sert qu'à /api/auth/token/refresh/ : il ne
        # doit jamais ouvrir l'API à la place d'un access token.
        if payload.get("typ") == "refresh":
            raise AuthenticationFailed("Un refresh token ne peut pas servir de jeton d'accès.")
        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(username=payload["sub"])
        if not user.is_active:
            raise AuthenticationFailed("Compte désactivé.")
        # Administrateur seulement si le compte Django l'est ET que le jeton a été émis
        # par la connexion administrateur : le rôle du jeton seul ne suffit pas.
        user.is_staff = user.is_staff and payload.get("domain_role") == "administrateur"
        return user, token
