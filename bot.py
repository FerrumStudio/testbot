#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
import telepot
from telepot.loop import MessageLoop
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

# Подключение к базе данных
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы, если их нет
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    balance INTEGER DEFAULT 0,
    admin INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS top (
    username TEXT PRIMARY KEY,
    scores INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS certificate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price INTEGER
)''')

conn.commit()

# Телеграм токен бота
TOKEN = '7894339966:AAECoiX6oPLwM_LPgPrd9dPHaw6wgIL2S5E'
bot = telepot.Bot(TOKEN)

# Состояние админов для начисления баллов
admin_give_state = {}
admin_add_cert_state = {}

# Функция регистрации пользователя
def register_user(chat_id, username, name):
    cursor.execute('INSERT OR IGNORE INTO users (chat_id, username, name) VALUES (?, ?, ?)', (chat_id, username, name))
    conn.commit()

# Функция получения всех админов
def get_admins():
    cursor.execute('SELECT chat_id FROM users WHERE admin = 1')
    admins = cursor.fetchall()
    return [admin[0] for admin in admins]

# Функция обработки запросов от кнопок
def handle_callback_query(msg):
    query_id, from_id, query_data = telepot.glance(msg, flavor='callback_query')

    # Начисление баллов (для админов)
    if query_data.startswith('give_'):
        target_username = query_data.split('_')[1]
        admin_give_state[from_id] = target_username  # Сохраняем, кому начисляем баллы
        bot.sendMessage(from_id, f"Сколько баллов начислить пользователю @{target_username}?")
    
    # Покупка сертификата
    elif query_data.startswith('buy_'):
        cert_id = query_data.split('_')[1]
        cursor.execute('SELECT name, price FROM certificate WHERE id = ?', (cert_id,))
        cert = cursor.fetchone()

        if cert:
            cert_name, cert_price = cert
            cursor.execute('SELECT balance FROM users WHERE username = ?', (msg['from']['username'],))
            balance = cursor.fetchone()

            if balance and balance[0] >= cert_price:
                # Списываем баллы с пользователя
                cursor.execute('UPDATE users SET balance = balance - ? WHERE username = ?', (cert_price, msg['from']['username']))
                conn.commit()
                bot.sendMessage(from_id, f"Поздравляем! Вы успешно купили сертификат '{cert_name}' за {cert_price} баллов.")
                
                # Уведомление всем админам о покупке сертификата
                admins = get_admins()
                for admin_username in admins:
                    cursor.execute('SELECT username FROM users WHERE username = ?', (msg['from']['username'],))
                    user_name = cursor.fetchone()[0]
                    bot.sendMessage(bot.getChat(admin_username)['id'], f"Пользователь @{user_name} купил сертификат '{cert_name}'.")
            else:
                bot.sendMessage(from_id, "Недостаточно баллов для покупки этого сертификата.")
        else:
            bot.sendMessage(from_id, "Ошибка: сертификат не найден.")

# Обработка сообщений от пользователя
def handle_message(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)

    # Игнорируем любые обновления, кроме сообщений и callback_query
    if content_type != 'text':
        return

    user = msg['from']
    username = user['username']
    
    if content_type == 'text':
        text = msg['text']

        # Если админ ввел количество баллов после команды /giveball
        if chat_id in admin_give_state:
            try:
                amount = int(text)  # Пробуем преобразовать сообщение в число
                target_username = admin_give_state[chat_id]  # Получаем выбранного пользователя
                
                # Обновляем баланс целевого пользователя в базе данных
                cursor.execute('UPDATE users SET balance = balance + ? WHERE username = ?', (amount, target_username))
                conn.commit()

                # Также обновляем таблицу с топом
                cursor.execute('INSERT OR IGNORE INTO top (username, scores) VALUES (?, 0)', (target_username,))
                cursor.execute('UPDATE top SET scores = scores + ? WHERE username = ?', (amount, target_username))
                conn.commit()

                bot.sendMessage(chat_id, f"Начислено {amount} баллов пользователю @{target_username}.")
                
                # Очищаем состояние после начисления
                del admin_give_state[chat_id]

                # Уведомляем пользователя о начислении баллов
                cursor.execute("SELECT chat_id FROM users WHERE username = ?", (target_username,))
                target_username = cursor.fetchone()[0]
                bot.sendMessage(bot.getChat(target_username)['id'], f"Вам начислено {amount} баллов!")

            except ValueError:
                bot.sendMessage(chat_id, "Введите корректное количество баллов.")
        
        # Если админ добавляет сертификат
        elif chat_id in admin_add_cert_state:
            if 'name' in admin_add_cert_state[chat_id]:
                cert_name = admin_add_cert_state[chat_id]['name']
                try:
                    price = int(text)
                    cursor.execute('INSERT INTO certificate (name, price) VALUES (?, ?)', (cert_name, price))
                    conn.commit()
                    bot.sendMessage(chat_id, f"Сертификат '{cert_name}' добавлен с ценой {price} баллов.")
                    del admin_add_cert_state[chat_id]  # Очищаем состояние
                except ValueError:
                    bot.sendMessage(chat_id, "Введите корректную цену сертификата.")
            else:
                # Получаем название сертификата
                admin_add_cert_state[chat_id]['name'] = text
                bot.sendMessage(chat_id, "Введите цену для сертификата:")
        
        else:
            # Обрабатываем другие сообщения и команды
            if text == '/start':
                register_user(chat_id, username, user.get('first_name', 'Unknown'))
                bot.sendMessage(chat_id, "Добро пожаловать! Используйте /help для списка команд.")

            elif text == '/help':
                cursor.execute('SELECT admin FROM users WHERE username = ?', (username,))
                is_admin = cursor.fetchone()[0]
                
                if is_admin:
                    help_text = """Список команд для админов:
                    /giveball - Начислить баллы пользователю
                    /addcert - Добавить сертификат
                    /balance - Посмотреть свой баланс
                    /top - Посмотреть топ пользователей
                    /shop - Магазин сертификатов
                    """
                else:
                    help_text = """Список команд для пользователей:
                    /balance - Посмотреть свой баланс
                    /top - Посмотреть топ пользователей
                    /shop - Магазин сертификатов
                    """
                bot.sendMessage(chat_id, help_text)

            elif text == '/balance':
                cursor.execute('SELECT balance FROM users WHERE username=?', (username,))
                balance = cursor.fetchone()
                if balance:
                    bot.sendMessage(chat_id, f"Ваш баланс: {balance[0]} баллов")
                else:
                    bot.sendMessage(chat_id, "Пользователь не найден.")

            elif text == '/top':
                cursor.execute('SELECT username, scores FROM top ORDER BY scores DESC LIMIT 10')
                top_users = cursor.fetchall()
                if top_users:
                    top_text = "Топ пользователей:\n"
                    for idx, (username, scores) in enumerate(top_users, start=1):
                        top_text += f"{idx}. {username} - {scores} баллов\n"
                else:
                    top_text = "Топ пользователей пуст."
                
                bot.sendMessage(chat_id, top_text)

            elif text == '/giveball':
                cursor.execute('SELECT username, name FROM users')
                users = cursor.fetchall()
                if users:
                    buttons = [InlineKeyboardButton(text=user[1], callback_data=f'give_{user[0]}') for user in users]
                    markup = InlineKeyboardMarkup(inline_keyboard=[buttons[i:i+2] for i in range(0, len(buttons), 2)])
                    bot.sendMessage(chat_id, "Выберите пользователя для начисления баллов:", reply_markup=markup)
                else:
                    bot.sendMessage(chat_id, "Нет пользователей для начисления баллов.")

            elif text == '/addcert':
                admin_add_cert_state[chat_id] = {}
                bot.sendMessage(chat_id, "Введите название сертификата:")

            elif text == '/shop':
                cursor.execute('SELECT id, name, price FROM certificate')
                certs = cursor.fetchall()
                if certs:
                    buttons = [InlineKeyboardButton(text=f"{cert[1]} - {cert[2]} баллов", callback_data=f'buy_{cert[0]}') for cert in certs]
                    markup = InlineKeyboardMarkup(inline_keyboard=[buttons[i:i+2] for i in range(0, len(buttons), 2)])
                    bot.sendMessage(chat_id, "Магазин сертификатов:", reply_markup=markup)
                else:
                    bot.sendMessage(chat_id, "Магазин пуст. Сертификаты не добавлены.")

# Запуск бота
MessageLoop(bot, {'chat': handle_message, 'callback_query': handle_callback_query}).run_as_thread()

while True:
    pass