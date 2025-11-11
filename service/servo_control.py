#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de controle de servos para o Sistema Cotesia
Controla 2 servos espelhados usando gpiozero com pigpio
"""

import time
import os
import json
from gpiozero import Servo
from gpiozero.pins.pigpio import PiGPIOFactory


class ServoControl:
    """Controla os servos do sistema Cotesia"""
    
    def __init__(self, logger=None):
        """
        Inicializa o controle de servos
        
        Args:
            logger: Objeto logger (opcional)
        """
        self.logger = logger
        self.servo1 = None
        self.servo2 = None
        self.estado = "OFF"
        self.contador_ativacoes = 0
        self.ultimo_movimento = 0
        self.tempo_minimo_entre_movimentos = 0.5  # segundos
        self.inicializado = False
        self.angulo_servo1 = -1.0
        self.angulo_servo2 = -1.0

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.calibration_file = os.path.join(base_dir, 'servo_calibration.json')
        self.calibration = {
            'servo1': {'min': -1.0, 'max': 1.0},
            'servo2': {'min': -1.0, 'max': 1.0},
        }
        self._load_calibration()
        self.angulo_servo1 = self.calibration['servo1']['min']
        self.angulo_servo2 = self.calibration['servo2']['min']
        
        self._log("ServoControl inicializado (servos não configurados)")
    
    def _log(self, mensagem, level="info"):
        """Log interno com fallback para print"""
        if self.logger:
            getattr(self.logger, level)(mensagem)
        else:
            print(f"[SERVO] {mensagem}")
    
    def inicializar_gpio(self, calibrar=True):
        """
        Inicializa GPIO e configura os servos
        
        Returns:
            bool: True se inicializado com sucesso
        """
        if self.inicializado:
            self._log("GPIO já inicializado")
            return True
        
        try:
            # Inicia daemon pigpio
            self._log("Iniciando daemon pigpio...")
            os.system('sudo pigpiod 2>/dev/null')
            time.sleep(2)  # Aguarda daemon inicializar
            
            # Cria factory do pigpio
            factory = PiGPIOFactory()
            self._log("Factory pigpio criada")
            
            # SERVO 1: GPIO 16 (pino físico 36)
            self.servo1 = Servo(
                16,
                pin_factory=factory,
                min_pulse_width=1.32 / 1000,   # 1320µs (posição inicial)
                max_pulse_width=2.0 / 1000,    # 2000µs (posição final)
                frame_width=20 / 1000
            )
            self._log("Servo1 (GPIO16/pino 36) criado")
            
            # SERVO 2: GPIO 12 (pino físico 32)
            self.servo2 = Servo(
                12,
                pin_factory=factory,
                min_pulse_width=1.076 / 1000,  # 1076µs (posição final espelhada)
                max_pulse_width=1.73 / 1000,   # 1730µs (posição inicial espelhada)
                frame_width=20 / 1000
            )
            self._log("Servo2 (GPIO12/pino 32) criado")
            
            if calibrar:
                # Calibração inicial com movimento
                self._log("Calibrando posição inicial dos servos...")
                
                # Pequeno movimento de calibração
                self.servo1.value = 0.00
                self.servo2.value = 0.00
                time.sleep(0.3)
                
                # Posição inicial espelhada
                self.servo1.value = self.calibration['servo1']['min']
                self.servo2.value = self.calibration['servo2']['min']
                time.sleep(0.5)
            else:
                # Inicialização silenciosa (sem movimentar)
                self._log("Servos inicializados sem movimento (boot automático)")
                self.servo1.value = self.calibration['servo1']['min']
                self.servo2.value = self.calibration['servo2']['min']
            
            # Desliga PWM
            self.servo1.detach()
            self.servo2.detach()
            
            self.inicializado = True
            self.angulo_servo1 = self.calibration['servo1']['min']
            self.angulo_servo2 = self.calibration['servo2']['min']
            self._log("✅ Servos inicializados e calibrados")
            return True
            
        except Exception as e:
            self._log(f"❌ Erro ao configurar servos: {e}", "error")
            self._log("⚠️ Sistema continuará sem controle de servos", "warning")
            return False
    
    def inicializar_gpio_silencioso(self):
        """Inicializa GPIO sem movimentar os servos (modo boot automático)"""
        return self.inicializar_gpio(calibrar=False)
    
    def medir_calibracao(self):
        """
        Executa uma demonstração dos limites atuais e retorna a calibração.
        Usado para enviar ao aplicativo os valores realmente configurados.
        """
        if not self.inicializado:
            self.inicializar_gpio(calibrar=False)
        
        try:
            self.estado = "ON"
            self._log("Iniciando medição de calibração dos servos")
            
            # Vai ao mínimo atual
            self.servo1.value = self.calibration['servo1']['min']
            self.servo2.value = self.calibration['servo2']['min']
            time.sleep(0.4)
            
            # Vai ao máximo atual
            self.servo1.value = self.calibration['servo1']['max']
            self.servo2.value = self.calibration['servo2']['max']
            time.sleep(0.4)
            
            # Retorna ao mínimo
            self.servo1.value = self.calibration['servo1']['min']
            self.servo2.value = self.calibration['servo2']['min']
            time.sleep(0.3)
            
            return self.calibration
        except Exception as e:
            self._log(f"Erro durante medição de calibração: {e}", "error")
            return self.calibration
        finally:
            self._tentar_detach()
            self.estado = "OFF"
    
    def teste(self):
        """
        Executa movimento de teste dos servos
        
        Returns:
            bool: True se teste executado com sucesso
        """
        if not self._validar_servos():
            return False
        
        if self.estado == "ON":
            self._log("Teste ignorado - servos ocupados")
            return False
        
        try:
            self.estado = "ON"
            self._log("Iniciando teste ESPELHADO dos servos")
            
            # Posição inicial espelhada
            self._log("Posição inicial: S1=1320µs / S2=1076µs")
            self.servo1.value = self.calibration['servo1']['min']
            self.servo2.value = self.calibration['servo2']['min']
            self.angulo_servo1 = self.calibration['servo1']['min']
            self.angulo_servo2 = self.calibration['servo2']['min']
            time.sleep(1.0)
            
            # Movimento 1 - Espelhado
            self._log("Movimento 1: S1 vai (1320→2000) / S2 volta (1076→1730)")
            self.servo1.value = self.calibration['servo1']['max']
            self.servo2.value = self.calibration['servo2']['max']
            self.angulo_servo1 = self.calibration['servo1']['max']
            self.angulo_servo2 = self.calibration['servo2']['max']
            time.sleep(2.0)
            
            # Movimento 2 - Espelhado
            self._log("Movimento 2: S1 volta (2000→1320) / S2 vai (1730→1076)")
            self.servo1.value = self.calibration['servo1']['min']
            self.servo2.value = self.calibration['servo2']['min']
            self.angulo_servo1 = self.calibration['servo1']['min']
            self.angulo_servo2 = self.calibration['servo2']['min']
            time.sleep(2.0)
            
            # Desativa servos
            self.servo1.detach()
            self.servo2.detach()
            
            self._log("✅ Teste concluído com sucesso")
            return True
            
        except Exception as e:
            self._log(f"Erro durante teste: {e}", "error")
            self._tentar_detach()
            return False
        finally:
            self.estado = "OFF"
    
    def reset(self):
        """
        Retorna os servos para posição inicial
        
        Returns:
            bool: True se reset executado com sucesso
        """
        if not self._validar_servos():
            return False
        
        try:
            self.servo1.value = self.calibration['servo1']['min']
            self.servo2.value = self.calibration['servo2']['min']
            time.sleep(0.5)
            self.servo1.detach()
            self.servo2.detach()
            self._log("Servos resetados para posição ESPELHADA")
            self.angulo_servo1 = self.calibration['servo1']['min']
            self.angulo_servo2 = self.calibration['servo2']['min']
            return True
        except Exception as e:
            self._log(f"Erro ao resetar: {e}", "error")
            return False
    
    def mover_operacao(self, posicao_alternada=False):
        """
        Movimenta os servos durante operação de voo
        
        Args:
            posicao_alternada: Se True, alterna entre duas posições
        
        Returns:
            bool: True se movimento executado
        """
        if not self._validar_servos():
            return False
        
        # Verifica tempo mínimo entre movimentos
        tempo_atual = time.time()
        if tempo_atual - self.ultimo_movimento < self.tempo_minimo_entre_movimentos:
            delta = self.tempo_minimo_entre_movimentos - (tempo_atual - self.ultimo_movimento)
            self._log(f"Aguardando {delta:.1f}s antes do próximo movimento", "debug")
            return False
        
        try:
            self.estado = "ON"
            
            # Movimento espelhado sincronizado com alternância, replicando SistemaCotesia.py
            self._log(
                f"Movimento operação #{self.contador_ativacoes + 1} | "
                f"{'alternado' if posicao_alternada else 'padrão'}"
            )
            
            alvo_servo1 = (self.calibration['servo1']['max']
                           if posicao_alternada else self.calibration['servo1']['min'])
            alvo_servo2 = (self.calibration['servo2']['max']
                           if posicao_alternada else self.calibration['servo2']['min'])

            self._log(f"Servo1 -> {alvo_servo1:.3f} | Servo2 -> {alvo_servo2:.3f}", "debug")

            self.servo1.value = alvo_servo1
            time.sleep(0.05)
            self.servo2.value = alvo_servo2

            self.angulo_servo1 = alvo_servo1
            self.angulo_servo2 = alvo_servo2

            # Aguarda movimento completar
            time.sleep(0.8)
            
            # Desativa servos
            self.servo1.detach()
            self.servo2.detach()
            
            self.contador_ativacoes += 1
            self.ultimo_movimento = time.time()
            
            self._log(f"✅ Movimento {self.contador_ativacoes} concluído")
            return True
            
        except Exception as e:
            self._log(f"Erro durante movimento: {e}", "error")
            self._tentar_detach()
            return False
        finally:
            self.estado = "OFF"
    
    def get_estado(self):
        """Retorna estado atual dos servos"""
        return {
            'estado': self.estado,
            'ativacoes': self.contador_ativacoes,
            'inicializado': self.inicializado,
            'servo1_angle': self.angulo_servo1,
            'servo2_angle': self.angulo_servo2,
            'calibration': self.calibration,
        }
    
    def limpar(self):
        """Limpa recursos GPIO"""
        try:
            if self.servo1:
                self.servo1.detach()
            if self.servo2:
                self.servo2.detach()
            self._log("GPIO limpo")
        except Exception as e:
            self._log(f"Erro ao limpar GPIO: {e}", "error")
    
    def ajustar_servo(self, servo_numero, valor):
        """
        Ajusta manualmente o ângulo de um servo específico.
        
        Args:
            servo_numero (int): 1 ou 2 indicando o servo a ajustar
            valor (float): valor normalizado entre -1.0 e 1.0
        
        Returns:
            bool: True se movimento executado
        """
        if not self._validar_servos():
            return False
        
        if servo_numero not in (1, 2):
            self._log(f"Número de servo inválido: {servo_numero}", "warning")
            return False
        
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            self._log(f"Valor inválido para ajuste manual: {valor}", "warning")
            return False
        
        valor = max(-1.0, min(1.0, valor))
        alvo = self.servo1 if servo_numero == 1 else self.servo2
        
        try:
            self.estado = "ON"
            self._log(f"Ajustando servo {servo_numero} para valor {valor:.2f}")
            alvo.value = valor
            time.sleep(0.4)
            alvo.detach()
            
            if servo_numero == 1:
                self.angulo_servo1 = valor
            else:
                self.angulo_servo2 = valor
            
            return True
        except Exception as e:
            self._log(f"Erro ao ajustar servo {servo_numero}: {e}", "error")
            self._tentar_detach()
            return False
        finally:
            self.estado = "OFF"

    def get_calibration(self):
        """Retorna a calibração atual dos servos"""
        return self.calibration

    def set_calibration(self, calibration):
        """Define nova calibração e persiste em disco"""
        try:
            servo1 = calibration.get('servo1', {})
            servo2 = calibration.get('servo2', {})

            self.calibration['servo1']['min'] = float(servo1.get('min', -1.0))
            self.calibration['servo1']['max'] = float(servo1.get('max', 1.0))
            self.calibration['servo2']['min'] = float(servo2.get('min', -1.0))
            self.calibration['servo2']['max'] = float(servo2.get('max', 1.0))

            self._normalize_calibration()
            self._save_calibration()
            self.angulo_servo1 = self.calibration['servo1']['min']
            self.angulo_servo2 = self.calibration['servo2']['min']
            self._log(f"Nova calibração aplicada: {self.calibration}")
            return True
        except Exception as e:
            self._log(f"Erro ao definir calibração: {e}", "error")
            return False
    
    def detectar_limites(self):
        """
        Executa um ciclo de movimentação para confirmar os limites atuais
        e retorna os valores configurados (min/max) de cada servo.
        """
        if not self._validar_servos():
            return None
        
        limites = {}
        
        try:
            for servo_num in (1, 2):
                servo = self.servo1 if servo_num == 1 else self.servo2
                nome = f"servo{servo_num}"
                min_val = float(self.calibration[nome]['min'])
                max_val = float(self.calibration[nome]['max'])
                
                self._log(f"[CALIBRAÇÃO] Servo {servo_num}: movendo para mínimo ({min_val:.3f})")
                servo.value = min_val
                time.sleep(0.6)
                
                self._log(f"[CALIBRAÇÃO] Servo {servo_num}: movendo para máximo ({max_val:.3f})")
                servo.value = max_val
                time.sleep(0.6)
                
                self._log(f"[CALIBRAÇÃO] Servo {servo_num}: voltando para mínimo")
                servo.value = min_val
                time.sleep(0.4)
                
                servo.detach()
                
                limites[nome] = {'min': min_val, 'max': max_val}
            
            self._log(f"[CALIBRAÇÃO] Limites atuais: {limites}")
            return limites
        
        except Exception as e:
            self._log(f"Erro durante detecção de limites: {e}", "error")
            self._tentar_detach()
            return None

    def _load_calibration(self):
        """Carrega calibração do arquivo"""
        try:
            if os.path.exists(self.calibration_file):
                with open(self.calibration_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.calibration.update(data)
                        self._normalize_calibration()
                        self._log(f"Calibração carregada: {self.calibration}")
                        self.angulo_servo1 = self.calibration['servo1']['min']
                        self.angulo_servo2 = self.calibration['servo2']['min']
        except Exception as e:
            self._log(f"Erro ao carregar calibração: {e}", "warning")

    def _save_calibration(self):
        """Persiste calibração em arquivo"""
        try:
            with open(self.calibration_file, 'w', encoding='utf-8') as f:
                json.dump(self.calibration, f, indent=2)
        except Exception as e:
            self._log(f"Erro ao salvar calibração: {e}", "error")

    def _normalize_calibration(self):
        """Clampa e organiza os valores de calibração"""
        for key in ('servo1', 'servo2'):
            self.calibration[key]['min'] = max(-1.0, min(1.0, float(self.calibration[key]['min'])))
            self.calibration[key]['max'] = max(-1.0, min(1.0, float(self.calibration[key]['max'])))
            if self.calibration[key]['min'] > self.calibration[key]['max']:
                self.calibration[key]['min'], self.calibration[key]['max'] = (
                    self.calibration[key]['max'],
                    self.calibration[key]['min'],
                )
    
    def _validar_servos(self):
        """Valida se servos estão inicializados"""
        if not self.inicializado or self.servo1 is None or self.servo2 is None:
            self._log("❌ Servos não disponíveis (GPIO não inicializado)", "error")
            return False
        return True
    
    def _tentar_detach(self):
        """Tenta desativar servos em caso de erro"""
        try:
            if self.servo1:
                self.servo1.detach()
            if self.servo2:
                self.servo2.detach()
        except:
            pass

