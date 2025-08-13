from flask import Flask, request, jsonify
import logging
import re
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Configuração de logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuração do Google Sheets ---
SERVICE_ACCOUNT_FILE = 'service_account.json'
SPREADSHEET_ID = '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg'
RANGE_NAME = 'carteirinhas_ok!A2:D'

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    logger.error(f'O arquivo {SERVICE_ACCOUNT_FILE} não foi encontrado. O deploy vai falhar!')
else:
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    service = build('sheets', 'v4', credentials=credentials)
    logger.info('✅ Conexão com Google Sheets configurada com sucesso.')

# --- Funções auxiliares ---
def normalize_matricula(raw):
    """Remove espaços e caracteres invisíveis"""
    if not raw:
        return None
    cleaned = str(raw).strip()
    cleaned = re.sub(r'[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]', '', cleaned)
    return cleaned or None

def sanitize_situacao(situacao):
    """Garante que situação não venha com caracteres estranhos"""
    return str(situacao).strip() if situacao else ''

def clean_motivo(motivo):
    """Limpa motivos vazios ou nulos"""
    return str(motivo).strip() if motivo else ''

def fetch_all_rows():
    """Busca todas as linhas da planilha direto, sem cache"""
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        rows = result.get('values', [])
        matr_dict = {}
        for idx, row in enumerate(rows, start=2):
            matricula = normalize_matricula(row[0])
            if not matricula:
                logger.warning(f'Linha {idx}: matrícula vazia ou inválida')
                continue
            visitante = row[1].strip() if len(row) > 1 else 'Desconhecido'
            situacao = sanitize_situacao(row[2] if len(row) > 2 else '')
            motivo = clean_motivo(row[3] if len(row) > 3 else '')
            registro = {'visitante': visitante, 'situacao': situacao, 'motivo': motivo}
            matr_dict[matricula] = [registro]
        logger.info(f'🔹 Matrículas carregadas: {len(matr_dict)}')
        return matr_dict
    except HttpError as err:
        logger.error('Erro ao acessar Google Sheets: %s', err)
        return {}
    except Exception as e:
        logger.error('Erro inesperado ao buscar dados: %s', e)
        return {}

def lookup_matricula(matricula):
    """Procura matrícula exata"""
    matr_dict = fetch_all_rows()
    matricula_clean = normalize_matricula(matricula)
    logger.info(f'🔹 Matrícula recebida: "{matricula}" | Normalizada: "{matricula_clean}"')
    resultados = matr_dict.get(matricula_clean, [])
    if not resultados:
        logger.info(f'❌ Matrícula "{matricula_clean}" não encontrada.')
    return resultados

# --- Webhook Flask ---
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data:
        logger.warning('⚠️ Requisição sem JSON recebido')
        return jsonify({'fulfillmentText': 'Erro: não foi possível ler os dados da requisição.'})

    raw_matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')
    if not raw_matricula:
        return jsonify({'fulfillmentText': 'Por favor, digite a matrícula.'})

    resultados = lookup_matricula(raw_matricula)
    if not resultados:
        return jsonify({'fulfillmentText': f'Matrícula "{raw_matricula}" não encontrada.'})

    resposta = []
    for r in resultados:
        texto = f'Visitante: {r["visitante"]}\nSituação: {r["situacao"]}'
        if r["motivo"]:
            texto += f'\nMotivo: {r["motivo"]}'
        resposta.append(texto)

    return jsonify({'fulfillmentText': '\n\n'.join(resposta)})

if __name__ == '__main__':
    logger.info('🌐 Servidor iniciando em 0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=True)
