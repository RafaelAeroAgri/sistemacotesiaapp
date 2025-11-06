# Instalação Manual do Sistema Cotesia

Caso o script automático `install.sh` não funcione, siga este guia passo a passo.

## 1. Instalar Dependências do Sistema

```bash
sudo apt update
sudo apt install -y python3-pip python3-serial python3-gpiozero git build-essential
```

## 2. Instalar pigpio (Controle PWM)

### Opção A: Compilar do Source (Recomendado)

```bash
cd /tmp
git clone https://github.com/joan2937/pigpio.git
cd pigpio
make
sudo make install
```

### Opção B: Tentar repositório (pode não funcionar em Trixie)

```bash
sudo apt install -y pigpio python3-pigpio
```

## 3. Configurar pigpio daemon

```bash
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
sudo systemctl status pigpiod
```

Se o serviço não existir, crie manualmente:

```bash
sudo tee /etc/systemd/system/pigpiod.service > /dev/null <<'EOF'
[Unit]
Description=Daemon required to control GPIO pins via pigpio
[Service]
ExecStart=/usr/local/bin/pigpiod -l
ExecStop=/bin/systemctl kill pigpiod
Type=forking
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

## 4. Instalar Bibliotecas Python

```bash
pip3 install pynmea2 pytz simplekml --break-system-packages
```

**Nota:** A flag `--break-system-packages` é necessária no Debian 12+ (Bookworm/Trixie)

## 5. Criar Diretórios

```bash
mkdir -p ~/cotesia_backup
mkdir -p ~/cotesia_logs
```

## 6. Instalar Serviço HTTP

```bash
cd ~/sistemacotesia

# Copiar serviço
sudo cp systemd/cotesia-http.service /etc/systemd/system/

# Editar para ajustar caminhos
sudo nano /etc/systemd/system/cotesia-http.service
```

**Ajuste as linhas:**
- `User=aeroagri` (seu usuário)
- `Group=aeroagri` (seu grupo)
- `WorkingDirectory=/home/aeroagri/sistemacotesia/service`
- `ExecStart=/usr/bin/python3 /home/aeroagri/sistemacotesia/service/http_server.py`

Salve: `Ctrl+O`, Enter, `Ctrl+X`

## 7. Ativar e Iniciar Serviço

```bash
sudo systemctl daemon-reload
sudo systemctl enable cotesia-http
sudo systemctl start cotesia-http
```

## 8. Verificar Status

```bash
sudo systemctl status cotesia-http
```

Deve aparecer **"active (running)"**

Ver logs:
```bash
sudo journalctl -u cotesia-http -f
```

## 9. Testar API

```bash
# Teste local
curl http://localhost:8080/ping

# Teste status
curl http://localhost:8080/status
```

---

## 🔧 Troubleshooting

### pigpio não compila

Se der erro ao compilar pigpio:

```bash
# Instalar mais dependências
sudo apt install -y gcc make libc6-dev

# Tentar novamente
cd /tmp/pigpio
make clean
make
sudo make install
```

### Python não encontra módulos

```bash
# Reinstalar com pip3
pip3 install --upgrade pynmea2 pytz simplekml --break-system-packages

# Verificar instalação
python3 -c "import pynmea2, pytz, simplekml; print('OK')"
```

### Serviço não inicia

```bash
# Ver erro detalhado
sudo journalctl -u cotesia-http -n 50

# Testar manualmente
cd ~/sistemacotesia/service
python3 http_server.py
```

Se aparecer erro de importação, instale o módulo faltante:
```bash
pip3 install <modulo> --break-system-packages
```

### GPS não detectado

```bash
# Verificar portas USB
ls /dev/ttyUSB* /dev/ttyACM*

# Ver dispositivos conectados
dmesg | grep -i tty

# Dar permissão ao usuário
sudo usermod -a -G dialout $USER
sudo reboot
```

---

## 🌐 Configurar IP Fixo (Hotspot)

Se usar RaspAP, configure:

1. Acesse: `http://raspberrypi.local`
2. Login: `admin` / `secret`
3. **Hotspot** → Basic:
   - SSID: `CotesiaPi`
   - Senha: `cotesia2025`
   - Channel: 6
4. **DHCP Server** → Interface `uap0`:
   - Router IP: `10.3.141.1`
   - Starting IP: `10.3.141.50`
   - Ending IP: `10.3.141.254`
5. **System** → Reboot

---

## ✅ Checklist Final

- [ ] pigpio instalado e rodando
- [ ] Bibliotecas Python instaladas
- [ ] Serviço cotesia-http rodando
- [ ] API responde em http://localhost:8080/ping
- [ ] Hotspot WiFi configurado com IP 10.3.141.1
- [ ] GPS conectado e detectado
- [ ] Servos conectados aos GPIOs 12 e 16

---

Pronto! Sistema instalado e funcionando! 🎉

