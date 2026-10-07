import os
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class VirungaJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, os.getenv("JWT_SECRET", settings.SECRET_KEY), algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed("JWT invalide ou expiré.") from exc
        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(username=payload.get("sub", "virunga-user"))
        user.is_staff = payload.get("domain_role") == "administrateur"
        return user, token
