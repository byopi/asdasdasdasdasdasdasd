import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from groq import Groq
from flask import Flask
import threading

TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ID_CANAL_LOGS = os.getenv("ID_CANAL_LOGS", "-100XXXXXXXXXX") 
LINK_CANAL_PROMO = "https://t.me/samugpt"

client = Groq(api_key=GROQ_API_KEY)
user_db = {}

app = Flask(__name__)

@app.route('/')
def health_check():
    return "SamuGPT Status: Active", 200

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    keyboard = [[InlineKeyboardButton("🙈 CANAL DE ACTUALIZACIONES 🆕", url=LINK_CANAL_PROMO)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Tu nuevo mensaje de inicio
    bienvenida = (
        f"Que fue, {user_name} 👋\n\n"
        "Soy **SamuGPT**, un dictador que se cansó de OSM y ahora se convirtió en IA. "
        "Pregúntame lo que sea y te responderé asere, te quiero :).\n\n"
        "👇 Únete abajo para ver actualizaciones."
    )
    
    await update.message.reply_text(bienvenida, reply_markup=reply_markup, parse_mode="Markdown")

async def logger_to_channel(context, user_id, username, question):
    mensaje = f"📊 **GROQ LOG**\n👤 {username}\n🆔 `{user_id}`\n❓ {question}"
    try:
        await context.bot.send_message(chat_id=ID_CANAL_LOGS, text=mensaje, parse_mode="Markdown")
    except:
        pass

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.effective_user.id
    username = f"@{update.effective_user.username}" or update.effective_user.first_name
    user_text = update.message.text
    ahora = datetime.now().date()

    if user_id not in user_db or user_db[user_id]["fecha"] != ahora:
        user_db[user_id] = {"fecha": ahora, "conteo": 0}

    if user_db[user_id]["conteo"] >= 50:
        await update.message.reply_text("Ya te pasaste de los 50 mensajes por hoy, asere.")
        return

    try:
        await logger_to_channel(context, user_id, username, user_text)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": user_text}],
            model="llama-3.1-8b-instant",
        )
        await update.message.reply_text(chat_completion.choices[0].message.content)
        user_db[user_id]["conteo"] += 1
    except Exception as e:
        await update.message.reply_text("Error técnico con Groq, intenta luego.")

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    bot_app = ApplicationBuilder().token(TOKEN_TELEGRAM).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder))
    bot_app.run_polling()

if __name__ == '__main__':
    main()
