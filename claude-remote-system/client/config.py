"""
Configurações do cliente.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field


class ClientSettings(BaseSettings):
    """Configurações do cliente carregadas do ambiente."""

    # Server
    server_url: str = Field(
        default="ws://localhost:8765",
        description="URL do servidor WebSocket"
    )

    # Autenticação
    client_id: str = Field(
        default="default_client",
        description="ID do cliente"
    )
    secret_key: str = Field(
        default="default_secret",
        description="Chave secreta do cliente"
    )

    # Reconexão
    reconnect_attempts: int = Field(
        default=5,
        description="Tentativas de reconexão"
    )
    reconnect_delay: int = Field(
        default=5,
        description="Delay entre reconexões (segundos)"
    )
    reconnect_backoff: float = Field(
        default=1.5,
        description="Fator de backoff exponencial"
    )

    # WebSocket
    ping_interval: int = Field(
        default=30,
        description="Intervalo do ping (segundos)"
    )
    ping_timeout: int = Field(
        default=10,
        description="Timeout do ping (segundos)"
    )

    # Session
    session_timeout: int = Field(
        default=3600,
        description="Timeout da sessão (segundos)"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Nível de log"
    )
    log_file: str = Field(
        default="client.log",
        description="Arquivo de log"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Instância global
settings = ClientSettings()
