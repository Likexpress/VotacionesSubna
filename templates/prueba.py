import requests

url = "https://waba-v2.360dialog.io/messages"
headers = {
    "D360-API-KEY": "DvY54vkC1Fu9dYn8zWzLZ9JOAK",
    "Content-Type": "application/json"
}
data = {
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": "59160770477",  # Número válido de prueba
    "type": "text",
    "text": {
        "body": "Hola, este es un mensaje de prueba desde Python"
    }
}

response = requests.post(url, headers=headers, json=data)
print("Código de respuesta:", response.status_code)
print("Respuesta:", response.text)
