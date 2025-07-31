from flask import Flask, request, jsonify
import os, json
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Configurações do Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg'
RANGE_NAME = 'carteirinhas_ok!A2:D'  # Começa na linha 2 para ignorar cabeçalho

# Carrega credenciais
credentials_info = json.loads(os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON'])
credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

@app.route('/', methods=['GET'])
def home():
    return '✅ API do Rol de Visitas funcionando!'

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    matricula = data.get('queryResult', {}).get('parameters', {}).get('matricula')

    if matricula is None:
        return jsonify({'fulfillmentText': '⚠️ Matrícula não informada.'})

    # Garantir string sem espaços
    matricula = str(matricula).strip()

    try:
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        rows = result.get('values', [])

        resposta = '❌ Matrícula não encontrada.'

        for row in rows:
            # row[0] será string no formato '1014099'
            if str(row[0]).strip() == matricula:
                visitante = row[1] if len(row) > 1 else 'Desconhecido'
                situacao = row[2] if len(row) > 2 else 'Indefinida'
                motivo = row[3] if len(row) > 3 else 'Nenhum motivo informado'
                resposta = f'👤 Visitante: {visitante}\n📌 Situação: {situacao}\n📄 Motivo: {motivo}'
                break

    except Exception as e:
        resposta = f'❌ Erro ao acessar a planilha: {e}'

    return jsonify({'fulfillmentText': resposta})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
