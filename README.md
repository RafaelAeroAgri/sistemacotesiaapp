# Sistema Cotesia - Headless

Sistema de liberação de Cotesia para Raspberry Pi 4B sem interface gráfica, controlado remotamente via WiFi através de API HTTP REST.

## Características

- **Operação Headless**: Sem necessidade de tela
- **Controle Remoto**: API HTTP REST completa
- **Offline-First**: Continua operando sem conexão WiFi durante voo
- **Auto-Recovery**: Reconecta GPS automaticamente se desconectar
- **Backup Automático Organizado**: Salva dados por Ano/Mês/Dia com numeração sequencial
- **4 Ciclos de Operação**: Sistema robusto de controle de voo
- **Logs Criptografáveis**: Possibilidade de gerar log protegido por chave simétrica

## Requisitos

- Raspberry Pi 4B (ou superior)
- GPS USB (G-mouse ou similar)
- 2 Servos (conectados aos GPIOs 12 e 16)
- Python 3.7+
- pigpio daemon
- Conexão WiFi (hotspot)

## Instalação

### 1. Copiar arquivos para a Raspberry Pi

```bash
# Na Raspberry Pi
cd ~
git clone <repositorio> sistemacotesia
cd sistemacotesia
```

### 2. Executar instalação

```bash
chmod +x install.sh
sudo ./install.sh
```

O script irá:
- Instalar todas as dependências
- Configurar pigpio daemon
- Criar diretórios necessários
- Instalar e iniciar o serviço systemd

### 3. Verificar instalação

```bash
sudo systemctl status cotesia-http
```

## Configuração WiFi Hotspot

O sistema funciona melhor com um hotspot WiFi na Raspberry Pi com IP fixo `10.3.141.1`.

Recomenda-se usar **RaspAP** para configuração do hotspot:

```bash
curl -sL https://install.raspap.com | bash
```

Configure:
- SSID: `CotesiaPi` (ou o nome que preferir)
- Senha: (defina uma senha)
- IP: `10.3.141.1`

## API HTTP REST

### Conectividade

#### `GET /ping`
Testa conectividade

**Resposta:**
```json
{
  "status": "ok",
  "message": "PONG"
}
```

#### `GET /status`
Retorna status completo do sistema

**Resposta:**
```json
{
  "status": "ok",
  "data": {
    "gps_status": "CONECTADO",
    "num_satelites": 8,
    "coordenadas": "-23.550520, -46.633308",
    "velocidade_ms": 12.5,
    "velocidade_kmh": 45.0,
    "pdop": 2.1,
    "estado_sistema": "OPERANDO",
    "ciclo_atual": 3,
    "distancia_acumulada": 15.3,
    "tempo_parada_atual": 0.0,
    "numero_voo": 1,
    "servos_ativacoes": 23,
    "finalizado": false
  }
}
```

### Configurações

#### `GET /config`
Retorna configurações atuais

#### `POST /config`
Atualiza configurações

**Body:**
```json
{
  "distancia_metros": 30,
  "tempo_parada": 12,
  "velocidade_operacao": 5.5
}
```

### Controles

#### `POST /servo/test`
Executa teste dos servos

#### `POST /servo/reset`
Reseta servos para posição inicial

#### `POST /system/boot`
Inicializa GPIO (se ainda não inicializado)

#### `POST /system/reset`
Reset completo do sistema

#### `POST /flight/start`
Inicia ciclo de voo (requer satélites >= 3)

#### `POST /flight/stop`
Para o voo manualmente

### Dados de Voo

#### `GET /flights/list`
Lista todos os voos salvos

**Resposta:**
```json
{
  "status": "ok",
  "flights": [
    {
      "id": "2025-11-10-VOO0003",
      "numero": 3,
      "numero_diario": 1,
      "ano": 2025,
      "mes": 11,
      "mes_nome": "NOVEMBRO",
      "dia": 10,
      "data": "10/11/2025 14:30:00",
      "tubos": 24,
      "duracao": "12min 10s",
      "tamanho_mb": 1.8,
      "pasta_relativa": "2025/NOVEMBRO/10/VOO_01"
    }
  ]
}
```

#### `GET /flights/{numero}`
Retorna dados completos de um voo (arquivos em base64)

**Resposta:**
```json
{
  "status": "ok",
  "flight": {
    "numero": 1,
    "metadata": {
      "id": "2025-11-10-VOO0003",
      "numero_global": 3,
      "numero_diario": 1,
      "ano": 2025,
      "mes_nome": "NOVEMBRO",
      "dia": 10,
      "data_humana": "10/11/2025 14:30:00",
      "log_encrypted": true,
      "arquivos": {
        "coordenadas": "VOO01.txt",
        "percurso": "PERCURSO01.kml",
        "pontos": "PONTOS01.kml",
        "relatorio": "DADOS01.txt",
        "log": "LOG_COMPLETO.txt.enc"
      }
    },
    "arquivos": {
      "VOO01.txt": "base64...",
      "PERCURSO01.kml": "base64...",
      "PONTOS01.kml": "base64...",
      "DADOS01.txt": "base64...",
      "LOG_COMPLETO.txt.enc": "base64..."
    }
  }
}
```

