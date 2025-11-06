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
echo "📦 Instalando dependências do sistema..."
apt install -y python3-pip python3-serial python3-gpiozero git build-essential

echo ""
echo "📦 Instalando bibliotecas Python via pip..."
pip3 install pynmea2 pytz simplekml --break-system-packages

echo ""
echo "🔧 Instalando pigpio do source..."
cd /tmp
rm -rf pigpio
git clone https://github.com/joan2937/pigpio.git
cd pigpio
make
make install
cd ~

echo ""
echo "🔧 Configurando pigpio daemon..."
systemctl enable pigpiod 2>/dev/null || true
systemctl start pigpiod 2>/dev/null || true

# Se o serviço systemd não existir, cria um
if [ ! -f /etc/systemd/system/pigpiod.service ]; then
    echo "Criando serviço pigpiod..."
    cat > /etc/systemd/system/pigpiod.service << 'EOF'
[Unit]
Description=Daemon required to control GPIO pins via pigpio
[Service]
ExecStart=/usr/local/bin/pigpiod -l
ExecStop=/bin/systemctl kill pigpiod
Type=forking
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable pigpiod
    systemctl start pigpiod
fi

echo ""
echo "📁 Criando diretórios..."
USUARIO=$(logname)
mkdir -p /home/$USUARIO/cotesia_backup
mkdir -p /home/$USUARIO/cotesia_logs
chown -R $USUARIO:$USUARIO /home/$USUARIO/cotesia_backup
chown -R $USUARIO:$USUARIO /home/$USUARIO/cotesia_logs

echo ""
echo "🔧 Instalando serviço systemd..."
cp systemd/cotesia-http.service /etc/systemd/system/

# Substitui [USER] pelo usuário atual
sed -i "s/\[USER\]/$USUARIO/g" /etc/systemd/system/cotesia-http.service

# Obtém o caminho atual do sistemacotesia
SISTEMA_PATH=$(pwd)
sed -i "s|/home/\[USER\]/sistemacotesia|$SISTEMA_PATH|g" /etc/systemd/system/cotesia-http.service

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
echo "🔍 Verificando status do serviço..."
sleep 2
systemctl status cotesia-http --no-pager
echo ""
echo "✅ Se aparecer 'active (running)' acima, está tudo OK!"
