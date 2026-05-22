import os
import json
import logging
import asyncio
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ChatJoinRequestHandler, CallbackQueryHandler, CommandHandler, ContextTypes
from telegram.error import TelegramError

# Configurar logs para Render
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

CHANNELS_FILE = "required_channels.json"
PENDING_FILE = "pending_requests.json"

# --- CONFIGURACIÓN POR VARIABLES DE ENTORNO ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Convertimos la cadena de texto separada por comas en una lista de enteros
canales_raw = os.getenv("CANALES_PRINCIPALES", "")
CANALES_PRINCIPALES = [int(x.strip()) for x in canales_raw.split(",") if x.strip().replace("-", "").isdigit()]
# ----------------------------------------------

# --- SERVIDOR WEB MINI PARA ENGAÑAR A RENDER ---
def run_health_server():
    # Render asigna automáticamente un puerto en la variable PORT
    port = int(os.getenv("PORT", 8080))
    server_address = ('', port)
    
    class HealthHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Bot activo y respondiendo")

    httpd = HTTPServer(server_address, HealthHandler)
    print(f"🌍 Servidor de respuesta web iniciado en el puerto {port}")
    httpd.serve_forever()
# -----------------------------------------------

def load_channels():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r") as f:
                content = f.read().strip()
                return json.loads(content) if content else []
        except json.JSONDecodeError:
            return []
    return []

def save_channels(channels):
    with open(CHANNELS_FILE, "w") as f:
        json.dump(channels, f, indent=4)

def load_pending():
    if os.path.exists(PENDING_FILE):
        try:
            with open(PENDING_FILE, "r") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except json.JSONDecodeError:
            return {}
    return []

def save_pending(pending):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=4)

async def is_user_member(app, user_id):
    channels = load_channels()
    if not channels:
        return True
    for ch_data in channels:
        target_id = ch_data.get("id")
        if not target_id: continue
        try:
            member = await app.bot.get_chat_member(chat_id=target_id, user_id=user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                return False
        except TelegramError:
            return False
    return True

def get_requirements_keyboard():
    channels = load_channels()
    keyboard = []
    for i, ch_data in enumerate(channels, 1):
        keyboard.append([InlineKeyboardButton(text=f"📢 Unirse al Canal Requisito {i}", url=ch_data.get("link"))])
    keyboard.append([InlineKeyboardButton(text="🔄 Verificar y Aceptar", callback_data="refresh_status")])
    return InlineKeyboardMarkup(keyboard)

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    user_id = request.from_user.id
    chat_id = request.chat.id
    
    if chat_id not in CANALES_PRINCIPALES: return
    if await is_user_member(context.application, user_id):
        try: 
            await request.approve()
            return
        except TelegramError: 
            pass
            
    pending = load_pending()
    pending[str(user_id)] = chat_id
    save_pending(pending)
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"¡Hola! Recibimos tu solicitud para entrar a {request.chat.title}.\n\nPara que el sistema te apruebe automáticamente, primero debes unirte a los siguientes canales requeridos:",
            reply_markup=get_requirements_keyboard()
        )
    except TelegramError: 
        pass

async def handle_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    pending = load_pending()
    chat_id = pending.get(str(user_id))
    
    if not chat_id:
        await query.edit_message_text("No encontré solicitudes pendientes.")
        return

    if await is_user_member(context.application, user_id):
        try:
            await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            await query.edit_message_text("¡Perfecto! Todo verificado. Tu solicitud ha sido aceptada.")
            del pending[str(user_id)]
            save_pending(pending)
        except TelegramError as e:
            await query.edit_message_text(f"Hubo un error: {e.message}")
    else:
        await query.answer("❌ Error: Aún no te has unido a todos los canales.", show_alert=True)

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("⚠️ Uso: /add -100ID_DEL_CANAL")
        return
    try:
        chan_id = int(context.args[0])
        invite_link_obj = await context.bot.create_chat_invite_link(chat_id=chan_id, name="Bot Requisitos")
        generated_link = invite_link_obj.invite_link
        channels = load_channels()
        channels.append({"id": chan_id, "link": generated_link})
        save_channels(channels)
        await update.message.reply_text(f"✅ Vinculado:\n🆔 ID: {chan_id}\n🔗 Link: {generated_link}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    channels = load_channels()
    if not channels: 
        return await update.message.reply_text("Lista vacía.")
    msg = "Canales obligatorios:\n" + "\n".join([f"- ID: {ch['id']} ➡️ Link: {ch['link']}" for ch in channels])
    await update.message.reply_text(msg)

async def clear_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    save_channels([])
    await update.message.reply_text("🧹 Lista vacía.")

def main():
    if not TELEGRAM_TOKEN or not ADMIN_ID or not CANALES_PRINCIPALES:
        print("❌ ERROR: Faltan variables de entorno obligatorias (TELEGRAM_TOKEN, ADMIN_ID o CANALES_PRINCIPALES).")
        return

    # Lanzar el servidor web falso en un hilo secundario para que Render valide el puerto
    web_thread = threading.Thread(target=run_health_server, daemon=True)
    web_thread.start()

    # Configuración del Bot de Telegram
    ptb_app = Application.builder().token(TELEGRAM_TOKEN).build()

    ptb_app.add_handler(ChatJoinRequestHandler(handle_join_request))
    ptb_app.add_handler(CallbackQueryHandler(handle_refresh, pattern="refresh_status"))
    ptb_app.add_handler(CommandHandler("add", add_channel))
    ptb_app.add_handler(CommandHandler("list", list_channels))
    ptb_app.add_handler(CommandHandler("clear", clear_channels))

    print("🚀 Bot iniciado en Render con Polling y Servidor Web integrado...")
    
    # --- FIX ASYNCIO PARA PYTHON 3.14 ---
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    ptb_app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == '__main__':
    main()
