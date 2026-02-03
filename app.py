from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime
from dotenv import load_dotenv
import os
import requests
from flask_migrate import Migrate
import json
import csv
from paises import PAISES_CODIGOS
from flask import session
from flask import render_template
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFProtect
from flask import Flask, request, render_template, redirect, jsonify, session
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer
import unicodedata
import re
import pandas as pd
from flask import request, jsonify



# ---------------------------
# Loader de Candidatos por Municipio (CSV)
# ---------------------------

CANDIDATOS_CSV_PATH = os.path.join(os.path.dirname(__file__), "privado", "CandidatosPorMunicipio.csv")

# Cache en memoria para no releer el CSV en cada request
_CANDIDATOS_CACHE = {
    "by_id_municipio": {},   # { "123": [ {candidato...}, ... ] }
    "id_by_municipio": {},   # { "TARVITA": ["10","11"] }  (ojo: puede haber duplicados)
    "loaded": False,
    "error": None
}


def _norm_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = re.sub(r"\s+", " ", s)
    return s


def cargar_candidatos_desde_csv():
    """
    Lee privado/CandidatosPorMunicipio.csv y construye:
    - by_id_municipio: lista de candidatos por id_municipio
    - id_by_municipio: posible lista de ids por nombre de municipio (si hay nombres repetidos)
    """
    global _CANDIDATOS_CACHE

    _CANDIDATOS_CACHE["by_id_municipio"] = {}
    _CANDIDATOS_CACHE["id_by_municipio"] = {}
    _CANDIDATOS_CACHE["loaded"] = False
    _CANDIDATOS_CACHE["error"] = None

    if not os.path.exists(CANDIDATOS_CSV_PATH):
        _CANDIDATOS_CACHE["error"] = f"No existe el archivo: {CANDIDATOS_CSV_PATH}"
        return

    try:
        with open(CANDIDATOS_CSV_PATH, encoding="utf-8-sig") as f:
            lector = csv.DictReader(f)

            required = {
                "id_municipio",
                "municipio",
                "id_nombre_completo",
                "nombre_completo",
                "id_organizacion_politica",
                "organizacion_politica",
                "id_cargo",
                "cargo",
            }
            headers = set(lector.fieldnames or [])
            faltantes = required - headers
            if faltantes:
                _CANDIDATOS_CACHE["error"] = f"Faltan columnas en CSV: {sorted(list(faltantes))}"
                return

            for row in lector:
                id_mun = str(row.get("id_municipio") or "").strip()
                mun = _norm_text(row.get("municipio"))

                if not id_mun or not mun:
                    continue

                item = {
                    "id_municipio": id_mun,
                    "municipio": mun,
                    "id_nombre_completo": str(row.get("id_nombre_completo") or "").strip(),
                    "nombre_completo": (row.get("nombre_completo") or "").strip(),
                    "id_organizacion_politica": str(row.get("id_organizacion_politica") or "").strip(),
                    "organizacion_politica": (row.get("organizacion_politica") or "").strip(),
                    "id_cargo": str(row.get("id_cargo") or "").strip(),
                    "cargo": (row.get("cargo") or "").strip(),
                }

                _CANDIDATOS_CACHE["by_id_municipio"].setdefault(id_mun, []).append(item)

                # Para resolver desde nombre (si hiciera falta)
                _CANDIDATOS_CACHE["id_by_municipio"].setdefault(mun, [])
                if id_mun not in _CANDIDATOS_CACHE["id_by_municipio"][mun]:
                    _CANDIDATOS_CACHE["id_by_municipio"][mun].append(id_mun)

        _CANDIDATOS_CACHE["loaded"] = True

    except Exception as e:
        _CANDIDATOS_CACHE["error"] = f"Error leyendo CandidatosPorMunicipio.csv: {str(e)}"


def asegurar_candidatos_cargados():
    """Carga el CSV una sola vez (cache)."""
    if not _CANDIDATOS_CACHE["loaded"] and _CANDIDATOS_CACHE["error"] is None:
        cargar_candidatos_desde_csv()


# Cargar al iniciar (si falla, quedará error en cache y lo veremos por logs)





def limpiar_numero(numero_raw):
    """Normaliza el número eliminando espacios, símbolos invisibles y caracteres no numéricos."""
    # Elimina símbolos Unicode raros y normaliza el texto
    numero = unicodedata.normalize("NFKD", str(numero_raw))
    # Elimina todo lo que no sea dígito
    numero = re.sub(r"\D", "", numero)
    # Asegura que tenga el prefijo +
    return f"+{numero}"


