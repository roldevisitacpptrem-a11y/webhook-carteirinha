from flask import Flask, request, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Caminho para o seu arquivo de chave
SERVICE_ACCOUNT_FILE = 'newagent-vngj-b8e71c299521.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# ID da planilha e nome da aba (com aspas simples por conter espaço)
SPREADSHEET_ID = '1EpGuRD02oPPJOT1O6L08aqWWZuD25ZmkV9jD6rUoeAg'
RANGE_NAME = "carteirinhas_ok!A2:D"
  # <- Aspas simples aqui resolvem o problema

# Autenticação
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

def consultar_visitantes(matricula):
    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME
    ).execute()

    values = result.get('values', [])

    resposta = f"Visitantes da matrícula {matricula}:\n\n"
    encontrou = False

    for row in values:
        if len(row) < 4:
            continue
        if row[0].strip() == str(matricula).strip():
            visitante = row[1]
            situacao = row[2]
            motivo = row[3]
            if situacao.lower() == "ok":
                resposta += f"- {visitante}: OK ✅\n"
            else:
                resposta += f"- {visitante}: Pendente ❌ ({motivo})\n"
            encontrou = True

    if not encontrou:
        resposta = f"Nenhum visitante encontrado para a matrícula {matricula}."

    return resposta

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    matricula = req['queryResult']['parameters'].get('matricula')
    
    resposta = consultar_visitantes(matricula)

    return jsonify({
        "fulfillmentText": resposta
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
