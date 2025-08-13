#!/usr/bin/env python3
"""
Sistema de Gerenciamento de Usuários
Controla cadastro, período de teste, pagamentos e acesso ao sistema
"""
import os
import logging
from datetime import datetime, timedelta
import pytz
from database import DatabaseManager

logger = logging.getLogger(__name__)

class UserManager:
    """Gerencia usuários, teste gratuito e controle de acesso"""
    
    def __init__(self, db):
        self.db = db
        self.timezone_br = pytz.timezone('America/Sao_Paulo')
        self.valor_mensal = 20.00
        self.dias_teste_gratuito = 7
        
    def cadastrar_usuario(self, chat_id, nome, email, telefone):
        """Cadastra novo usuário com período de teste gratuito"""
        try:
            # Verificar se usuário já existe
            if self.verificar_usuario_existe(chat_id):
                return {'success': False, 'message': 'Usuário já cadastrado no sistema'}
            
            agora = datetime.now(self.timezone_br)
            fim_teste = agora + timedelta(days=self.dias_teste_gratuito)
            
            # Inserir usuário
            query = """
            INSERT INTO usuarios (
                chat_id, nome, email, telefone, 
                data_cadastro, fim_periodo_teste, status, plano_ativo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db.execute_query(query, [
                chat_id, nome, email, telefone,
                agora, fim_teste, 'teste_gratuito', True
            ])
            
            logger.info(f"Usuário cadastrado: {nome} (chat_id: {chat_id})")
            
            return {
                'success': True, 
                'message': f'Cadastro realizado com sucesso! Você tem {self.dias_teste_gratuito} dias de teste gratuito.',
                'fim_teste': fim_teste
            }
            
        except Exception as e:
            logger.error(f"Erro ao cadastrar usuário: {e}")
            return {'success': False, 'message': 'Erro interno ao realizar cadastro'}
    
    def verificar_usuario_existe(self, chat_id):
        """Verifica se usuário já está cadastrado"""
        try:
            query = "SELECT id FROM usuarios WHERE chat_id = %s"
            result = self.db.fetch_one(query, [chat_id])
            return result is not None
        except Exception as e:
            logger.error(f"Erro ao verificar usuário: {e}")
            return False
    
    def obter_usuario(self, chat_id):
        """Obtém dados completos do usuário"""
        try:
            query = """
            SELECT chat_id, nome, email, telefone, data_cadastro, 
                   fim_periodo_teste, ultimo_pagamento, proximo_vencimento,
                   status, plano_ativo, total_pagamentos
            FROM usuarios WHERE chat_id = %s
            """
            return self.db.fetch_one(query, [chat_id])
        except Exception as e:
            logger.error(f"Erro ao obter usuário: {e}")
            return None
    
    def verificar_acesso(self, chat_id):
        """Verifica se usuário tem acesso ao sistema"""
        try:
            usuario = self.obter_usuario(chat_id)
            if not usuario:
                return {'acesso': False, 'motivo': 'usuario_nao_cadastrado'}
            
            agora = datetime.now(self.timezone_br)
            
            # Verificar se ainda está no período de teste
            if usuario['status'] == 'teste_gratuito':
                if agora <= usuario['fim_periodo_teste']:
                    dias_restantes = (usuario['fim_periodo_teste'] - agora).days
                    return {
                        'acesso': True, 
                        'tipo': 'teste',
                        'dias_restantes': dias_restantes,
                        'usuario': usuario
                    }
                else:
                    # Teste expirado, precisa pagar
                    self.atualizar_status_usuario(chat_id, 'teste_expirado', False)
                    return {'acesso': False, 'motivo': 'teste_expirado', 'usuario': usuario}
            
            # Verificar se tem plano pago ativo
            if usuario['status'] == 'pago' and usuario['plano_ativo']:
                if usuario['proximo_vencimento'] and agora <= usuario['proximo_vencimento']:
                    dias_restantes = (usuario['proximo_vencimento'] - agora).days
                    return {
                        'acesso': True, 
                        'tipo': 'pago',
                        'dias_restantes': dias_restantes,
                        'usuario': usuario
                    }
                else:
                    # Plano vencido
                    self.atualizar_status_usuario(chat_id, 'vencido', False)
                    return {'acesso': False, 'motivo': 'plano_vencido', 'usuario': usuario}
            
            # Sem acesso
            return {'acesso': False, 'motivo': 'sem_plano_ativo', 'usuario': usuario}
            
        except Exception as e:
            logger.error(f"Erro ao verificar acesso: {e}")
            return {'acesso': False, 'motivo': 'erro_interno'}
    
    def atualizar_status_usuario(self, chat_id, status, plano_ativo):
        """Atualiza status e plano ativo do usuário"""
        try:
            query = "UPDATE usuarios SET status = %s, plano_ativo = %s WHERE chat_id = %s"
            self.db.execute_query(query, [status, plano_ativo, chat_id])
            logger.info(f"Status do usuário {chat_id} atualizado para: {status}")
        except Exception as e:
            logger.error(f"Erro ao atualizar status do usuário: {e}")
    
    def processar_pagamento(self, chat_id, valor_pago, referencia_pagamento):
        """Processa pagamento aprovado e ativa plano mensal"""
        try:
            agora = datetime.now(self.timezone_br)
            proximo_vencimento = agora + timedelta(days=30)  # 30 dias
            
            # Atualizar dados do usuário
            query = """
            UPDATE usuarios SET 
                status = %s, 
                plano_ativo = %s,
                ultimo_pagamento = %s,
                proximo_vencimento = %s,
                total_pagamentos = COALESCE(total_pagamentos, 0) + %s
            WHERE chat_id = %s
            """
            
            self.db.execute_query(query, [
                'pago', True, agora, proximo_vencimento, valor_pago, chat_id
            ])
            
            # Registrar pagamento
            self.registrar_pagamento(chat_id, valor_pago, referencia_pagamento)
            
            logger.info(f"Pagamento processado para usuário {chat_id}: R$ {valor_pago}")
            
            return {
                'success': True,
                'message': 'Pagamento aprovado! Plano ativado por 30 dias.',
                'proximo_vencimento': proximo_vencimento
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar pagamento: {e}")
            return {'success': False, 'message': 'Erro ao processar pagamento'}
    
    def registrar_pagamento(self, chat_id, valor, referencia):
        """Registra pagamento no histórico"""
        try:
            agora = datetime.now(self.timezone_br)
            query = """
            INSERT INTO pagamentos (chat_id, valor, data_pagamento, referencia, status)
            VALUES (%s, %s, %s, %s, %s)
            """
            self.db.execute_query(query, [chat_id, valor, agora, referencia, 'aprovado'])
        except Exception as e:
            logger.error(f"Erro ao registrar pagamento: {e}")
    
    def obter_estatisticas_usuario(self, chat_id):
        """Obtém estatísticas do usuário"""
        try:
            usuario = self.obter_usuario(chat_id)
            if not usuario:
                return None
                
            # Contar clientes do usuário
            query_clientes = "SELECT COUNT(*) as total FROM clientes WHERE chat_id_usuario = %s"
            total_clientes = self.db.fetch_one(query_clientes, [chat_id])
            
            # Contar mensagens enviadas
            query_mensagens = "SELECT COUNT(*) as total FROM logs_envio WHERE chat_id_usuario = %s"
            total_mensagens = self.db.fetch_one(query_mensagens, [chat_id])
            
            return {
                'usuario': usuario,
                'total_clientes': total_clientes['total'] if total_clientes else 0,
                'total_mensagens': total_mensagens['total'] if total_mensagens else 0,
                'total_pagamentos': usuario.get('total_pagamentos', 0)
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return None
    
    def listar_usuarios_vencendo(self, dias_aviso=3):
        """Lista usuários que vão vencer em X dias"""
        try:
            limite = datetime.now(self.timezone_br) + timedelta(days=dias_aviso)
            
            query = """
            SELECT chat_id, nome, email, proximo_vencimento
            FROM usuarios 
            WHERE status = 'pago' 
            AND plano_ativo = true 
            AND proximo_vencimento <= %s
            ORDER BY proximo_vencimento ASC
            """
            
            return self.db.fetch_all(query, [limite])
            
        except Exception as e:
            logger.error(f"Erro ao listar usuários vencendo: {e}")
            return []
    
    def get_valor_mensal(self):
        """Retorna valor da mensalidade"""
        return self.valor_mensal