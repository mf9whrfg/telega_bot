import logging
import os
import json
import random
import threading
from datetime import datetime
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler, ConversationHandler
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [7877332060]
DB_FILE = 'database.json'

app = Flask(__name__)

@app.route('/')
def health_check():
    return 'Bot is running!'

def run_web_server():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# ─── DATABASE ────────────────────────────────────────────────────────────────

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    db = load_db()
    uid = str(user_id)
    return db.get(uid)

def save_user(user_id, data):
    db = load_db()
    db[str(user_id)] = data
    save_db(db)

def create_user(user_id, username, region):
    currencies = {'ru': ('рублей', '₽'), 'ua': ('гривен', '₴'), 'en': ('долларов', '$')}
    cur_name, cur_sym = currencies[region]
    user = {
        'id': user_id,
        'username': username or 'Аноним',
        'region': region,
        'currency_name': cur_name,
        'currency_symbol': cur_sym,
        'balance': 100,
        'banned': False,
        'registered': datetime.now().isoformat(),
        'games_played': 0,
        'total_won': 0,
        'total_lost': 0,
    }
    save_user(user_id, user)
    return user

# ─── CURRENCY HELPER ─────────────────────────────────────────────────────────

def fmt(user, amount):
    return f"{amount} {user['currency_symbol']}"

# ─── KEYBOARDS ───────────────────────────────────────────────────────────────

def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🎰 Казино"), KeyboardButton("🎮 Игры")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("⚙️ Настройки")],
    ], resize_keyboard=True)

def casino_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🎰 Слоты"), KeyboardButton("🎡 Рулетка")],
        [KeyboardButton("🃏 Дурак"), KeyboardButton("🔙 Назад")],
    ], resize_keyboard=True)

def games_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🎲 Кубик"), KeyboardButton("🪙 Орёл/Решка")],
        [KeyboardButton("✂️ Камень-Ножницы-Бумага"), KeyboardButton("🔙 Назад")],
    ], resize_keyboard=True)

def settings_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🌍 Сменить регион"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🔙 Назад")],
    ], resize_keyboard=True)

def admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("💰 Выдать монеты"), KeyboardButton("💸 Забрать монеты")],
        [KeyboardButton("🚫 Забанить"), KeyboardButton("✅ Разбанить")],
        [KeyboardButton("📋 Список игроков"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("🔙 Назад")],
    ], resize_keyboard=True)

def region_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇷🇺 Россия (рубли ₽)", callback_data='region_ru')],
        [InlineKeyboardButton("🇺🇦 Украина (гривны ₴)", callback_data='region_ua')],
        [InlineKeyboardButton("🌐 Другое (доллары $)", callback_data='region_en')],
    ])

def slots_bet_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data='slots_1'),
         InlineKeyboardButton("5", callback_data='slots_5'),
         InlineKeyboardButton("10", callback_data='slots_10')],
        [InlineKeyboardButton("25", callback_data='slots_25'),
         InlineKeyboardButton("50", callback_data='slots_50'),
         InlineKeyboardButton("100", callback_data='slots_100')],
    ])

def roulette_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Красное (x2)", callback_data='rou_red'),
         InlineKeyboardButton("⚫ Чёрное (x2)", callback_data='rou_black')],
        [InlineKeyboardButton("🟢 Зеро (x14)", callback_data='rou_zero')],
        [InlineKeyboardButton("1️⃣ Чётное (x2)", callback_data='rou_even'),
         InlineKeyboardButton("2️⃣ Нечётное (x2)", callback_data='rou_odd')],
    ])

def roulette_bet_keyboard(color):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data=f'roubet_{color}_1'),
         InlineKeyboardButton("5", callback_data=f'roubet_{color}_5'),
         InlineKeyboardButton("10", callback_data=f'roubet_{color}_10')],
        [InlineKeyboardButton("25", callback_data=f'roubet_{color}_25'),
         InlineKeyboardButton("50", callback_data=f'roubet_{color}_50'),
         InlineKeyboardButton("100", callback_data=f'roubet_{color}_100')],
    ])