def enviar_mensaje_whatsapp(numero, mensaje):
    """Envía un mensaje por WhatsApp vía 360dialog."""
    try:
        token = os.environ.get("WABA_TOKEN")
        if not token:
            print("⚠️ WABA_TOKEN no está configurado.")
            return False

        resp = requests.post(
            "https://waba-v2.360dialog.io/messages",
            headers={
                "Content-Type": "application/json",
                "D360-API-KEY": token
            },
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": numero,
                "type": "text",
                "text": {"preview_url": False, "body": mensaje}
            },
            timeout=15
        )
        print("WhatsApp status:", resp.status_code, resp.text[:200])
        return 200 <= resp.status_code < 300
    except Exception as e:
        print("❌ Error enviando WhatsApp:", str(e))
        return False



# ---------------------------
# Configuración inicial
# ---------------------------
load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY", "clave-super-secreta")
app = Flask(__name__)
app.secret_key = SECRET_KEY

csrf = CSRFProtect(app)
serializer = URLSafeTimedSerializer(SECRET_KEY)

# ---------------------------
# Configuración de la base de datos
# ---------------------------
db_url = os.environ.get("DATABASE_URL", "sqlite:///votos.db")
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ---------------------------
# Cargar candidatos (1 sola vez)
# ---------------------------
asegurar_candidatos_cargados()
print("✅ CANDIDATOS loaded:", _CANDIDATOS_CACHE["loaded"])
print("⚠️ CANDIDATOS error:", _CANDIDATOS_CACHE["error"])
print("📌 CANDIDATOS path:", CANDIDATOS_CSV_PATH)



# ---------------------------
# Modelos
# ---------------------------
class Voto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False, index=True)
    genero = db.Column(db.String(10), nullable=False)
    pais = db.Column(db.String(100), nullable=False)
    departamento = db.Column(db.String(100), nullable=False)
    provincia = db.Column(db.String(100), nullable=False)
    id_municipio = db.Column(db.String(20), nullable=True)
    municipio = db.Column(db.String(100), nullable=False)
    recinto = db.Column(db.String(100), nullable=False)
    dia_nacimiento = db.Column(db.Integer, nullable=False)
    mes_nacimiento = db.Column(db.Integer, nullable=False)
    anio_nacimiento = db.Column(db.Integer, nullable=False)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    ip = db.Column(db.String(50), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    
    candidato = db.Column(db.String(100), nullable=False)
    pregunta3 = db.Column(db.String(10), nullable=False)
    ci = db.Column(db.BigInteger, nullable=True)



# ---------------------------
# NumeroTemporal
# ---------------------------
class NumeroTemporal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False)
    token = db.Column(db.Text, nullable=True)  # <--- Este campo debe existir
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class WhatsappMensajeProcesado(db.Model):
    __tablename__ = "whatsapp_mensajes_procesados"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(120), unique=True, nullable=False, index=True)
    numero = db.Column(db.String(50), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------------------
# Bloqueo WHatsapp
# ---------------------------
class BloqueoWhatsapp(db.Model):
    __tablename__ = "bloqueo_whatsapp"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False)
    intentos = db.Column(db.Integer, default=0)
    bloqueado = db.Column(db.Boolean, default=False)



with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print("❌ Error db.create_all():", str(e))


        


# ---------------------------
# Whatsapp
# ---------------------------

