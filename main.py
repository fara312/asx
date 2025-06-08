import os
import random
import logging
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные среды
BOT_TOKEN = os.getenv("YOUR_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7366365871"))  # Укажи свой Telegram ID в Secrets

QUIZ_FILE = 'shintasov.txt'
ALLOWED_USERS_FILE = 'allowed_users.txt'

# Flask веб-сервер
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot is running"

def run_flask():
    app_flask.run(host='0.0.0.0', port=8080)

# Загрузка разрешённых пользователей
def load_allowed_users():
    if not os.path.exists(ALLOWED_USERS_FILE):
        return set()
    with open(ALLOWED_USERS_FILE, 'r') as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

allowed_users = load_allowed_users()

def parse_quiz_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    blocks = content.split('\n\n')
    questions = []

    for block in blocks:
        lines = [line.strip() for line in block.strip().split('\n') if line.strip()]
        if not lines:
            continue

        question = lines[0]
        options = []
        correct_index = -1

        for i, line in enumerate(lines[1:]):
            if line.startswith('+'):
                options.append(line[1:].strip())
                correct_index = i
            elif line.startswith('-'):
                options.append(line[1:].strip())
            else:
                raise ValueError(f"Ошибка формата в строке: {line}")

        if correct_index == -1:
            raise ValueError(f"❌ Не найден правильный ответ в вопросе: {question}")

        questions.append({
            'question': question,
            'options': options,
            'correct_index': correct_index
        })

    return questions

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in allowed_users:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Разрешить", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"deny_{user_id}")
            ]
        ])
        await update.message.reply_text("⏳ Запрос отправлен администратору. кут наку.")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🛂 Новый пользователь просит доступ:\nID: {user_id}",
            reply_markup=keyboard
        )
        return
    await update.message.reply_text("Группалас калайсын /quiz наны бассиш шынтасов ко нау.")

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in allowed_users:
        await update.message.reply_text("⛔️ У вас нет доступа. Напишите /start чтобы запросить доступ.")
        return
    try:
        questions = parse_quiz_file(QUIZ_FILE)
        random.shuffle(questions)

        context.user_data['questions'] = questions
        context.user_data['current_q'] = 0
        context.user_data['score'] = 0

        await send_question(update, context)

    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке теста: {e}")

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = context.user_data['current_q']
    questions = context.user_data['questions']

    if current >= len(questions):
        score = context.user_data['score']
        total = len(questions)
        await update.message.reply_text(
            f"биттниба не! Правильных ответов: {score} из {total}.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    question_data = questions[current]
    options = question_data['options']
    correct_idx = question_data['correct_index']

    indexed_options = list(enumerate(options))
    random.shuffle(indexed_options)

    for new_idx, (old_idx, option) in enumerate(indexed_options):
        if old_idx == correct_idx:
            new_correct_index = new_idx
            break

    context.user_data['correct_option'] = new_correct_index

    text = f"Вопрос {current + 1}:\n{question_data['question']}\n\n"
    for i, (_, option) in enumerate(indexed_options):
        text += f"{i + 1}. {option}\n"

    await update.message.reply_text(text)

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'questions' not in context.user_data:
        await update.message.reply_text("Пожалуйста, начните тест командой /quiz.")
        return

    current = context.user_data['current_q']
    questions = context.user_data['questions']

    if current >= len(questions):
        await update.message.reply_text("Тест уже завершён. Напишите /quiz чтобы начать заново.")
        return

    user_answer = update.message.text.strip()
    if not user_answer.isdigit():
        await update.message.reply_text("Пожалуйста, отправьте номер варианта (цифру).")
        return

    selected = int(user_answer) - 1
    correct_option = context.user_data.get('correct_option', -1)

    if selected == correct_option:
        context.user_data['score'] += 1
        await update.message.reply_text("✅ Правильно!")
    else:
        correct_answer_text = questions[current]['options'][questions[current]['correct_index']]
        await update.message.reply_text(f"❌ Неправильно! Правильный ответ: {correct_answer_text}")

    context.user_data['current_q'] += 1
    await send_question(update, context)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("approve_"):
        user_id = int(data.split("_")[1])
        if user_id not in allowed_users:
            allowed_users.add(user_id)
            with open(ALLOWED_USERS_FILE, "a") as f:
                f.write(f"{user_id}\n")
        await context.bot.send_message(chat_id=user_id, text="✅ Вам разрешен доступ. Напишите /quiz.")
        await query.edit_message_text(f"✅ Пользователю {user_id} разрешён доступ.")
    elif data.startswith("deny_"):
        user_id = int(data.split("_")[1])
        await context.bot.send_message(chat_id=user_id, text="❌ Доступ отклонён администратором.")
        await query.edit_message_text(f"❌ Пользователю {user_id} отказано в доступе.")

# Основной запуск
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Бот запущен ✅")
    app.run_polling()