def knb_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪨 Камень", callback_data='knb_rock'),
         InlineKeyboardButton("✂️ Ножницы", callback_data='knb_scissors'),
         InlineKeyboardButton("📄 Бумага", callback_data='knb_paper')],
    ])

# ─── BAN CHECK ───────────────────────────────────────────────────────────────

async def check_banned(update, user):
    if user and user.get('banned'):
        await update.message.reply_text("🚫 Вы заблокированы в этом боте.")
        return True
    return False

# ─── START / REGION ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if user:
        if user.get('banned'):
            await update.message.reply_text("🚫 Вы заблокированы.")
            return
        await update.message.reply_text(
            f"👋 С возвращением, {user['username']}!\n💰 Баланс: {fmt(user, user['balance'])}",
            reply_markup=main_menu_keyboard()
        )
        return

    await update.message.reply_text(
        "🌍 Добро пожаловать в казино-бот!\n\n"
        "Выберите ваш регион — это определит валюту в боте:\n\n"
        "🇷🇺 Россия → рубли (₽)\n"
        "🇺🇦 Украина → гривны (₴)\n"
        "🌐 Другое → доллары ($)",
        reply_markup=region_keyboard()
    )

async def region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    region = query.data.replace('region_', '')
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    user = create_user(user_id, username, region)

    region_names = {'ru': '🇷🇺 Россия', 'ua': '🇺🇦 Украина', 'en': '🌐 Другое'}
    await query.edit_message_text(
        f"✅ Регион выбран: {region_names[region]}\n"
        f"💰 Стартовый баланс: {fmt(user, user['balance'])}\n\n"
        f"Добро пожаловать! Удачи в игре!"
    )
    await query.message.reply_text("🎰 Главное меню:", reply_markup=main_menu_keyboard())

