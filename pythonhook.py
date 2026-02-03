import requests
import os

# Cargar el token de tu archivo .env o ponelo directamente aquí
WABA_TOKEN = os.environ.get("WABA_TOKEN", "DvY54vkC1Fu9dYn8zWzLZ9JOAK")

url = "https://waba-v2.360dialog.io/v1/configs/webhook"
headers = {
    "Content-Type": "application/json",
    "D360-API-KEY": WABA_TOKEN
}
webhook_payload = {
    "url": "https://741a-2800-cd0-db2d-6500-d4a5-4875-8429-2529.ngrok-free.app/whatsapp"
}

response = requests.post(url, json=webhook_payload, headers=headers)
print("Código de estado:", response.status_code)
print("Respuesta:", response.text)