@app.route('/whatsapp', methods=['POST'])
@csrf.exempt
def whatsapp_webhook():
    try:
        # Lee JSON seguro (no rompe si viene vacío)
        data = request.get_json(force=True, silent=True) or {}
        print("📥 JSON recibido:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        # ====== Normalización del payload (360dialog / Meta Cloud) ======
        messages = None

        # Formato Meta (Graph API): entry -> changes -> value -> messages
        if isinstance(data, dict) and 'entry' in data:
            try:
                entry = (data.get('entry') or [])[0] or {}
                changes = (entry.get('changes') or [])[0] or {}
                value = changes.get('value', {}) or {}
                messages = value.get('messages')
            except Exception:
                messages = None

        # Formato "plano": { "messages": [...] }
        if not messages and isinstance(data, dict) and 'messages' in data:
            messages = data.get('messages')

        # Si no hay mensajes no procesamos
        if not messages:
            print("ℹ️ Webhook sin 'messages'; no hay nada que procesar.")
            return "ok", 200

        # Tomamos el primer mensaje
        msg = messages[0] or {}
        message_id = (msg.get("id") or "").strip()
        if message_id:
            ya = WhatsappMensajeProcesado.query.filter_by(message_id=message_id).first()
            if ya:
                print(f"ℹ️ Mensaje duplicado ignorado: {message_id}")
                return "ok", 200

            db.session.add(WhatsappMensajeProcesado(
                message_id=message_id,
                numero=numero_completo
            ))
            db.session.commit()


        # Número del remitente (MSISDN, a veces sin '+')
        numero_raw = msg.get('from') or msg.get('wa_id') or ""
        numero_completo = limpiar_numero(numero_raw)

        # Texto del mensaje (puede venir en diferentes campos)
        texto = ""
        if isinstance(msg.get('text'), dict):
            texto = (msg['text'].get('body') or "").strip()
        elif isinstance(msg.get('button'), dict):
            texto = (msg['button'].get('text') or "").strip()
        elif isinstance(msg.get('interactive'), dict):
            interactive = msg['interactive']
            if isinstance(interactive.get('button_reply'), dict):
                texto = (interactive['button_reply'].get('title') or "").strip()
            elif isinstance(interactive.get('list_reply'), dict):
                texto = (interactive['list_reply'].get('title') or "").strip()

        texto_lc = texto.lower()
        print(f"📨 Mensaje recibido de {numero_completo}: '{texto}'")

        # Triggers flexibles (no bloquea si no están; solo loguea)
        TRIGGERS = ("votar", "enlace", "link", "participar", "quiero votar")
        if not any(t in texto_lc for t in TRIGGERS):
            print("ℹ️ Mensaje sin palabra clave; continuaremos si el número está autorizado.")

        # ====== Verificación de bloqueo ======
        bloqueo = db.session.execute(
            db.select(BloqueoWhatsapp).where(BloqueoWhatsapp.numero == numero_completo)
        ).scalar_one_or_none()

        if bloqueo and bloqueo.bloqueado:
            print(f"🚫 Número bloqueado: {numero_completo}")
            return "ok", 200

        # ====== Verificación de autorización (debe existir en NumeroTemporal) ======
        autorizado = NumeroTemporal.query.filter_by(numero=numero_completo).first()
        if not autorizado:
            print(f"❌ Número NO autorizado: {numero_completo}")

            # Manejo de advertencias / bloqueo progresivo
            if not bloqueo:
                bloqueo = BloqueoWhatsapp(numero=numero_completo, intentos=1)
                db.session.add(bloqueo)
            else:
                bloqueo.intentos += 1
                if bloqueo.intentos >= 4:
                    bloqueo.bloqueado = True
            db.session.commit()

            if bloqueo.intentos < 4:
                advertencia = (
                    "⚠️ Para recibir tu enlace de votación, primero debes registrarte en el portal oficial:\n\n"
                    "👉 https://https://bit.ly/2davueltabk\n\n"
                    "Asegúrate de ingresar correctamente tu número de WhatsApp durante el registro, "
                    "ya que solo ese número podrá recibir el enlace.\n\n"
                    f"Advertencia {bloqueo.intentos}/3"
                )
            else:
                advertencia = (
                    "🚫 Has excedido el número de intentos permitidos. "
                    "Tus mensajes ya no serán respondidos por este sistema."
                )

            # Enviar advertencia (si hay token configurado)
            try:
                requests.post(
                    "https://waba-v2.360dialog.io/messages",
                    headers={
                        "Content-Type": "application/json",
                        "D360-API-KEY": os.environ.get("WABA_TOKEN")
                    },
                    json={
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": numero_completo,
                        "type": "text",
                        "text": {"preview_url": False, "body": advertencia}
                    },
                    timeout=15
                )
            except Exception as e:
                print("❌ Error enviando advertencia WhatsApp:", str(e))

            return "ok", 200

        # ====== Ya autorizado: recuperar token y enviar enlace ======
        if not autorizado.token:
            print(f"⚠️ No se encontró token almacenado para {numero_completo}")
            return "ok", 200

        # Dominios coherentes
# ====== Ya autorizado: generar token NUEVO y enviar enlace ======
        AZURE_DOMAIN = os.environ.get("AZURE_DOMAIN", request.host_url.rstrip('/')).rstrip('/')

        token_data = {
            "numero": numero_completo,
            "dominio": AZURE_DOMAIN
        }
        token_nuevo = serializer.dumps(token_data)

        # Guardar el token nuevo (reemplaza el viejo)
        autorizado.token = token_nuevo
        autorizado.fecha = datetime.utcnow()
        db.session.commit()

        link = f"{AZURE_DOMAIN}/votar?token={token_nuevo}"
        print(f"🔗 Enlace nuevo generado: {link}")

        print(f"🔗 Enlace recuperado: {link}")

        mensaje = (
            "Estás por ejercer un derecho fundamental como ciudadano boliviano.\n\n"
            "Participa en las *Primarias Bolivia 2025* y elige de manera libre y responsable.\n\n"
            f"Aquí tienes tu enlace único para votar (válido por 10 minutos):\n{link}\n\n"
            "Este enlace es personal e intransferible. Solo se permite un voto por persona.\n\n"
            "Gracias por ser parte del cambio que Bolivia necesita."
        )

        # Enviar mensaje con el enlace
        try:
            respuesta = requests.post(
                "https://waba-v2.360dialog.io/messages",
                headers={
                    "Content-Type": "application/json",
                    "D360-API-KEY": os.environ.get("WABA_TOKEN")
                },
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": numero_completo,
                    "type": "text",
                    "text": {"preview_url": False, "body": mensaje}
                },
                timeout=15
            )
            if 200 <= respuesta.status_code < 300:
                print("✅ Enlace enviado correctamente.")
            else:
                print(f"❌ Error al enviar mensaje WhatsApp: {respuesta.status_code} - {respuesta.text}")
        except Exception as e:
            print("❌ Error al enviar WhatsApp:", str(e))

    except Exception as e:
        print("❌ Error procesando webhook:", str(e))

    return "ok", 200