# ─── MAIN MENU HANDLER ───────────────────────────────────────────────────────

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    text = update.message.text

    if not user:
        await start(update, context)
        return

    if await check_banned(update, user):
        return

    if text == "🎰 Казино":
        await update.message.reply_text("🎰 Выберите игру:", reply_markup=casino_keyboard())

    elif text == "🎮 Игры":
        await update.message.reply_text("🎮 Выберите игру:", reply_markup=games_keyboard())

    elif text == "👤 Профиль":
        region_names = {'ru': '🇷🇺 Россия', 'ua': '🇺🇦 Украина', 'en': '🌐 Другое'}
        await update.message.reply_text(
            f"👤 Профиль\n\n"
            f"🆔 ID: {user['id']}\n"
            f"👤 Username: @{user['username']}\n"
            f"🌍 Регион: {region_names.get(user['region'], '?')}\n"
            f"💰 Баланс: {fmt(user, user['balance'])}\n"
            f"🎮 Игр сыграно: {user['games_played']}\n"
            f"📈 Выиграно: {fmt(user, user['total_won'])}\n"
            f"📉 Проиграно: {fmt(user, user['total_lost'])}\n"
            f"📅 Регистрация: {user['registered'][:10]}",
            reply_markup=main_menu_keyboard()
        )

    elif text == "⚙️ Настройки":
        await update.message.reply_text("⚙️ Настройки:", reply_markup=settings_keyboard())

    elif text == "🔙 Назад":
        if user_id in ADMIN_IDS:
            await update.message.reply_text("Главное меню:", reply_markup=main_menu_keyboard())
        else:
            await update.message.reply_text("Главное меню:", reply_markup=main_menu_keyboard())

    elif text == "🌍 Сменить регион":
        await update.message.reply_text(
            "🌍 Выберите новый регион:",
            reply_markup=region_keyboard()
        )

    elif text == "📊 Статистика":
        db = load_db()
        total_users = len(db)
        await update.message.reply_text(
            f"📊 Статистика бота\n\n"
            f"👥 Всего игроков: {total_users}\n"
            f"💰 Ваш баланс: {fmt(user, user['balance'])}",
            reply_markup=settings_keyboard()
        )

    # ── CASINO ──
    elif text == "🎰 Слоты":
        await update.message.reply_text(
            f"🎰 Слоты\n💰 Ваш баланс: {fmt(user, user['balance'])}\n\nВыберите ставку:",
            reply_markup=slots_bet_keyboard()
        )

    elif text == "🎡 Рулетка":
        await update.message.reply_text(
            f"🎡 Рулетка\n💰 Ваш баланс: {fmt(user, user['balance'])}\n\nВыберите цвет/тип:",
            reply_markup=roulette_keyboard()
        )

    elif text == "🃏 Дурак":
        await start_durak(update, context, user)

    # ── GAMES ──
    elif text == "🎲 Кубик":
        result = random.randint(1, 6)
        faces = ['⚀','⚁','⚂','⚃','⚄','⚅']
        await update.message.reply_text(
            f"🎲 Бросаю кубик...\n\nВыпало: {faces[result-1]} ({result})",
            reply_markup=games_keyboard()
        )

    elif text == "🪙 Орёл/Решка":
        result = random.choice(["🦅 Орёл", "🔵 Решка"])
        await update.message.reply_text(
            f"🪙 Подбрасываю монету...\n\nВыпало: {result}",
            reply_markup=games_keyboard()
        )

    elif text == "✂️ Камень-Ножницы-Бумага":
        await update.message.reply_text(
            "✂️ Камень-Ножницы-Бумага\n\nВыберите:",
            reply_markup=knb_keyboard()
        )

    # ── ADMIN ──
    elif text == "🔐 Админ-панель" and user_id in ADMIN_IDS:
        await update.message.reply_text("🔐 Админ-панель:", reply_markup=admin_keyboard())

    elif text == "💰 Выдать монеты" and user_id in ADMIN_IDS:
        context.user_data['admin_action'] = 'give'
        await update.message.reply_text("Введите: ID пользователя и сумму\nПример: 123456789 500")

    elif text == "💸 Забрать монеты" and user_id in ADMIN_IDS:
        context.user_data['admin_action'] = 'take'
        await update.message.reply_text("Введите: ID пользователя и сумму\nПример: 123456789 500")

    elif text == "🚫 Забанить" and user_id in ADMIN_IDS:
        context.user_data['admin_action'] = 'ban'
        await update.message.reply_text("Введите ID пользователя для бана:")

    elif text == "✅ Разбанить" and user_id in ADMIN_IDS:
        context.user_data['admin_action'] = 'unban'
        await update.message.reply_text("Введите ID пользователя для разбана:")

    elif text == "📋 Список игроков" and user_id in ADMIN_IDS:
        db = load_db()
        lines = []
        for uid, u in db.items():
            ban = "🚫" if u.get('banned') else "✅"
            lines.append(f"{ban} @{u['username']} | {u['id']} | {fmt(u, u['balance'])}")
        msg = "\n".join(lines[:30]) if lines else "Нет игроков"
        await update.message.reply_text(f"📋 Игроки:\n\n{msg}", reply_markup=admin_keyboard())

    elif text == "📢 Рассылка" and user_id in ADMIN_IDS:
        context.user_data['admin_action'] = 'broadcast'
        await update.message.reply_text("Введите текст рассылки:")

    else:
        # Admin text input handling
        action = context.user_data.get('admin_action')
        if action and user_id in ADMIN_IDS:
            await handle_admin_input(update, context, action, text, user)
            context.user_data.pop('admin_action', None)

# ─── ADMIN INPUT ─────────────────────────────────────────────────────────────

