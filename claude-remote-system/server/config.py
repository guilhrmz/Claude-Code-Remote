"""
Configurações do servidor.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class ServerSettings(BaseSettings):
    """Configurações do servidor carregadas do ambiente."""

    # Server
    host: str = Field(default="0.0.0.0", description="Host para escutar")
    port: int = Field(default=8765, description="Porta do servidor WebSocket")

    # WebSocket
    max_message_size: int = Field(default=10 * 1024 * 1024, description="Max mensagem (10MB)")
    ping_timeout: int = Field(default=30, description="Timeout do ping")
    ping_interval: int = Field(default=30, description="Intervalo do ping")

    # Autenticação
    auth_enabled: bool = Field(default=True, description="Habilitar autenticação")
    secret_key: str = Field(default="change-me-in-production", description="Chave secreta JWT")
    token_expire_hours: int = Field(default=24, description="Expiração do token (horas)")

    # Clientes autorizados (cliente_id:secret_key)
    authorized_clients: dict = Field(
        default={"default_client": "default_secret"},
        description="Clientes autorizados"
    )

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434", description="URL do Ollama")
    ollama_model: str = Field(default="llama3.2", description="Modelo do Ollama")
    ollama_timeout: int = Field(default=120, description="Timeout Ollama (segundos)")

    # Sessions
    max_concurrent_sessions: int = Field(default=10, description="Max sessões simultâneas")
    session_timeout_minutes: int = Field(default=60, description="Timeout da sessão (min)")
    heartbeat_interval: int = Field(default=30, description="Intervalo heartbeat (seg)")

    # Segurança
    allowed_origins: list = Field(
        default=["*"],
        description="Origins CORS permitidos"
    )
    rate_limit_per_minute: int = Field(default=100, description="Rate limit por minuto")

    # SSL/TLS
    ssl_enabled: bool = Field(default=False, description="Habilitar SSL")
    ssl_cert_path: Optional[str] = Field(default=None, description="Caminho cert SSL")
    ssl_key_path: Optional[str] = Field(default=None, description="Caminho chave SSL")

    # Logging
    log_level: str = Field(default="INFO", description="Nível de log")
    log_file: Optional[str] = Field(default="server.log", description="Arquivo de log")

    # Working directory (onde o Claude Code opera)
    work_dir: str = Field(default="/tmp/claude-remote-work", description="Diretório de trabalho")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Instância global das configurações
settings = ServerSettings()
