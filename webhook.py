from flask import Flask, request, jsonify
import logging
import re
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

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
)
service = build('sheets', 'v4', credentials=credentials)

# --- Funções auxiliares ---
def normalize_matricula(raw):
    if not raw:
        return None
    cleaned = str(raw).strip()
    cleaned = re.sub(r'[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]', '', cleaned)
    return cleaned or None

def fetch_all_rows():
    """Busca todas as linhas da planilha direto, sem cache"""
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        rows = result.get('values', [])
        matr_dict = {}
        for row in rows:
            matricula = normalize_matricula(row[0])
            if not matricula:
                continue
            visitante = row[1].strip() if len(row) > 1 else 'Desconhecido'
            situacao = row[2].strip() if len(row) > 2 else ''
            motivo = row[3].strip() if len(row) > 3 else ''
            registro = {'visitante': visitante, 'situacao': situacao, 'motivo': motivo}
            matr_dict[matricula] = [registro]
        logger.info('🔹 Matrículas carregadas: %d', len(matr_dict))
        return matr_dict
    except HttpError as err:
        logger.error('Erro ao acessar Google Sheets: %s', err)
        return {}

def lookup_matricula(matricula):
    """Procura matrícula exata"""
    matr_dict = fetch_all_rows()
    matricula_clean = normalize_matricula(matricula)
    logger.debug('🔹 Matrícula recebida: "%s"', matricula)
    logger.debug('🔹 Matrícula normalizada: "%s"', matricula_clean)
    return matr_dict.get(matricula_clean, [])

# --- Webhook Flask ---
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
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
    app.run(port=5000, debug=True)