async def handle_admin_input(update, context, action, text, admin_user):
    if action in ('give', 'take'):
        parts = text.strip().split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await update.message.reply_text("❌ Формат: ID сумма\nПример: 123456789 500")
            return
        target_id, amount = int(parts[0]), int(parts[1])
        target = get_user(target_id)
        if not target:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        if action == 'give':
            target['balance'] += amount
            save_user(target_id, target)
            await update.message.reply_text(f"✅ Выдано {fmt(target, amount)} пользователю @{target['username']}")
        else:
            target['balance'] = max(0, target['balance'] - amount)
            save_user(target_id, target)
            await update.message.reply_text(f"✅ Забрано {fmt(target, amount)} у @{target['username']}")

    elif action == 'ban':
        if not text.strip().isdigit():
            await update.message.reply_text("❌ Введите числовой ID")
            return
        target = get_user(int(text.strip()))
        if not target:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        target['banned'] = True
        save_user(int(text.strip()), target)
        await update.message.reply_text(f"🚫 @{target['username']} заблокирован")

    elif action == 'unban':
        if not text.strip().isdigit():
            await update.message.reply_text("❌ Введите числовой ID")
            return
        target = get_user(int(text.strip()))
        if not target:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        target['banned'] = False
        save_user(int(text.strip()), target)
        await update.message.reply_text(f"✅ @{target['username']} разблокирован")

    elif action == 'broadcast':
        db = load_db()
        sent = 0
        for uid in db:
            try:
                await context.bot.send_message(int(uid), f"📢 Сообщение от администратора:\n\n{text}")
                sent += 1
            except:
                pass
        await update.message.reply_text(f"✅ Рассылка отправлена {sent} пользователям")

# ─── SLOTS ───────────────────────────────────────────────────────────────────

SLOT_EMOJIS = ['🍒', '🍋', '🍊', '🍇', '⭐', '💎', '7️⃣']

async def slots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    if not user:
        return

    bet = int(query.data.replace('slots_', ''))
    if user['balance'] < bet:
        await query.edit_message_text(f"❌ Недостаточно средств! Баланс: {fmt(user, user['balance'])}")
        return

    s1, s2, s3 = random.choices(SLOT_EMOJIS, k=3)
    user['balance'] -= bet
    user['games_played'] += 1

    if s1 == s2 == s3:
        win = bet * 10
        result = f"🎉 ДЖЕКПОТ! Выиграли {fmt(user, win)}!"
        user['balance'] += win
        user['total_won'] += win
    elif s1 == s2 or s2 == s3 or s1 == s3:
        win = bet * 2
        result = f"✅ Два одинаковых! Выиграли {fmt(user, win)}!"
        user['balance'] += win
        user['total_won'] += win
    else:
        result = f"❌ Не повезло! Потеряли {fmt(user, bet)}"
        user['total_lost'] += bet

    save_user(user_id, user)
    await query.edit_message_text(
        f"🎰 Слоты\n\n[ {s1} | {s2} | {s3} ]\n\n{result}\n\n💰 Баланс: {fmt(user, user['balance'])}",
        reply_markup=slots_bet_keyboard()
    )

# ─── ROULETTE ────────────────────────────────────────────────────────────────

RED_NUMBERS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

async def roulette_color_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    color = query.data.replace('rou_', '')
    color_names = {'red': '🔴 Красное', 'black': '⚫ Чёрное', 'zero': '🟢 Зеро', 'even': 'Чётное', 'odd': 'Нечётное'}
    user_id = query.from_user.id
    user = get_user(user_id)
    await query.edit_message_text(
        f"🎡 Рулетка\nВы выбрали: {color_names[color]}\n💰 Баланс: {fmt(user, user['balance'])}\n\nВыберите ставку:",
        reply_markup=roulette_bet_keyboard(color)
    )

