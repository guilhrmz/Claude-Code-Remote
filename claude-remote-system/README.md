# Claude Remote System

Sistema de comunicação remota para Claude Code via Ollama, permitindo que máquinas clientes enviem comandos e mensagens para um servidor que executa o Claude Code localmente.

## Arquitetura

```
┌─────────────────┐         WebSocket (ws:// ou wss://)         ┌─────────────────┐
│   PC Cliente    │◄───────────────────────────────────────────►│   PC Servidor   │
│   (Remote API)  │              Internet / LAN                 │  (Ollama + CC)  │
└─────────────────┘                                             └─────────────────┘
                                                                       │
                                                                       ▼
                                                            ┌─────────────────────┐
                                                            │  Claude Code Local  │
                                                            │  + Ollama (LLM)     │
                                                            └─────────────────────┘
```

## Funcionalidades

- ✅ **Comunicação em tempo real** via WebSocket
- ✅ **Autenticação com JWT** para segurança básica
- ✅ **Sessão stateful** mantida com o Claude
- ✅ **Execução de comandos shell** remoatos
- ✅ **Leitura/escrita de arquivos** no servidor
- ✅ **Listagem de diretórios** remota
- ✅ **Reconexão automática** com backoff exponencial
- ✅ **Keep-alive** para manter conexão ativa
- ✅ **Tratamento de erros** e reconexão

## Estrutura

```
claude-remote-system/
├── server/
│   ├── main.py              # Servidor WebSocket + API
│   ├── claude_handler.py    # Integração com Claude Code/Ollama
│   ├── auth.py              # Autenticação e segurança
│   └── config.py            # Configurações
├── client/
│   ├── main.py              # Cliente CLI remoto
│   ├── ws_client.py         # Cliente WebSocket
│   └── config.py            # Configurações
├── shared/
│   ├── protocol.py          # Protocolo de mensagens
│   └── models.py            # Modelos de dados
├── requirements.txt
├── .env.example
└── README.md
```

## Instalação

### 1. Clone/Download

```bash
cd claude-remote-system
```

### 2. Instale dependências

```bash
pip install -r requirements.txt
```

### 3. Configure o ambiente

```bash
cp .env.example .env
# Edite .env com suas configurações
```

## Configuração do Servidor

### Pré-requisitos

1. **Ollama instalado e rodando** no servidor:
   ```bash
   # Instalar Ollama (Linux/Mac)
   curl -fsSL https://ollama.com/install.sh | sh

   # Pull de um modelo
   ollama pull llama3.2
   ```

2. **Configurar `.env`** no servidor:
   ```ini
   SERVER_HOST=0.0.0.0
   SERVER_PORT=8765
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.2
   SECRET_KEY=change-me-in-production
   WORK_DIR=/path/to/working/dir
   ```

### Rodando o Servidor

```bash
# No PC servidor
python -m server.main
```

Ou com uvicorn direto:

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8765
```

## Configuração do Cliente

### Configurar `.env`** no cliente:
   ```ini
   SERVER_URL=ws://<IP_DO_SERVIDOR>:8765
   CLIENT_ID=default_client
   SECRET_KEY=default_secret
   ```

### Rodando o Cliente

```bash
# No PC cliente

# Modo interativo
python -m client.main --interactive

# One-shot commands
python -m client.main --action chat --arg "Hello, Claude!"
python -m client.main --action cmd --arg "ls -la"
python -m client.main --action cat --arg "/path/to/file.txt"
python -m client.main --action ls --arg "/path/to/dir"
```

## Protocolo de Mensagens

### Tipos de Mensagem

| Tipo | Descrição | Direção |
|------|-----------|---------|
| `auth_request` | Autenticação | Cliente → Servidor |
| `auth_response` | Resposta auth | Servidor → Cliente |
| `chat_message` | Mensagem para Claude | Cliente → Servidor |
| `chat_response` | Resposta do Claude | Servidor → Cliente |
| `command` | Executar comando shell | Cliente → Servidor |
| `command_output` | Output do comando | Servidor → Cliente |
| `file_read` | Ler arquivo | Cliente → Servidor |
| `file_content` | Conteúdo do arquivo | Servidor → Cliente |
| `file_write` | Escrever arquivo | Cliente → Servidor |
| `file_created` | Confirmação escrita | Servidor → Cliente |
| `file_list` | Listar diretório | Cliente → Servidor |
| `directory_listing` | Listagem de diretório | Servidor → Cliente |
| `keepalive` | Manter conexão | Cliente → Servidor |
| `keepalive_ack` | Ack do keepalive | Servidor → Cliente |
| `session_end` | Finalizar sessão | Cliente → Servidor |
| `error` | Erro | Servidor → Cliente |
| `status` | Status do servidor | Ambos |

### Exemplo de Mensagem

```json
{
    "id": "uuid-gerado-automaticamente",
    "type": "chat_message",
    "content": "Hello, Claude!",
    "session_id": "session_123456",
    "timestamp": "2024-01-01T00:00:00Z"
}
```

## Uso em Rede Local (LAN)

### Configuração

1. **No servidor** (`.env`):
   ```ini
   SERVER_HOST=0.0.0.0
   SERVER_PORT=8765
   ```

2. **Descobrir IP do servidor**:
   ```bash
   # Linux
   ip addr show
   # ou
   hostname -I

   # Windows
   ipconfig
   ```

3. **No cliente** (`.env`):
   ```ini
   SERVER_URL=ws://192.168.1.100:8765
   ```

4. **Firewall**: Permitir porta 8765:
   ```bash
   # Linux (ufw)
   sudo ufw allow 8765/tcp

   # Windows (PowerShell Admin)
   New-NetFirewallRule -DisplayName "Claude Remote" -Direction Inbound -LocalPort 8765 -Protocol TCP -Action Allow
   ```

## Uso pela Internet

### Opção 1: Port Forwarding (NAT)

1. **Configurar roteador**: Encaminhar porta externa → IP interno:8765
2. **No cliente**: Usar IP público do servidor
3. **Cuidado**: Expõe servidor diretamente à internet

### Opção 2: SSH Tunnel (Recomendado para teste)

```bash
# No cliente, criar túnel SSH
ssh -L 8765:localhost:8765 user@server-ip

