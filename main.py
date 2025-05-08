import os
import unicodedata
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from transformers import AutoTokenizer, AutoModelForCausalLM
from flask import Flask, request
import torch

from fuzzywuzzy import fuzz
from unidecode import unidecode
import re
import random

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "mi_token_unico_12345")
PHONE_ID     = "674027565786401"
WHATSAPP_API = f"https://graph.facebook.com/v13.0/{PHONE_ID}/messages"
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "EAAbIBxQGVy0BO1i95YfXArjZCX9Jn8HchKLnxxV12CpnZBopUC59h02c2lBnL0nRib7VXWfeKmfKZBMNRvZCGk0wUE1J2BiHZCPnCsJAQVcKOCTW7y0SUGuCZB713yC092ZBsYHPZBKS3MkMms3yL0CfDBNbBNsTVymLsxAM1tzjGQZA0ZBnVrT2IXPjKyNz1b1zV09PmAMTZBIJeVd1DIfyhHBIbncAKNwBk1pZASxVI9Xt")
# Inicializar Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("saborysazon-55dcf-firebase-adminsdk-fbsvc-7ac822bdce.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# Cargar modelo de Hugging Face
model_name = "NadiaLiz/Llama-3.2"
tokenizer  = AutoTokenizer.from_pretrained(model_name)
device     = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model      = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="auto",
    low_cpu_mem_usage = True,
    torch_dtype=torch.float16
).to(device)

# Normalizar texto (eliminar tildes y caracteres especiales)
def normalizar_texto(texto):
    texto = unidecode(texto.lower().strip())
    return re.sub(r'[^\w\s]', '', texto)


def obtener_carta():
    try:
        carta = db.collection('Carta').get()  # Cambiado a 'Carta'
        # Convertir documentos a lista de diccionarios
        items = [item.to_dict() for item in carta]
        # Ordenar por categoria (alfabético) y luego por nombre (alfabético)
        items_sorted = sorted(items, key=lambda x: (x['categoria'].lower(), x['nombre'].lower()))

        contexto = "Menú del restaurante:\n"
        for item in items_sorted:
            contexto += f"- {item['nombre']} ({item['categoria']})\n"
        return contexto
    except Exception as e:
        print(f"Error al obtener la carta: {e}")
        #"Lo siento, no puedo mostrar la carta ahora. ¿Qué plato buscas?"
        return "Menú del restaurante: No disponible temporalmente."

# Extraer nombre del plato con coincidencia aproximada
def extraer_plato(mensaje):
    mensaje_normalizado = normalizar_texto(mensaje)
    carta = db.collection('Carta').get()
    nombres_platos = [(item.to_dict()['nombre'], normalizar_texto(item.to_dict()['nombre'])) for item in carta]

    for nombre, nombre_normalizado in nombres_platos:
        if fuzz.partial_ratio(nombre_normalizado, mensaje_normalizado) > 80:
            return nombre
    return None

# Buscar precio y detalles de un plato
def buscar_precio(plato):
    try:
        carta = db.collection('Carta').get()
        for item in carta:
            item_data = item.to_dict()
            if item_data['nombre'].lower() == plato.lower():
                return (f"{item_data['nombre']} ({item_data['categoria']}): "
                        f"{item_data['descripcion']}, Precio: S/{item_data['precio']}")
        return None
    except Exception as e:
        print(f"Error al buscar precio: {e}")
        return None

# Nueva función mejorada para obtener una recomendación
def obtener_recomendacion(mensaje_normalizado):
    try:
        # Categorías válidas
        categorias_validas = ["Plato de fondo", "Bebida", "Postre", "Sopa", "Ensalada"]

        # Detectar categoría específica en el mensaje
        categoria_seleccionada = None
        for cat in categorias_validas:
            if fuzz.partial_ratio(normalizar_texto(cat), mensaje_normalizado) > 80:
                categoria_seleccionada = cat
                break

        # Si no se especifica categoría, recomendar un plato principal, bebida y postre
        if not categoria_seleccionada:
            recomendacion = "Te recomiendo una comida completa:\n"
            for cat in ["Plato de fondo", "Bebida", "Postre"]:
                carta = db.collection('Carta').where('categoria', '==', cat).get()
                if carta:
                    item = random.choice(carta).to_dict()
                    recomendacion += f"- {item['nombre']} ({cat}): {item['descripcion']}, Precio: S/{item['precio']}\n"
                else:
                    recomendacion += f"- No hay {cat.lower()}s disponibles.\n"
            return recomendacion.strip()

        # Si se especifica categoría, recomendar solo un ítem de esa categoría
        carta = db.collection('Carta').where('categoria', '==', categoria_seleccionada).get()
        if carta:
            item = random.choice(carta).to_dict()
            return f"Te recomiendo {item['nombre']}: {item['descripcion']}, por solo S/{item['precio']}."
        else:
            return f"No tengo {categoria_seleccionada}s para recomendar. ¿Quieres otra categoría?"
    except Exception as e:
        print(f"Error al recomendar: {e}")
        return "Lo siento, no puedo recomendar ahora. ¿Qué te gustaría?"