async def roulette_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, color, bet_str = query.data.split('_', 2)
    bet = int(bet_str)
    user_id = query.from_user.id
    user = get_user(user_id)

    if user['balance'] < bet:
        await query.edit_message_text(f"❌ Недостаточно средств! Баланс: {fmt(user, user['balance'])}")
        return

    number = random.randint(0, 36)
    is_red = number in RED_NUMBERS
    is_zero = number == 0
    is_even = number != 0 and number % 2 == 0

    if is_zero:
        spin_result = f"🟢 Зеро ({number})"
    elif is_red:
        spin_result = f"🔴 {number}"
    else:
        spin_result = f"⚫ {number}"

    user['balance'] -= bet
    user['games_played'] += 1
    win = 0

    won = False
    if color == 'red' and is_red:
        win = bet * 2
        won = True
    elif color == 'black' and not is_red and not is_zero:
        win = bet * 2
        won = True
    elif color == 'zero' and is_zero:
        win = bet * 14
        won = True
    elif color == 'even' and is_even:
        win = bet * 2
        won = True
    elif color == 'odd' and not is_even and not is_zero:
        win = bet * 2
        won = True

    if won:
        user['balance'] += win
        user['total_won'] += win
        result = f"🎉 Выиграли {fmt(user, win)}!"
    else:
        user['total_lost'] += bet
        result = f"❌ Не повезло! Потеряли {fmt(user, bet)}"

    save_user(user_id, user)
    await query.edit_message_text(
        f"🎡 Рулетка\n\nШарик упал на: {spin_result}\n\n{result}\n\n💰 Баланс: {fmt(user, user['balance'])}",
        reply_markup=roulette_keyboard()
    )

# ─── DURAK (упрощённый через сообщения) ──────────────────────────────────────

DURAK_SUITS = ['♠️', '♥️', '♦️', '♣️']
DURAK_RANKS = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

def make_deck():
    return [f"{r}{s}" for r in DURAK_RANKS for s in DURAK_SUITS]

def card_rank(card):
    rank = card[:-2] if len(card) > 3 else card[0]
    return DURAK_RANKS.index(rank)

