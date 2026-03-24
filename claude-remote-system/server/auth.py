"""
Autenticação e autorização do servidor.
"""

import jwt
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from server.config import settings


class AuthenticationError(Exception):
    """Erro de autenticação."""
    pass


class AuthManager:
    """Gerenciador de autenticação."""

    def __init__(self):
        self.secret_key = settings.secret_key
        self.algorithm = "HS256"
        self.authorized_clients = settings.authorized_clients
        self.active_tokens: dict[str, datetime] = {}  # token -> expiry

    def verify_client(self, client_id: str, secret_key: str) -> bool:
        """Verifica se o cliente está autorizado."""
        if client_id in self.authorized_clients:
            return self.authorized_clients[client_id] == secret_key
        return False

    def generate_token(self, client_id: str) -> str:
        """Gera token JWT para o cliente."""
        expiry = datetime.utcnow() + timedelta(hours=settings.token_expire_hours)
        payload = {
            "client_id": client_id,
            "exp": expiry,
            "iat": datetime.utcnow(),
            "type": "access"
        }
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        self.active_tokens[token] = expiry
        return token

    def verify_token(self, token: str) -> Optional[str]:
        """Verifica token JWT e retorna client_id se válido."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            client_id = payload.get("client_id")
            if client_id and token in self.active_tokens:
                expiry = self.active_tokens[token]
                if datetime.utcnow() < expiry:
                    return client_id
                else:
                    del self.active_tokens[token]
        except jwt.ExpiredSignatureError:
            self.active_tokens.pop(token, None)
        except jwt.InvalidTokenError:
            pass
        return None

    def revoke_token(self, token: str) -> bool:
        """Revoga um token."""
        if token in self.active_tokens:
            del self.active_tokens[token]
            return True
        return False

    def hash_secret(self, secret: str) -> str:
        """Hash da secret key para comparação segura."""
        return hashlib.sha256(secret.encode()).hexdigest()

    def get_client_info(self, client_id: str) -> Optional[dict]:
        """Obtém informações do cliente."""
        if client_id in self.authorized_clients:
            return {"client_id": client_id, "authorized": True}
        return None


# Instância global
auth_manager = AuthManager()