# Obtener contexto desde Firebase, ordenado por categoria y nombre
def obtener_contexto():
    try:
        carta = db.collection('carta').get()
        contexto = "Menú del restaurante:\n"
        for item in carta:
            item_data = item.to_dict()
            contexto += f"- {item_data['nombre']} ({item_data['categoria']}): {item_data['descripcion']}, Precio: ${item_data['precio']}\n"
        return contexto
    except Exception as e:
        print(f"Error al obtener contexto: {e}")
        return "Menú del restaurante: No disponible temporalmente."

# Generar respuesta con el modelo
def generar_respuesta(mensaje, contexto):
    prompt = (
        f"{contexto}\n\n"
        f"Eres un asistente de Sabor y Sazón (un restaurante de comid peruana) que ayuda con el menú. "
        f"Responde de forma amable, precisa y breve, usando la información del menú. "
        f"Si no entiendes, pide aclaraciones.\n\n"
        f"Usuario: {mensaje}\n"
        f"Asistente:"
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    outputs = model.generate(
        **inputs,
        max_new_tokens=100,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        pad_token_id=tokenizer.eos_token_id
    )
    respuesta = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return respuesta.replace(prompt, "").strip()

def send_whatsapp_message(to: str, body: str) -> dict:
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type":  "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":                to,
        "text":              {"body": body}
    }
    resp = requests.post(WHATSAPP_API, headers=headers, json=payload)
    try:
        return resp.json()
    except ValueError:
        return {"error": resp.text}

# ———————— FLASK APP ————————
app = Flask(__name__)

# Ruta principal para WhatsApp
@app.route("/whatsapp", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode      = request.args.get("hub.mode")
        token     = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("Webhook verificado")
            return challenge, 200
        return "Token no coincide", 403

    data = request.get_json(force=True)
    try:
        msg_obj      = data["entry"][0]["changes"][0]["value"]["messages"][0]
        incoming_msg = msg_obj["text"]["body"]
        from_number  = msg_obj["from"]
    except Exception:
        return "OK", 200  # ignorar otros eventos

    print("Mensaje recibido:", incoming_msg)
    incoming_msg_normalizado = normalizar_texto(incoming_msg)

    # Obtener contexto
    contexto = obtener_contexto()

    # Lista de variaciones para cada intención
    precio_keywords = ["precio", "presio", "precios", "cuanto", "cuanto cuesta", "cuesta", "valor", "costo"]
    carta_keywords = ["carta", "karta", "menu", "menú", "menus"]
    recomendacion_keywords = ["recomendacion", "recomendación", "recomendaciones", "recomendar", "rekomendar", "sugerencia", "sugerir"]

    # Detectar intenciones con coincidencia aproximada
    es_pregunta_precio = any(fuzz.partial_ratio(kw, incoming_msg_normalizado) > 80 for kw in precio_keywords)
    es_pregunta_carta = any(fuzz.partial_ratio(kw, incoming_msg_normalizado) > 80 for kw in carta_keywords)
    es_pregunta_recomendacion = any(fuzz.partial_ratio(kw, incoming_msg_normalizado) > 80 for kw in recomendacion_keywords)

    # Manejar casos específicos
    if "hola" in incoming_msg_normalizado:
        respuesta = ("¡Hola! Bienvenido al restaurante Sabor y Sazón. ¿Quieres ver la carta, saber el precio de un plato, "
                     "o necesitas una recomendación?")

    elif es_pregunta_carta:
        respuesta = obtener_carta()

    elif es_pregunta_recomendacion:
        respuesta = obtener_recomendacion(incoming_msg_normalizado)

    elif es_pregunta_precio:
        plato = extraer_plato(incoming_msg)
        if plato:
            respuesta = buscar_precio(plato)
            if not respuesta:
                respuesta = f"Lo siento, no encontré detalles para '{plato}'."
        else:
            respuesta = "¿De qué plato deseas saber el precio?"

    else:
        respuesta = generar_respuesta(incoming_msg, contexto)
        if not respuesta or len(respuesta) < 10:
            respuesta = "No entendí tu mensaje. ¿Puedes especificar si quieres la carta, un precio, o una recomendación?"

    print("Respuesta generada:", respuesta)

    # Limpiar número y enviar respuesta
    to   = from_number.replace("whatsapp:", "").replace("+", "").strip()
    print("Enviando a:", to)
    resp = send_whatsapp_message(to, respuesta)
    print("WhatsApp API response:", resp)

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
