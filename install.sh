#!/bin/bash
# Script de instalação do Sistema Cotesia na Raspberry Pi

set -e  # Para em caso de erro

echo "========================================="
echo "  Instalação Sistema Cotesia"
echo "========================================="
echo ""

# Verifica se está rodando como root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Este script precisa ser executado como root"
    echo "Use: sudo ./install.sh"
    exit 1
fi

echo "📦 Atualizando sistema..."
apt update

echo ""
echo "📦 Instalando dependências Python..."
apt install -y python3-pip python3-serial python3-gpiozero pigpio python3-pigpio

echo ""
echo "📦 Instalando bibliotecas Python via pip..."
pip3 install pynmea2 pytz simplekml

echo ""
echo "🔧 Configurando pigpio daemon..."
systemctl enable pigpiod
systemctl start pigpiod

echo ""
echo "📁 Criando diretórios..."
mkdir -p /home/$(logname)/cotesia_backup
mkdir -p /home/$(logname)/cotesia_logs
chown -R $(logname):$(logname) /home/$(logname)/cotesia_backup
chown -R $(logname):$(logname) /home/$(logname)/cotesia_logs

echo ""
echo "🔧 Instalando serviço systemd..."
cp systemd/cotesia-http.service /etc/systemd/system/

# Substitui [USER] pelo usuário atual
sed -i "s/\[USER\]/$(logname)/g" /etc/systemd/system/cotesia-http.service

systemctl daemon-reload
systemctl enable cotesia-http
systemctl start cotesia-http

echo ""
echo "✅ Instalação concluída!"
echo ""
echo "========================================="
echo "  Comandos Úteis"
echo "========================================="
echo ""
echo "Ver status:    sudo systemctl status cotesia-http"
echo "Ver logs:      sudo journalctl -u cotesia-http -f"
echo "Parar:         sudo systemctl stop cotesia-http"
echo "Iniciar:       sudo systemctl start cotesia-http"
echo "Reiniciar:     sudo systemctl restart cotesia-http"
echo ""
echo "Servidor HTTP disponível em: http://10.3.141.1:8080"
echo "(Configure o hotspot WiFi com IP 10.3.141.1)"
echo ""