# Conectar localmente
SERVER_URL=ws://localhost:8765
```

### Opção 3: ngrok (Testes rápidos)

```bash
# No servidor
ngrok http 8765

# Usar URL gerada (com wss://)
SERVER_URL=wss://xxxx.ngrok.io
```

### Opção 4: SSL/TLS (Produção)

1. Gerar certificado:
   ```bash
   openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365
   ```

2. Configurar `.env`:
   ```ini
   SSL_ENABLED=true
   SSL_CERT_PATH=/path/to/cert.pem
   SSL_KEY_PATH=/path/to/key.pem
   ```

3. Rodar com SSL:
   ```bash
   uvicorn server.main:app \
     --host 0.0.0.0 --port 8765 \
     --ssl-keyfile=key.pem --ssl-certfile=cert.pem
   ```

4. Cliente usa `wss://`:
   ```ini
   SERVER_URL=wss://server-ip:8765
   ```

## Exemplo de Uso Programático

### Cliente Python

```python
import asyncio
from client.ws_client import RemoteClient

async def main():
    client = RemoteClient(
        server_url="ws://192.168.1.100:8765",
        client_id="my_client",
        secret_key="my_secret"
    )

    # Callbacks
    client.on_connect(lambda: print("Connected!"))
    client.on_disconnect(lambda: print("Disconnected"))

    # Conectar
    connect_task = asyncio.create_task(client.connect())
    await asyncio.sleep(2)

    if client.is_authenticated:
        # Chat
        response = await client.send_chat("Create a Python file with hello world")
        print(response.content)

        # Comando
        result = await client.run_command("ls -la")
        print(result.stdout)

        # Ler arquivo
        file_content = await client.read_file("hello.py")
        print(file_content.content)

        # Escrever arquivo
        await client.write_file("test.txt", "Hello from remote!")

    await client.disconnect()

asyncio.run(main())
```

## Segurança

### Recomendações para Produção

1. **Mudar SECRET_KEY** no `.env`
2. **Usar SSL/TLS** (wss://)
3. **Configurar clientes autorizados** explicitamente
4. **Rate limiting** habilitado
5. **Firewall** configurado
6. **Work directory** com permissões restritas
7. **Logs** habilitados para auditoria

### Adicionar Novo Cliente

No `.env` do servidor:

```ini
AUTHORIZED_CLIENT_cliente1=senha123
AUTHORIZED_CLIENT_cliente2=outra_senha
```

No `.env` do cliente:

```ini
CLIENT_ID=cliente1
SECRET_KEY=senha123
```

## Troubleshooting

### Servidor não inicia

```bash
# Verificar Ollama
ollama list
curl http://localhost:11434/api/tags

# Verificar porta
netstat -tlnp | grep 8765
```

### Cliente não conecta

```bash
# Testar conectividade
ping server-ip
telnet server-ip 8765
# ou
nc -zv server-ip 8765
```

### Autenticação falha

- Verificar `CLIENT_ID` e `SECRET_KEY` correspondem ao servidor
- Verificar `.env` carregado corretamente

### Ollama timeout

- Aumentar `OLLAMA_TIMEOUT` no `.env`
- Verificar modelo disponível: `ollama list`

## API REST

O servidor também expõe endpoints HTTP:

- `GET /health` - Health check
- `GET /status` - Status do servidor

```bash
curl http://localhost:8765/health
curl http://localhost:8765/status
```

## License

MIT