# ---------------------------
# Página principal
# ---------------------------
@app.route('/')
def index():
    return redirect('/generar_link')


# ---------------------------
# Generar Link
# ---------------------------

@app.route('/generar_link', methods=['GET', 'POST'])
def generar_link():
    if request.method == 'POST':
        pais = request.form.get('pais')
        numero = request.form.get('numero')

        if not pais or not numero:
            return "Por favor, selecciona un país e ingresa tu número."


        numero = numero.replace(" ", "").replace("-", "")
        pais = pais.strip()
        if not pais.startswith("+"):
            pais = f"+{pais}"  # agrega + si no está

        numero_completo = limpiar_numero(pais + numero)



        # Si ya votó, mostrar mensaje
        if Voto.query.filter_by(numero=numero_completo).first():
            return render_template("voto_ya_registrado.html")

        # Obtener dominio
        dominio = os.environ.get("AZURE_DOMAIN", request.host_url.rstrip('/')).rstrip('/')

        # Generar token único
        token_data = {
            "numero": numero_completo,
            "dominio": dominio
        }
        token = serializer.dumps(token_data)



        # Verificar si ya está registrado
        temporal = NumeroTemporal.query.filter_by(numero=numero_completo).first()

        if not temporal:
            temporal = NumeroTemporal(numero=numero_completo, token=token)
            db.session.add(temporal)
        else:
            # IMPORTANTE: reemplazar el token viejo por uno nuevo
            temporal.token = token
            temporal.fecha = datetime.utcnow()

        db.session.commit()


        # Redireccionar al WhatsApp con el mensaje prellenado
        return redirect("https://wa.me/59172902813?text=Hola,%20deseo%20participar%20en%20este%20proceso%20democrático%20porque%20creo%20en%20el%20cambio.%20Quiero%20ejercer%20mi%20derecho%20a%20votar%20de%20manera%20libre%20y%20responsable%20por%20el%20futuro%20de%20Bolivia.")

    return render_template("generar_link.html", paises=PAISES_CODIGOS)



# ---------------------------
# Página de votación
# ---------------------------

