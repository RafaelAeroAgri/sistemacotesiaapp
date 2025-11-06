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
apt install -y python3-pip python3-serial python3-gpiozero git build-essential python3-setuptools

echo ""
echo "📦 Instalando bibliotecas Python via pip..."
pip3 install pynmea2 pytz simplekml --break-system-packages

echo ""
echo "🔧 Instalando pigpio do source..."
cd /tmp
rm -rf pigpio
git clone https://github.com/joan2937/pigpio.git
cd pigpio

# Compila e instala apenas os binários (sem Python)
make
make install EXCLUDELIB=y

# Instala biblioteca Python do pigpio via pip
pip3 install pigpio --break-system-packages

cd ~

echo ""
echo "🔧 Configurando pigpio daemon..."

# Cria serviço systemd se não existir
if [ ! -f /etc/systemd/system/pigpiod.service ]; then
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
fi

systemctl daemon-reload
systemctl enable pigpiod
systemctl start pigpiod

echo ""
echo "📁 Criando diretórios..."
USUARIO=$(logname)
mkdir -p /home/$USUARIO/cotesia_backup
mkdir -p /home/$USUARIO/cotesia_logs
chown -R $USUARIO:$USUARIO /home/$USUARIO/cotesia_backup
chown -R $USUARIO:$USUARIO /home/$USUARIO/cotesia_logs

echo ""
echo "🔧 Instalando serviço systemd..."
# Detecta o caminho real do script
SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
SISTEMA_PATH="$(dirname "$SCRIPT_PATH")"

echo "   Diretório do sistema: $SISTEMA_PATH"

if [ ! -f "$SISTEMA_PATH/systemd/cotesia-http.service" ]; then
    echo "❌ Erro: Arquivo systemd/cotesia-http.service não encontrado!"
    echo "   Procurado em: $SISTEMA_PATH/systemd/cotesia-http.service"
    ls -la "$SISTEMA_PATH/" 2>/dev/null || echo "   (Diretório não existe)"
    exit 1
fi

cp "$SISTEMA_PATH/systemd/cotesia-http.service" /etc/systemd/system/

# Substitui [USER] pelo usuário atual e o caminho
sed -i "s/\[USER\]/$USUARIO/g" /etc/systemd/system/cotesia-http.service
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
echo "🔍 Verificando status dos serviços..."
sleep 2
echo ""
echo "--- PIGPIO DAEMON ---"
systemctl status pigpiod --no-pager | head -n 10
echo ""
echo "--- COTESIA HTTP ---"
systemctl status cotesia-http --no-pager | head -n 10
echo ""
echo "✅ Se aparecer 'active (running)' acima, está tudo OK!"
