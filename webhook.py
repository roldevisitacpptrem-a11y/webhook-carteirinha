from flask import Flask, request, jsonify
import os
import json
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configura logging para o Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configurações do Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg')
RANGE_NAME = 'carteirinhas_ok!A2:D'

# Inicializa conexão com Google Sheets
try:
    credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if not credentials_json:
        logger.error('❌ Variável GOOGLE_APPLICATION_CREDENTIALS_JSON não encontrada')
        raise ValueError('Credenciais do Google não configuradas')
    
    logger.info('🔑 Credenciais encontradas: %s...', credentials_json[:50])
    credentials_info = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=SCOPES
    )
    service = build('sheets', 'v4', credentials=credentials)
    logger.info('✅ Conexão com Google Sheets estabelecida')
except Exception as e:
    logger.error('❗ Erro ao conectar com Google Sheets: %s', e)
    raise

@app.route('/', methods=['GET'])
def home():
    logger.info('🏠 Acessando endpoint raiz')
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info('📥 Recebendo requisição no webhook')
    try:
        data = request.get_json(silent=True)
        if not data:
            logger.warning('⚠️ Nenhum JSON recebido na requisição')
            return jsonify({'fulfillmentText': '⚠️ Requisição inválida: JSON não fornecido.'}), 400

        logger.info('📄 JSON recebido: %s', json.dumps(data, ensure_ascii=False))
        matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')

        if not matricula:
            logger.warning('⚠️ Matrícula não informada no JSON')
            return jsonify({'fulfillmentText': '⚠️ Matrícula não informada.'}), 400

        matricula = str(matricula).strip()
        logger.info('📌 Matrícula recebida: %s', matricula)

        # Consulta a planilha
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME
            ).execute()
            rows = result.get('values', [])
            logger.info('📄 Linhas carregadas da planilha: %s', rows)
            logger.info('🔢 Matrículas na planilha: %s', [row[0] for row in rows if row])
        except HttpError as e:
            logger.error('❗ Erro ao acessar a planilha: %s', e)
            return jsonify({'fulfillmentText': f'❌ Erro ao acessar a planilha: {e}'}), 500

        # Busca a matrícula
        for row in rows:
            if not row:
                continue
            matricula_planilha = str(row[0]).strip()
            logger.info('🔍 Comparando: %s == %s', matricula_planilha, matricula)
            if matricula_planilha == matricula:
                visitante = row[1] if len(row) > 1 else 'Desconhecido'
                situacao = row[2] if len(row) > 2 else 'Indefinida'
                motivo = row[3] if len(row) > 3 else 'Nenhum motivo informado'
                resposta = f'👤 Visitante: {visitante}\n📌 Situação: {situacao}\n📄 Motivo: {motivo}'
                logger.info('✅ Matrícula encontrada: %s', resposta)
                return jsonify({'fulfillmentText': resposta})

        logger.warning('❌ Matrícula %s não encontrada na planilha', matricula)
        return jsonify({'fulfillmentText': '❌ Matrícula não encontrada.'}), 404

    except Exception as e:
        logger.error('❗ Erro no webhook: %s', e, exc_info=True)
        return jsonify({'fulfillmentText': f'❌ Erro interno: {e}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info('🚀 Iniciando servidor na porta %d', port)
    app.run(host='0.0.0.0', port=port)