@app.route('/votar')
def votar():
    token = request.args.get('token')
    if not token:
        return "Acceso no válido."

    try:
  
        data = serializer.loads(token, max_age=600)  
        numero = limpiar_numero(data.get("numero"))
        registro = NumeroTemporal.query.filter_by(numero=numero, token=token).first()
        if not registro:
            enviar_mensaje_whatsapp(numero, "Este enlace ya fue utilizado o es inválido. Solicita uno nuevo.")
            return "Este enlace ya fue utilizado, es inválido o ha intentado manipular el proceso."




        dominio_token = data.get("dominio")
        dominio_esperado = os.environ.get("AZURE_DOMAIN")

        # Validación de dominio
        if dominio_token != dominio_esperado:
            return "Dominio inválido para este enlace."

    except SignatureExpired:
        return "El enlace ha expirado. Solicita uno nuevo."
    except BadSignature:
        return "Enlace inválido o alterado."

    # Verificar que el número esté en NumeroTemporal (aún válido)
    if not NumeroTemporal.query.filter_by(numero=numero).first():
        enviar_mensaje_whatsapp(numero, "Detectamos que intentó ingresar datos falsos. Por favor, use su número real o será bloqueado.")
        return "Este enlace ya fue utilizado, es inválido o ha intentado manipular el proceso."

    # Verificar si ya votó
    if Voto.query.filter_by(numero=numero).first():
        return render_template("voto_ya_registrado.html")

    # Guardar el número del token validado en sesión para comparación posterior segura
    session['numero_token'] = numero

    # Renderizar formulario y enviar el token también como campo oculto
    return render_template("votar.html", numero=numero, token=token)




# ---------------------------
# Enviar voto
# ---------------------------
@app.route('/enviar_voto', methods=['POST'])
def enviar_voto():

    referer = request.headers.get("Referer", "")
    dominio_permitido = os.environ.get("AZURE_DOMAIN", "votacionprimarias2025-g7ebaphpgrcucgbr.brazilsouth-01.azurewebsites.net")

    if referer and (dominio_permitido not in referer):
        return "Acceso no autorizado (referer inválido).", 403


    numero = session.get("numero_token")  # ← ✅ fuera del if
    if not numero:
        return "Acceso denegado: sin sesión válida o token expirado.", 403
    numero = limpiar_numero(numero)


    if not numero:
        return "Acceso denegado: sin sesión válida o token expirado.", 403

    # Campos requeridos
    genero = request.form.get('genero')
    pais = request.form.get('pais')
    departamento = request.form.get('departamento')
    provincia = request.form.get('provincia')
    id_municipio = request.form.get('id_municipio')
    municipio = request.form.get('municipio_nombre')
    recinto = request.form.get('recinto')
    dia = request.form.get('dia_nacimiento')
    mes = request.form.get('mes_nacimiento')
    anio = request.form.get('anio_nacimiento')
    
    candidato = request.form.get('candidato')
    pregunta3 = request.form.get('pregunta3')
    ci = request.form.get('ci') or None
    latitud = request.form.get('latitud')
    longitud = request.form.get('longitud')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()


    if not all([genero, pais, departamento, provincia, municipio, id_municipio, recinto,
                dia, mes, anio, candidato, pregunta3]):
        return render_template("faltan_campos.html")



    if pregunta3 == "Sí" and not ci:
        return "Debes ingresar tu CI si respondes que colaborarás en el control del voto.", 400

    if ci:
        try:
            ci = int(ci)
        except ValueError:
            return "CI inválido.", 400

    if Voto.query.filter_by(numero=numero).first():
        return render_template("voto_ya_registrado.html")

    nuevo_voto = Voto(
        numero=numero,
        genero=genero,
        pais=pais,
        departamento=departamento,
        provincia=provincia,
        id_municipio=id_municipio,
        municipio=municipio,        # nombre
        recinto=recinto,
        dia_nacimiento=int(dia),
        mes_nacimiento=int(mes),
        anio_nacimiento=int(anio),
        latitud=float(latitud) if latitud else None,
        longitud=float(longitud) if longitud else None,
        ip=ip,
        candidato=candidato,
        pregunta3=pregunta3,
        ci=ci
        
    )

    db.session.add(nuevo_voto)
    NumeroTemporal.query.filter_by(numero=numero).delete()
    db.session.commit()
    session.pop('numero_token', None)

    return render_template("voto_exitoso.html",
                           numero=numero,
                           genero=genero,
                           pais=pais,
                           departamento=departamento,
                           provincia=provincia,
                           municipio=municipio,
                           recinto=recinto,
                           dia=dia,
                           mes=mes,
                           anio=anio,
                           candidato=candidato)