#### `DELETE /flights/{numero}`
Apaga um voo da Raspberry

## Ciclos de Operação

O sistema opera em 4 ciclos automáticos:

### Ciclo 0: Aguardando GPS
- Aguarda GPS >= 3 satélites
- Aguarda movimento >= 5 m/s
- Ao atingir → Ciclo 1

### Ciclo 1: Primeira Parada
- Aguarda velocidade <= 1.5 m/s
- Ao parar: grava coordenada + aciona servo
- Passa para Ciclo 2

### Ciclo 2: Retomando Voo
- Aguarda velocidade >= 5 m/s
- Sem timeout (pode esperar indefinidamente)
- Ao retomar → Ciclo 3

### Ciclo 3: Operação Normal
- A cada 25m percorridos: grava coordenada + aciona servo
- Se velocidade < 5 m/s por 10s: FINALIZA
- Se velocidade volta a >= 5 m/s: continua operando

## Arquivos e Estrutura de Pastas

Cada voo é salvo em `~/cotesia_backup/ANO/MÊS/DIA/VOO_XX/` contendo:

- `VOOXX.txt`: Coordenadas (lat, lon)
- `PERCURSOXX.kml`: Linha do percurso
- `PONTOSXX.kml`: Pontos individuais
- `DADOSXX.txt`: Relatório completo
- `LOG_COMPLETO.txt` (ou `LOG_COMPLETO.txt.enc` quando criptografado)
- `metadata.json`: Metadados completos do voo (campos usados pela API)

Exemplo:

```
cotesia_backup/
 └── 2025/
     └── NOVEMBRO/
         └── 10/
             └── VOO_01/
                 ├── VOO01.txt
                 ├── PERCURSO01.kml
                 ├── PONTOS01.kml
                 ├── DADOS01.txt
                 ├── LOG_COMPLETO.txt.enc
                 └── metadata.json
```

### Criptografia de Logs

- O log é criptografado automaticamente se existir a chave `~/.cotesia_log.key`.
- Para gerar a chave:

```bash
python3 - <<'PY'
from cryptography.fernet import Fernet
key = Fernet.generate_key()
open('/home/$USER/.cotesia_log.key', 'wb').write(key)
print('Chave salva em ~/.cotesia_log.key')
PY
```

- Para descriptografar um log:

```bash
python3 tools/decrypt_log.py LOG_COMPLETO.txt.enc ~/.cotesia_log.key LOG_SAIDA.txt
```

- Se a biblioteca `cryptography` não estiver instalada ou a chave não existir, o log permanecerá em texto puro.
- É possível definir outro caminho de chave adicionando `log_key_path: /caminho/para/chave.key` no `config.yaml`.

## Comandos Úteis

```bash
# Ver status do serviço
sudo systemctl status cotesia-http

# Ver logs em tempo real
sudo journalctl -u cotesia-http -f

# Parar serviço
sudo systemctl stop cotesia-http

# Iniciar serviço
sudo systemctl start cotesia-http

# Reiniciar serviço
sudo systemctl restart cotesia-http

# Ver logs do sistema
tail -f ~/cotesia_logs/cotesia_*.log

# Listar voos salvos
ls -la ~/cotesia_backup/
```

## Estrutura de Arquivos

```
sistemacotesia/
├── service/
│   ├── http_server.py      # Servidor HTTP principal
│   ├── gps_control.py      # Controle GPS e ciclos
│   ├── servo_control.py    # Controle servos
│   └── logger.py           # Sistema de logging
├── systemd/
│   └── cotesia-http.service
├── config.yaml
├── install.sh
└── README.md
```

## Troubleshooting

### GPS não conecta

```bash
# Verifica portas disponíveis
ls /dev/tty*

# Verifica se GPS está sendo detectado
dmesg | grep tty
```

### Servos não respondem

```bash
# Verifica se pigpio está rodando
sudo systemctl status pigpiod

# Reinicia pigpio
sudo systemctl restart pigpiod
```

### Servidor HTTP não inicia

```bash
# Verifica logs
sudo journalctl -u cotesia-http -n 50

# Testa manualmente
cd ~/sistemacotesia/service
python3 http_server.py
```

## Suporte

Para mais informações ou suporte, consulte a documentação completa ou entre em contato com a equipe da Aeroagri.

