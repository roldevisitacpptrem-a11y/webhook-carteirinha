from flask import Flask, request, jsonify
import os
import json
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configurações de log
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg')
RANGE_NAME = 'carteirinhas_ok!A2:D'

# Autenticação
try:
    credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if not credentials_json:
        logger.error('❌ Credenciais não encontradas')
        raise ValueError('Credenciais do Google não configuradas')
    credentials_info = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=credentials)
    logger.info('✅ Conexão com Google Sheets estabelecida')
except Exception as e:
    logger.error('❗ Erro na autenticação: %s', e)
    raise

@app.route('/', methods=['GET'])
def home():
    logger.info('🏠 Endpoint raiz acessado')
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info('📥 Requisição recebida')
    try:
        data = request.get_json(silent=True)
        if not data:
            logger.warning('⚠️ JSON inválido')
            return jsonify({'fulfillmentText': '⚠️ Requisição inválida: JSON não fornecido.'}), 400

        logger.info('📄 JSON: %s', json.dumps(data, ensure_ascii=False))
        raw_matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')
        if not raw_matricula:
            logger.warning('⚠️ Matrícula não informada')
            return jsonify({'fulfillmentText': '⚠️ Matrícula não informada.'}), 400

        # ✅ Normaliza matrícula (remove decimais, espaços, etc.)
        matricula = str(int(float(raw_matricula))).strip()
        logger.info('📌 Matrícula normalizada: %s', matricula)

        # Busca planilha
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME
            ).execute()
            rows = result.get('values', [])
            logger.info('📄 Linhas carregadas: %d', len(rows))
        except HttpError as e:
            logger.error('❗ Erro ao acessar planilha: %s', e)
            return jsonify({'fulfillmentText': f'❌ Erro ao acessar planilha: {e}'}), 500

        # Busca matrícula
        for row in rows:
            if not row or len(row) < 1:
                continue
            matricula_planilha = str(row[0]).strip()
            logger.info('🔍 Comparando: %s == %s', matricula_planilha, matricula)
            if matricula_planilha == matricula:
                visitante = row[1] if len(row) > 1 else 'Desconhecido'
                situacao = row[2] if len(row) > 2 else 'Indefinida'
                motivo = row[3] if len(row) > 3 else 'Nenhum motivo informado'
                resposta = (
                    f'👤 Visitante: {visitante}\n'
                    f'📌 Situação: {situacao}\n'
                    f'📄 Motivo: {motivo}'
                )
                logger.info('✅ Dados encontrados: %s', resposta)
                return jsonify({'fulfillmentText': resposta})

        # ⚠️ Matrícula não encontrada
        logger.warning('❌ Matrícula %s não encontrada', matricula)
        print(f'❌ MATRÍCULA NÃO ENCONTRADA: {matricula}')
        return jsonify({'fulfillmentText': '❌ Nenhuma informação encontrada para esta matrícula.'}), 404

    except Exception as e:
        logger.error('❗ Erro interno: %s', e, exc_info=True)
        return jsonify({'fulfillmentText': f'❌ Erro interno: {e}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info('🚀 Servidor iniciado na porta %d', port)
    app.run(host='0.0.0.0', port=port)
