import requests
import os

# Reemplaza este token por el real (si no está en tu .env local)
WABA_TOKEN = os.getenv("WABA_TOKEN", "DvY54vkC1Fu9dYn8zWzLZ9JOAK")

# Webhook que quieres registrar
webhook_url = "https://votacion-whatsapp.onrender.com/whatsapp"

# Solicitud HTTP
headers = {
    "Content-Type": "application/json",
    "D360-API-KEY": WABA_TOKEN
}
data = {
    "url": webhook_url
}

# Hacer la solicitud POST
response = requests.post("https://waba-v2.360dialog.io/v1/configs/webhook", headers=headers, json=data)

# Mostrar resultado
print("✅ Código de estado:", response.status_code)
print("✅ Respuesta:", response.text)