# ---------------------------
# API local desde CSV con validación de origen (Referer)
# ---------------------------
@app.route('/api/recintos')
def api_recintos():
    # Validación del dominio de origen (protección básica)
    referer = request.headers.get("Referer", "")
    dominio_esperado = os.environ.get(
        "AZURE_DOMAIN",
        "votacionprimarias2025-g7ebaphpgrcucgbr.brazilsouth-01.azurewebsites.net"
    )

    # OJO: a veces el Referer viene vacío por privacidad del navegador.
    # Si te da 403, más abajo te digo cómo ajustarlo.
    if referer and (dominio_esperado not in referer):
        return "Acceso no autorizado", 403


    archivo = os.path.join(os.path.dirname(__file__), "privado", "RecintosParaPrimaria.csv")
    datos = []

    try:
        with open(archivo, encoding="utf-8-sig") as f:
            lector = csv.DictReader(f)

            required = {
                "id_pais", "nombre_pais",
                "id_departamento", "nombre_departamento",
                "id_provincia", "nombre_provincia",
                "id_municipio", "nombre_municipio",
                "id_recinto", "nombre_recinto",
            }
            headers = set(lector.fieldnames or [])
            faltantes = required - headers
            if faltantes:
                print("Faltan columnas en RecintosParaPrimaria.csv:", faltantes)
                return "CSV de recintos con columnas incompletas.", 500

            for fila in lector:
                datos.append({
                    "id_pais": str(fila.get("id_pais") or "").strip(),
                    "nombre_pais": (fila.get("nombre_pais") or "").strip(),

                    "id_departamento": str(fila.get("id_departamento") or "").strip(),
                    "nombre_departamento": (fila.get("nombre_departamento") or "").strip(),

                    "id_provincia": str(fila.get("id_provincia") or "").strip(),
                    "nombre_provincia": (fila.get("nombre_provincia") or "").strip(),

                    # CLAVE PARA EL PASO 3/4:
                    "id_municipio": str(fila.get("id_municipio") or "").strip(),
                    "nombre_municipio": (fila.get("nombre_municipio") or "").strip(),

                    "id_recinto": str(fila.get("id_recinto") or "").strip(),
                    "nombre_recinto": (fila.get("nombre_recinto") or "").strip(),

                    # extras opcionales (si existen)
                    "direccion": (fila.get("Direccion") or "").strip(),
                    "latitud": (fila.get("latitud") or "").strip(),
                    "longitud": (fila.get("longitud") or "").strip(),
                })

        return jsonify(datos)

    except FileNotFoundError:
        print("Archivo RecintosParaPrimaria.csv no encontrado en privado/.")
        return "Archivo de recintos no disponible.", 500
    except Exception as e:
        print(f"Error al leer CSV recintos: {str(e)}")
        return "Error procesando los datos.", 500


@app.route("/api/candidatos")
def api_candidatos():
    id_municipio = request.args.get("id_municipio")

    if not id_municipio:
        return jsonify([])

    # 1️⃣ BUSCAR el municipio real en RecintosParaPrimaria.csv
    archivo_recintos = os.path.join(
        os.path.dirname(__file__),
        "privado",
        "RecintosParaPrimaria.csv"
    )

    departamento = None
    provincia = None
    municipio = None

    with open(archivo_recintos, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            if fila["id_municipio"] == id_municipio:
                departamento = fila["nombre_departamento"].strip().lower()
                provincia = fila["nombre_provincia"].strip().lower()
                municipio = fila["nombre_municipio"].strip().lower()
                break

    # Si no se encontró el municipio
    if not municipio:
        return jsonify([])

    # 2️⃣ BUSCAR candidatos por departamento + provincia + municipio
    archivo_candidatos = os.path.join(
        os.path.dirname(__file__),
        "privado",
        "CandidatosPorMunicipio.csv"
    )

    candidatos = []

    with open(archivo_candidatos, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            if (
                fila["departamento"].strip().lower() == departamento and
                fila["provincia"].strip().lower() == provincia and
                fila["municipio"].strip().lower() == municipio and
                fila["cargo"].strip().lower() == "alcalde"
            ):
                candidatos.append({
                    "id_nombre_completo": fila["id_nombre_completo"],
                    "nombre_completo": fila["nombre_completo"],
                    "organizacion_politica": fila["organizacion_politica"],
                    "id_organizacion_politica": fila["id_organizacion_politica"],
                    "id_cargo": fila["id_cargo"],
                    "cargo": fila["cargo"]
                })

    return jsonify(candidatos)


# ---------------------------
# Página de preguntas frecuentes
# ---------------------------
@app.route('/preguntas')
def preguntas_frecuentes():
    return render_template("preguntas.html")

# ---------------------------
# Ejecutar localmente
# ---------------------------
if __name__ == '__main__':
    app.run(debug=True)