async def start_durak(update, context, user):
    deck = make_deck()
    random.shuffle(deck)
    player_hand = deck[:6]
    bot_hand = deck[6:12]
    trump_card = deck[12]
    trump_suit = trump_card[-2:]

    game = {
        'player_hand': player_hand,
        'bot_hand': bot_hand,
        'trump': trump_suit,
        'trump_card': trump_card,
        'table': [],
        'deck': deck[13:],
        'phase': 'attack',  # attack / defend
    }
    context.user_data['durak'] = game

    hand_str = ' '.join(player_hand)
    buttons = [[InlineKeyboardButton(c, callback_data=f'durak_play_{c}')] for c in player_hand]
    buttons.append([InlineKeyboardButton("🏳️ Сдаться", callback_data='durak_give_up')])

    await update.message.reply_text(
        f"🃏 Дурак!\n\n"
        f"Козырь: {trump_card} {trump_suit}\n"
        f"Карт у бота: {len(bot_hand)}\n\n"
        f"Ваши карты: {hand_str}\n\n"
        f"Ход ваш — выберите карту для атаки:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def durak_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    game = context.user_data.get('durak')

    if not game:
        await query.edit_message_text("Игра не найдена. Начните заново через меню.")
        return

    data = query.data

    if data == 'durak_give_up':
        context.user_data.pop('durak', None)
        await query.edit_message_text("🏳️ Вы сдались! Вы — дурак 😄")
        return

    if data.startswith('durak_play_'):
        card = data.replace('durak_play_', '')
        if card not in game['player_hand']:
            await query.answer("Эта карта уже сыграна")
            return

        game['player_hand'].remove(card)
        game['table'].append(card)

        # Bot defends
        trump = game['trump']
        bot_hand = game['bot_hand']
        defended = False
        defend_card = None

        for bc in sorted(bot_hand, key=card_rank):
            same_suit = bc.endswith(card[-2:]) and card_rank(bc) > card_rank(card)
            trump_beat = bc.endswith(trump) and not card.endswith(trump)
            if same_suit or trump_beat:
                defend_card = bc
                defended = True
                break

        if defended:
            bot_hand.remove(defend_card)
            game['table'].append(defend_card)

            # Check win
            if not bot_hand:
                context.user_data.pop('durak', None)
                await query.edit_message_text("🎉 Вы выиграли! Бот остался с картами!")
                return

            # Bot attacks back
            bot_attack = random.choice(bot_hand)
            bot_hand.remove(bot_attack)
            game['table'].append(bot_attack)

            hand_str = ' '.join(game['player_hand'])
            buttons = [[InlineKeyboardButton(c, callback_data=f'durak_play_{c}')] for c in game['player_hand']]
            buttons.append([InlineKeyboardButton("🏳️ Сдаться", callback_data='durak_give_up')])

            await query.edit_message_text(
                f"🃏 Дурак!\n\n"
                f"Козырь: {game['trump_card']}\n"
                f"Вы сыграли: {card}\n"
                f"Бот отбил: {defend_card}\n"
                f"Бот атакует: {bot_attack}\n\n"
                f"Карт у бота: {len(bot_hand)}\n"
                f"Ваши карты: {hand_str}\n\n"
                f"Отбейте карту бота:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            # Bot picks up
            bot_hand.extend(game['table'])
            game['table'] = []

            if not game['player_hand']:
                context.user_data.pop('durak', None)
                await query.edit_message_text("🎉 Вы выиграли! Бот не смог отбить!")
                return

            hand_str = ' '.join(game['player_hand'])
            buttons = [[InlineKeyboardButton(c, callback_data=f'durak_play_{c}')] for c in game['player_hand']]
            buttons.append([InlineKeyboardButton("🏳️ Сдаться", callback_data='durak_give_up')])

            await query.edit_message_text(
                f"🃏 Дурак!\n\n"
                f"Бот не смог отбить {card} и берёт карты!\n"
                f"Карт у бота: {len(bot_hand)}\n\n"
                f"Ваши карты: {hand_str}\n\nВаш ход:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        context.user_data['durak'] = game

# ─── KNB ─────────────────────────────────────────────────────────────────────

async def knb_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.replace('knb_', '')
    bot_choice = random.choice(['rock', 'scissors', 'paper'])

    names = {'rock': '🪨 Камень', 'scissors': '✂️ Ножницы', 'paper': '📄 Бумага'}
    wins = {'rock': 'scissors', 'scissors': 'paper', 'paper': 'rock'}

    if choice == bot_choice:
        result = "🤝 Ничья!"
    elif wins[choice] == bot_choice:
        result = "🎉 Вы выиграли!"
    else:
        result = "😔 Бот выиграл!"

    await query.edit_message_text(
        f"✂️ Камень-Ножницы-Бумага\n\n"
        f"Вы: {names[choice]}\n"
        f"Бот: {names[bot_choice]}\n\n"
        f"{result}",
        reply_markup=knb_keyboard()
    )

# ─── ADMIN COMMAND ───────────────────────────────────────────────────────────

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    await update.message.reply_text("🔐 Админ-панель:", reply_markup=admin_keyboard())

# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not BOT_TOKEN:
        logger.error('TELEGRAM_BOT_TOKEN не установлен.')
        raise SystemExit('Установите TELEGRAM_BOT_TOKEN перед запуском.')

    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('admin', admin_command))

    # Callbacks
    application.add_handler(CallbackQueryHandler(region_callback, pattern='^region_'))
    application.add_handler(CallbackQueryHandler(slots_callback, pattern='^slots_'))
    application.add_handler(CallbackQueryHandler(roulette_color_callback, pattern='^rou_'))
    application.add_handler(CallbackQueryHandler(roulette_bet_callback, pattern='^roubet_'))
    application.add_handler(CallbackQueryHandler(durak_callback, pattern='^durak_'))
    application.add_handler(CallbackQueryHandler(knb_callback, pattern='^knb_'))

    # Menu text handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    logger.info('Бот запущен!')
    application.run_polling()
