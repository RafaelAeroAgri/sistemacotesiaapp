#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de controle de servos para o Sistema Cotesia
Controla 2 servos espelhados usando gpiozero com pigpio
"""

import time
import os
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
        
        self._log("ServoControl inicializado (servos não configurados)")
    
    def _log(self, mensagem, level="info"):
        """Log interno com fallback para print"""
        if self.logger:
            getattr(self.logger, level)(mensagem)
        else:
            print(f"[SERVO] {mensagem}")
    
    def inicializar_gpio(self):
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
            
            # SERVO 1: GPIO 12 (pino físico 32)
            self.servo1 = Servo(
                12,
                pin_factory=factory,
                min_pulse_width=1.32/1000,   # 1320µs (inicial)
                max_pulse_width=2.0/1000,    # 2000µs (final)
                frame_width=20/1000
            )
            self._log("Servo1 (GPIO12) criado")
            
            # SERVO 2: GPIO 16 (pino físico 36)
            self.servo2 = Servo(
                16,
                pin_factory=factory,
                min_pulse_width=1.076/1000,  # 1076µs (final - invertido)
                max_pulse_width=1.73/1000,   # 1730µs (inicial - invertido)
                frame_width=20/1000
            )
            self._log("Servo2 (GPIO16) criado")
            
            # Calibração inicial
            self._log("Calibrando posição inicial dos servos...")
            
            # Pequeno movimento de calibração
            self.servo1.value = 0.00
            self.servo2.value = 0.00
            time.sleep(0.3)
            
            # Posição inicial espelhada
            self.servo1.value = -1.00  # 1320µs (inicial)
            self.servo2.value = -1.00  # 1076µs (final - espelhado)
            time.sleep(0.5)
            
            # Desliga PWM
            self.servo1.detach()
            self.servo2.detach()
            
            self.inicializado = True
            self._log("✅ Servos inicializados e calibrados")
            return True
            
        except Exception as e:
            self._log(f"❌ Erro ao configurar servos: {e}", "error")
            self._log("⚠️ Sistema continuará sem controle de servos", "warning")
            return False
    
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
            self.servo1.value = -1.00
            self.servo2.value = -1.00
            time.sleep(1.0)
            
            # Movimento 1 - Espelhado
            self._log("Movimento 1: S1 vai (1320→2000) / S2 volta (1076→1730)")
            self.servo1.value = 1.00
            self.servo2.value = 1.00
            time.sleep(2.0)
            
            # Movimento 2 - Espelhado
            self._log("Movimento 2: S1 volta (2000→1320) / S2 vai (1730→1076)")
            self.servo1.value = -1.00
            self.servo2.value = -1.00
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
            self.servo1.value = -1.00  # 1320µs (inicial)
            self.servo2.value = -1.00  # 1076µs (final espelhado)
            time.sleep(0.5)
            self.servo1.detach()
            self.servo2.detach()
            self._log("Servos resetados para posição ESPELHADA")
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
            
            # Movimento espelhado sincronizado
            self._log(f"Movimento operação #{self.contador_ativacoes + 1}")
            
            # Vai para posição final
            self.servo1.value = 1.00   # 2000µs
            self.servo2.value = 1.00   # 1730µs
            time.sleep(0.8)
            
            # Volta para posição inicial
            self.servo1.value = -1.00  # 1320µs
            self.servo2.value = -1.00  # 1076µs
            time.sleep(0.5)
            
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
            'inicializado': self.inicializado
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

