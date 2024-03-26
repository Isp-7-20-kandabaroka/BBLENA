import asyncio
import logging
import sqlite3
import os
import re
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import MessageNotModified
from forbidden_words import forbidden_words_list
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.exceptions import MessageToDeleteNotFound, MessageCantBeDeleted, BadRequest
# Создаем подключение к базе данных
connection = sqlite3.connect('my_database.db')
cursor = connection.cursor()

ADMIN_IDS = [487242878]  # Замените на реальные ID администраторов
# Список городов
cities_list = [
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород",
    "Челябинск", "Красноярск", "Самара", "Уфа", "Ростов-на-Дону", "Омск", "Краснодар",
    "Воронеж", "Волгоград", "Пермь", "Томск", "Кемерово", "Владивосток", "Хабаровск", "Иркутск"
]


# Сохраняем изменения и закрываем соединение
connection.commit()
connection.close()
# Инициализация логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

storage = MemoryStorage()
bot = Bot(token='6669399410:AAHWkE80Jqix61KmaXW-TQzqYw6bMZaFuhE')
dp = Dispatcher(bot, storage=storage)

class UserState(StatesGroup):
    AddCity = State()
    CitySelected = State()
    Subscribed = State()
    AdDescription = State()
    WaitForContact = State()
    AskForPhoto = State()
    WaitForPhotos = State()
    AdPhotos = State()
    Complaint = State()
    DeleteAd = State()


async def register_user_if_not_exists(user_id: int, username: str = None):
    async with aiosqlite.connect('my_database.db') as db:
        # Проверяем, существует ли пользователь в базе данных
        async with db.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cursor:
            user_exists = await cursor.fetchone()
            if not user_exists:
                # Если пользователя нет, регистрируем его и сохраняем его телеграм-ссылку
                await db.execute("INSERT INTO users (id, username, is_blocked) VALUES (?, ?, 0)", (user_id, username))
                await db.commit()
async def check_and_block_user_if_needed(user_id: int):
    async with aiosqlite.connect('my_database.db') as db:
        # Подсчет количества жалоб на пользователя
        async with db.execute("SELECT COUNT(*) FROM complaints WHERE user_id = ?", (user_id,)) as cursor:
            complaints_count = await cursor.fetchone()
            if complaints_count and complaints_count[0] >= 1:  # Проверяем, что количество жалоб >= 1
                # Проверяем, существует ли пользователь в таблице users
                async with db.execute("SELECT is_blocked FROM users WHERE id = ?", (user_id,)) as user_cursor:
                    user_exists = await user_cursor.fetchone()
                    if user_exists is not None:  # Пользователь существует
                        # Обновляем статус блокировки пользователя
                        await db.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
                        await db.commit()
                        return True  # Возвращаем True, если пользователь был заблокирован
    return False  # Возвращаем False, если пользователь не был заблокирован


@dp.message_handler(commands=['start'], state="*")
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username  # Получаем username пользователя
    await register_user_if_not_exists(user_id,username)
    if await is_user_blocked(user_id):
        await message.reply("Извините, ваш аккаунт заблокирован.")
        return
    keyboard = InlineKeyboardMarkup(row_width=2)
    button_subscribe = InlineKeyboardButton(text="Подписаться", url="https://t.me/SOVMESTNAYA_ARENDA_RU")
    button_continue = InlineKeyboardButton(text="Продолжить", callback_data='continue')

    keyboard.add(button_subscribe, button_continue)

    # Отправка картинки с кнопками в одном сообщении
    with open('main.jpg', 'rb') as photo:
        await message.answer_photo(photo, caption="Добро пожаловать в бота. Выберите, пожалуйста, действие.",reply_markup=keyboard)
async def is_user_blocked(user_id: int) -> bool:
    async with aiosqlite.connect('my_database.db') as db:
        async with db.execute("SELECT is_blocked FROM users WHERE id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result and result[0] == 1:
                return True
    return False
@dp.callback_query_handler(lambda c: c.data == 'continue', state="*")
async def main(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    # Отправляем сообщение с инструкциями или информацией
    await callback_query.message.answer("Для начала выберите город", reply_markup=generate_main_menu_markup())
    # Добавляем реплай кнопку "Главное меню"

@dp.message_handler(commands=['delete'], state="*")
async def start_delete_ad(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply("Извините, но эта команда доступна только администраторам.")
        return

    await UserState.DeleteAd.set()
    await message.reply("Пожалуйста, введите ID объявления, которое вы хотите удалить:")
@dp.message_handler(state=UserState.DeleteAd)
async def delete_ad(message: types.Message, state: FSMContext):
    ad_id = message.text.strip()

    # Проверка, что введенный текст является числом
    if not ad_id.isdigit():
        await message.reply("ID объявления должен быть числом. Пожалуйста, попробуйте еще раз.")
        return

    async with aiosqlite.connect('my_database.db') as db:
        # Проверяем наличие объявления в базе данных
        async with db.execute("SELECT id FROM advertisements WHERE id = ?", (ad_id,)) as cursor:
            ad = await cursor.fetchone()
            if ad is None:
                await message.reply(f"Объявление с ID {ad_id} не найдено.")
            else:
                # Удаляем объявление
                await db.execute("DELETE FROM advertisements WHERE id = ?", (ad_id,))
                await db.commit()
                await message.reply(f"Объявление с ID {ad_id} успешно удалено.")

    await state.finish()  # Выход из состояния удаления


@dp.message_handler(commands=['menu'], state="*")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    if await is_user_blocked(user_id):
        await message.reply("Извините, ваш аккаунт заблокирован.")
        return
    last_menu_message_id = data.get('last_menu_message_id')

    if last_menu_message_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=last_menu_message_id)
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения с меню: {e}")

    # Отправка нового сообщения с меню
    sent_message = await message.answer("Добро пожаловать в главное меню!", reply_markup=generate_main_menu_markup())

    # Обновляем ID последнего сообщения с меню
    await state.update_data(last_menu_message_id=sent_message.message_id)

def generate_main_menu_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Выбрать город", callback_data="select_city"))
    markup.add(types.InlineKeyboardButton("Подписка", callback_data="oplata"))
    # Добавьте другие кнопки по мере необходимости
    return markup

async def generate_city_selection_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []

    # Устанавливаем соединение с базой данных
    connection = sqlite3.connect('my_database.db')
    cursor = connection.cursor()
    cities = await fetch_cities()  # Получаем отсортированный список городов
    # Получаем список городов из базы данных
    cursor.execute("SELECT name FROM cities ORDER BY name ASC")
    cities = cursor.fetchall()

    # Закрываем соединение с базой данных
    connection.close()

    # Создаём кнопки для каждого города
    for city in cities:
        city_name = city[0]  # Получаем название города из кортежа
        button = types.InlineKeyboardButton(city_name, callback_data=f"city_{city_name}")
        buttons.append(button)

    # Добавляем кнопки в разметку
    markup.add(*buttons)

    # Добавляем кнопку "Добавить город"
    markup.row(types.InlineKeyboardButton("Добавить город", callback_data="add_city"))
    # Добавляем кнопку "Назад"
    markup.row(types.InlineKeyboardButton("Назад", callback_data="back_to_main"))

    return markup
@dp.callback_query_handler(lambda c: c.data == 'add_city')
async def add_city_callback(callback_query: types.CallbackQuery):
    # Переводим пользователя в состояние добавления города
    await UserState.AddCity.set()
    await bot.send_message(callback_query.from_user.id, "Введите название города:")

def generate_delete_keyboard():
    markup = types.InlineKeyboardMarkup()
    delete_button = types.InlineKeyboardButton("скрыть", callback_data="delete_message")
    markup.add(delete_button)
    return markup
def generate_back_to_main_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Назад", callback_data="back_to_main"))
    return markup
def generate_skip_button():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_photos"))
    return markup
def generate_oplata_button():
    markup = types.InlineKeyboardMarkup()
    delete_button = types.InlineKeyboardButton("скрыть", callback_data="delete_message")
    markup.add(types.InlineKeyboardButton("Купить подписку", callback_data="buy"))
    return markup
def generate_done_button():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Завершить создание", callback_data="done_z"))
    return markup
def city_again():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Посмотреть другие объявления", callback_data="sityagain"))
    return markup
def generate_reply_keyboard():
    # Создаем реплай клавиатуру с кнопкой "Главное меню"
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    keyboard.add(KeyboardButton("Главное меню"))
    return keyboard
def generate_action_keyboard_with_back():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("Создать объявление", callback_data="create_ad"),
               types.InlineKeyboardButton("Просмотр объявлений", callback_data="view_ads"))
    markup.row(types.InlineKeyboardButton("Моё обьявление", callback_data="my_ad"),
               types.InlineKeyboardButton("Жалобы и предложения", callback_data="complaint_start"))
    #markup.add(types.InlineKeyboardButton("Купить подписку за 399руб.", callback_data="oplata"))
    markup.add(types.InlineKeyboardButton("Выбрать другой город", callback_data="back_to_city_selection"))
    return markup
@dp.callback_query_handler(lambda c: c.data == "complaint_start", state="*")
async def start_complaint(callback_query: types.CallbackQuery):
    await UserState.Complaint.set()
    await bot.send_message(callback_query.from_user.id, "Пожалуйста, опишите вашу проблему или предложение.\n\n"
        "Если вы хотите пожаловаться на пользователя, укажите его имя в формате @имя.\n"
        "Также вы можете написать любой другой комментарий или пожелание - мы его обязательно рассмотрим.")
@dp.message_handler(state=UserState.Complaint)
async def handle_complaint(message: types.Message, state: FSMContext):
    channel_id = -1002025346514  # ID вашего канала для жалоб
    complaint_text = message.text

    # Попытка извлечь username из текста жалобы
    username_match = re.search(r'@(\w+)', complaint_text)
    if username_match:
        username = username_match.group(1)
        # Проверка наличия пользователя в базе данных
        async with aiosqlite.connect('my_database.db') as db:
            async with db.execute("SELECT id FROM users WHERE username = ?", (username,)) as cursor:
                user = await cursor.fetchone()
                if user:
                    user_id = user[0]
                    # Блокировка пользователя
                    await db.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
                    await db.commit()
                    await message.reply(f"Пользователь @{username} был заблокирован.")
                else:
                    await message.reply(f"Пользователь @{username} не найден в базе данных.")

    user_mention = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    channel_message = f"Пользователь {user_mention} ({message.from_user.id}) отправил следующее сообщение:\n\n{complaint_text}"
    await bot.send_message(channel_id, channel_message)
    await message.reply("Ваше сообщение отправлено, спасибо за обратную свзяь!", reply_markup=generate_clear_chat_button())
    await state.finish()

def generate_clear_chat_button():
    markup = InlineKeyboardMarkup()
    clear_button = InlineKeyboardButton("Назад", callback_data="clear_chat")
    markup.add(clear_button)
    return markup

async def city_exists(city_name: str) -> bool:
    async with aiosqlite.connect('my_database.db') as db:
        async with db.execute("SELECT EXISTS(SELECT 1 FROM cities WHERE name = ? LIMIT 1)", (city_name,)) as cursor:
            return (await cursor.fetchone())[0] == 1


@dp.callback_query_handler(lambda c: c.data.startswith("confirm_city_"))
async def confirm_city(callback_query: types.CallbackQuery, state: FSMContext):
    city_name = callback_query.data[len("confirm_city_"):]
    # Получаем user_id из состояния
    user_data = await state.get_data()
    user_id = user_data.get('user_id')

    if await city_exists(city_name):
        await bot.answer_callback_query(callback_query.id, f"Город {city_name} уже существует.")
    else:
        async with aiosqlite.connect('my_database.db') as db:
            await db.execute("INSERT INTO cities (name) VALUES (?)", (city_name,))
            await db.commit()
        await bot.answer_callback_query(callback_query.id, f"Город {city_name} добавлен.")
        # Отправляем уведомление пользователю, предложившему город
        if user_id:
            await bot.send_message(user_id, f"Ваш предложенный город {city_name} был успешно добавлен.")


@dp.callback_query_handler(lambda c: c.data == "cancel_city")
async def cancel_city(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, "Предложение отклонено.")
    # Опционально: отправляйте уведомление пользователю, предложившему город


# Обработчик для кнопки удаления
@dp.callback_query_handler(lambda c: c.data == 'delete_message')
async def process_callback_delete_message(callback_query: types.CallbackQuery):
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)

@dp.message_handler(state=UserState.AddCity)
async def add_city(message: types.Message, state: FSMContext):
    city_name = message.text
    channel_id = -1002025346514  # ID вашего канала

    # Сохраняем название города и ID пользователя, который предложил добавление
    await state.update_data(city_name=city_name, user_id=message.from_user.id)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm_city_{city_name}")],
        [InlineKeyboardButton(text="Отклонить", callback_data="cancel_city")]
    ])
    try:
        await bot.send_message(channel_id, f"Пользователь @{message.from_user.username} предложил добавить город: {city_name}", reply_markup=markup)
        await message.reply("Ваше предложение отправлено на рассмотрение.")
    except Exception as e:
        await message.reply("Произошла ошибка при отправке предложения.")
        logger.error(f"Ошибка при отправке сообщения в канал: {e}")
    finally:
        await state.finish()  # Завершаем состояние после обработки
async def back_to_main(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("Главное меню:", reply_markup=generate_main_menu_markup())

@dp.callback_query_handler(text="select_city")
async def select_city(callback_query: types.CallbackQuery):
    # Используем await для асинхронного получения InlineKeyboardMarkup
    markup = await generate_city_selection_markup()
    await callback_query.message.edit_text("Выберите город:", reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('city_'), state='*')
async def process_city_selection(callback_query: types.CallbackQuery, state: FSMContext):
    city = callback_query.data.split('_')[1]
    await state.update_data(city=city, user_id=callback_query.from_user.id)
    logger.info(f"Город {city} выбран, обновление данных состояния.")

    # Сохраняем выбранный город в данных состояния
    await state.update_data(city=city)
    logger.info("Данные состояния обновлены с выбранным городом.")

    # Отправляем сообщение с обновленной клавиатурой
    markup = generate_action_keyboard_with_back()
    await callback_query.message.edit_text(f"Вы выбрали город: {city}.", reply_markup=markup)
    logger.info("Сообщение с выбором города отправлено.")

@dp.callback_query_handler(lambda c: c.data == 'sityagain', state='*')
async def select_city_again(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # Попытка удалить сообщение с кнопкой "Посмотреть другие объявления"
    try:
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        logger.info("Сообщение с кнопкой 'Посмотреть другие объявления' удалено.")
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения с кнопкой: {e}")

    if 'last_menu_message_id' in data:
        try:
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=data['last_menu_message_id'])
            logger.info(f"Сообщение с ID {data['last_menu_message_id']} удалено.")
        except Exception as e:
            logger.error(f"Ошибка при удалении предыдущего сообщения с меню: {e}")

    # Очищаем ID последнего сообщения с меню в состоянии и продолжаем логику функции
    await state.update_data(last_menu_message_id=None)

    # Очистка данных о предыдущих объявлениях и сообщении с меню
    await state.set_data({'ads': [], 'current_ad_index': 0, 'messages_to_delete': []})
    logger.info("Состояние очищено для нового выбора города.")

    # Удаление прошлых объявлений
    for msg_id in data.get('messages_to_delete', []):
        try:
            await bot.delete_message(callback_query.message.chat.id, msg_id)
            logger.info(f"Сообщение объявления с ID {msg_id} удалено.")
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение объявления: {e}")





@dp.callback_query_handler(lambda c: c.data == 'back_to_city_selection', state='*')
async def back_to_city_selection(callback_query: types.CallbackQuery, state: FSMContext):
    # Используем await для асинхронного получения InlineKeyboardMarkup
    markup = await generate_city_selection_markup()
    await callback_query.message.edit_text("Выберите ваш город:", reply_markup=markup)


@dp.callback_query_handler(text="my_ad", state="*")
async def my_ad(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    connection = sqlite3.connect('my_database.db')
    cursor = connection.cursor()
    cursor.execute("SELECT id, description, contact, photos FROM advertisements WHERE user_id=?", (user_id,))
    ad = cursor.fetchone()
    connection.close()

    if not ad:
        await bot.send_message(user_id, "У вас пока нет созданных объявлений.")
        return

    ad_id, description, contact, photos = ad
    message_text = f"Ваше объявление:\nID: {ad_id}\nОписание: {description}\nКонтакт: {contact}"

    # Проверяем наличие фотографий в объявлении
    if photos:
        # Предполагаем, что `photos` хранит пути к фотографиям через запятую
        photos_list = photos.split(',')
        # Отправляем первую фотографию с текстом объявления
        with open(photos_list[0].strip(), 'rb') as photo:
            await bot.send_photo(user_id, photo, caption=message_text, reply_markup=generate_delete_keyboard())
        # Если есть дополнительные фотографии, отправляем их отдельными сообщениями
        for photo_path in photos_list[1:]:
            with open(photo_path.strip(), 'rb') as photo:
                await bot.send_photo(user_id, photo)
    else:
        await bot.send_message(user_id, message_text, reply_markup=generate_delete_keyboard())



async def delete_previous_messages(state: FSMContext, chat_id: int):
    async with state.proxy() as data:
        # Удаление сообщения бота
        last_bot_message_id = data.pop('last_bot_message_id', None)
        if last_bot_message_id:
            try:
                await bot.delete_message(chat_id, last_bot_message_id)
            except Exception as e:
                logging.error(f"Error deleting bot's message: {e}")

        # Удаление сообщения пользователя
        last_user_message_id = data.pop('last_user_message_id', None)
        if last_user_message_id:
            try:
                await bot.delete_message(chat_id, last_user_message_id)
            except Exception as e:
                logging.error(f"Error deleting user's message: {e}")


@dp.callback_query_handler(lambda c: c.data == 'create_ad', state="*")
async def create_ad(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    # Удаление предыдущих сообщений
    await delete_previous_messages(state, chat_id)

    async with aiosqlite.connect('my_database.db') as db:
        cursor = await db.execute("SELECT COUNT(*) FROM advertisements WHERE user_id = ?", (user_id,))
        count = await cursor.fetchone()
        await cursor.close()

    if count[0] > 0:
        # Если объявление уже существует, информируем пользователя
        reply_message = await bot.send_message(chat_id, "Вы уже создали объявление. В данный момент разрешено создавать только одно объявление.")
    else:
        # Если объявления нет, устанавливаем начальное состояние процесса создания объявления
        reply_message = await bot.send_message(chat_id, "Укажите краткую информацию о себе и вашем предложении:")

        # Переходим в состояние описания объявления
        await UserState.AdDescription.set()

    # Сохраняем ID отправленного сообщения для последующего удаления
    async with state.proxy() as data:
        data['last_bot_message_id'] = reply_message.message_id



def compile_forbidden_words_regex(words_list):
    # Экранируем специальные символы в словах и объединяем их в одно большое регулярное выражение
    escaped_words = [re.escape(word) for word in words_list]
    pattern = '|'.join(escaped_words)
    return re.compile(pattern, re.IGNORECASE)


def filter_description(description):
    # Регулярные выражения для фильтрации контактной информации
    phone_pattern = r'\+?[0-9\-\(\)\s]{10,}'  # Простой шаблон для номеров телефонов
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'  # Шаблон для электронных адресов
    link_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'  # Шаблон для ссылок
    mention_pattern = r'@\w+'  # Шаблон для упоминаний пользователей
    # Шаблон для удаления всех чисел, кроме двухзначных
    numbers_except_two_digits = r'\b(?!\d{2}\b)\d+\b'

    # Компилируем регулярное выражение для запрещенных слов
    forbidden_words_regex = compile_forbidden_words_regex(forbidden_words_list)

    # Заменяем запрещенные слова и контактные данные на пустые строки
    patterns = [forbidden_words_regex, phone_pattern, email_pattern, link_pattern, mention_pattern,
                numbers_except_two_digits]
    for pattern in patterns:
        description = re.sub(pattern, "", description)

    return description.strip()  # Удаляем начальные и конечные пробелы

# Обработка введенного описания объявления
@dp.message_handler(state=UserState.AdDescription)
async def process_ad_description(message: types.Message, state: FSMContext):
    filtered_description = filter_description(message.text)  # Фильтруем текст

    async with state.proxy() as data:
        data['description'] = filtered_description

    await UserState.WaitForContact.set()
    await message.answer("Введите контактную информацию:")

@dp.message_handler(state=UserState.WaitForContact)
async def process_contact_info(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['contact'] = message.text

    # Переход к новому состоянию запроса на добавление фото
    await UserState.AskForPhoto.set()
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Добавить фото", callback_data="add_photo"))
    markup.add(InlineKeyboardButton("Пропустить", callback_data="skip_photo"))
    await message.answer("Хотите ли добавить фото?", reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data == 'add_photo', state=UserState.AskForPhoto)
async def add_photo_handler(callback_query: types.CallbackQuery):
    await UserState.WaitForPhotos.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Пожалуйста, отправьте фотографию.")

# Обработка полученной фотографии
@dp.message_handler(content_types=types.ContentType.PHOTO, state=UserState.WaitForPhotos)
async def process_photos(message: types.Message, state: FSMContext):
    photo = message.photo[-1]  # Берем последнюю отправленную фотографию
    photo_id = photo.file_id

    # Получаем путь для сохранения фотографии
    photo_path = os.path.join('img', f'{photo_id}.jpg')

    # Сохраняем фотографию на диск
    await photo.download(destination=photo_path)

    # Сохраняем ID фотографии в состояние
    async with state.proxy() as data:
        data['photo'] = photo_path

    await message.answer("Фотография добавлена. нажмите чтобы закончить.",reply_markup=generate_done_button())

async def fetch_cities():
    async with aiosqlite.connect('my_database.db') as db:
        cursor = await db.execute("SELECT name FROM cities ORDER BY name ASC")
        cities = await cursor.fetchall()
        return [city[0] for city in cities]

@dp.callback_query_handler(lambda c: c.data == 'skip_photo', state=UserState.AskForPhoto)
async def skip_photo_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await done_add(callback_query, state)  # Переход к завершению добавления объявления


@dp.callback_query_handler(lambda c: c.data == 'done_z', state=UserState.WaitForPhotos)
async def done_add(callback_query: types.CallbackQuery, state: FSMContext):
    # Получаем данные из состояния
    async with state.proxy() as data:
        if 'city' not in data:
            # Если город не выбран, возвращаем пользователя к выбору города
            await bot.send_message(callback_query.from_user.id, "Пожалуйста, сначала выберите город.")
            await UserState.CitySelected.set()  # Установите нужное состояние для выбора города
            return  # Завершаем выполнение функции
    # Получаем данные из состояния
    async with state.proxy() as data:
        city = data['city']
        user_id = data.get('user_id')  # Используйте .get() для избежания KeyError
        description = data['description']
        contact = data['contact']
        photos = []
        if 'photo' in data:
            photos.append(data['photo'])

    # Вставляем новое объявление в базу данных
    connection = sqlite3.connect('my_database.db')
    cursor = connection.cursor()

    try:
        # Вставляем информацию о объявлении
        cursor.execute('''
            INSERT INTO advertisements (user_id, city_id, description, contact, photos) VALUES (?, ?, ?, ?, ?)
        ''', (user_id, city, description, contact, ','.join(photos) if isinstance(photos, list) else photos))
        connection.commit()
        ad_id = cursor.lastrowid  # Получаем ID только что вставленного объявления
    except sqlite3.DatabaseError as e:
        await bot.send_message(callback_query.from_user.id, f"Произошла ошибка при сохранении объявления: {e}")
        return
    finally:
        connection.close()

    # Строим текст сообщения
    message_text = f"\n\nОписание: {description}\nКонтакт: {contact}"

    # Отправляем сообщение с деталями объявления
    if photos:
        # Если у вас есть путь к фото, отправляем его как фото
        with open(photos if isinstance(photos, str) else photos[0], 'rb') as photo:
            await bot.send_photo(callback_query.from_user.id, photo=photo, caption=message_text)
            await bot.send_message(callback_query.from_user.id,
                                   "Ваше объявление размещено, срок размещения 14 дней. \n\nЖелаем удачи в поисках!",
                                   reply_markup=generate_clear_chat_button())
    else:
        await bot.send_message(callback_query.from_user.id, message_text)
        await bot.send_message(callback_query.from_user.id, "Ваше объявление размещено, срок размещения 14 дней. \n\nЖелаем удачи в поисках!",reply_markup=generate_clear_chat_button())

    # Завершаем текущее состояние
    await state.finish()


# Инициализация логгера
logging.basicConfig(level=logging.INFO)


@dp.callback_query_handler(lambda c: c.data == 'view_ads', state='*')
async def view_ads(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    state_data = await state.get_data()
    city = state_data.get('city')

    async with aiosqlite.connect('my_database.db') as db:
        cursor = await db.execute("SELECT id, description, contact, photos FROM advertisements WHERE city_id=? ORDER BY RANDOM()", (city,))
        ads = await cursor.fetchall()

    if not ads:
        # Если в выбранном городе нет объявлений
        await bot.send_message(
            callback_query.from_user.id,
            "В данном городе пока нет доступных объявлений. Разместите объявление первым!!!",
            reply_markup=generate_clear_chat_button()  # Предоставляем кнопку "Назад" для возврата к предыдущему выбору
        )
        return  # Останавливаем выполнение функции, чтобы не продолжать с send_ads_batch

    # Если есть объявления, продолжаем как обычно
    await state.set_data({'ads': ads, 'current_ad_index': 0})
    await send_ads_batch(callback_query.from_user.id, state)



async def show_ad(user_id, ad, state: FSMContext):
    ad_id, description, contact, photos = ad
    message_text = f"Объявление ID: {ad_id}\nОписание: {description}\nКонтакт: {contact}"
    message = None

    if photos:
        photo_ids = photos.split(', ')
        photo_path = photo_ids[0].strip()
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo_file:
                message = await bot.send_photo(user_id, photo_file, caption=message_text)
        else:
            message = await bot.send_message(user_id, "Проблема с загрузкой изображения.")
    else:
        message = await bot.send_message(user_id, message_text)






async def send_ads_batch(user_id, state: FSMContext):
    user_data = await state.get_data()
    ads = user_data['ads']
    current_ad_index = user_data['current_ad_index']
    ads_to_send = ads[current_ad_index:current_ad_index+20]

    for ad in ads_to_send:
        await show_ad(user_id, ad, state)
        await asyncio.sleep(0.3)  # Для предотвращения флуда

    new_index = current_ad_index + 20
    await state.update_data(current_ad_index=new_index)

    # Если после этого есть еще объявления, показываем кнопку "Показать ещё"
    if new_index < len(ads):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Показать ещё", callback_data="next_ad"))
        await bot.send_message(user_id, "Показать следующие объявления?", reply_markup=markup)
        await bot.send_message(user_id, "Нажмите назад чтобы вернуться в меню", reply_markup=generate_clear_chat_button())
    else:
        await bot.send_message(user_id, "Вы просмотрели все доступные объявления в этом городе.", reply_markup=generate_clear_chat_button())




@dp.callback_query_handler(lambda c: c.data == 'next_ad', state='*')
async def next_ad(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)

    # Получаем текущее состояние
    data = await state.get_data()
    ads = data['ads']
    current_ad_index = data['current_ad_index']

    # Проверяем, достигли ли мы конца списка объявлений
    if current_ad_index >= len(ads):
        # Сбрасываем индекс, если достигли конца списка
        current_ad_index = 0
        await state.update_data(current_ad_index=current_ad_index)
        await bot.send_message(callback_query.from_user.id, "Вы просмотрели все доступные объявления. Начинаем снова.")

    # Продолжаем показ объявлений с текущего индекса
    await send_ads_batch(callback_query.from_user.id, state)

def generate_show_contact_button(ad_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Показать контакты", callback_data=f"show_contact_{ad_id}"))
    return markup
@dp.callback_query_handler(lambda c: c.data == 'oplata', state='*')
async def view_ads(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.send_message(
        callback_query.from_user.id,
        "Стоимость подписки: 399 руб.\n\nПокупая подписку, Вы получаете:\n- доступ к размещению одного объявления;\n- доступ к контактам авторов объявлений сроком на 14 дней.",
        reply_markup=generate_oplata_button()
    )


@dp.errors_handler(exception=MessageNotModified)
async def message_not_modified_handler(update: types.Update, exception: MessageNotModified):
    # Логируем ошибку, если нужно
    logging.error(f"MessageNotModified: {exception}")

    # Пытаемся ответить пользователю, предлагая вернуться в главное меню
    try:
        if update.callback_query:
            chat_id = update.callback_query.from_user.id
        elif update.message:
            chat_id = update.message.chat.id
        else:
            return True  # Если не можем определить chat_id, просто выходим

        # Отправляем сообщение с предложением вернуться в главное меню
        await bot.send_message(chat_id, "Кажется, что-то пошло не так. Попробуйте вернуться в главное меню.",
                               reply_markup=generate_main_menu_markup())
    except Exception as e:
        logging.error(f"Error sending 'return to main menu' message: {e}")

    return True  # Говорим aiogram, что ошибка обработана
@dp.callback_query_handler(lambda c: c.data == 'clear_chat')
async def clear_chat_callback(callback_query: types.CallbackQuery):

    user_id = callback_query.from_user.id
    await bot.send_message(user_id, "Добро пожаловать в главное меню!", reply_markup=generate_main_menu_markup())
    message_id = callback_query.message.message_id
    start_message_id = message_id
    end_message_id = max(1, start_message_id - 100)  # Предположим, что 1000 — достаточный лимит
    deleted_count = 0

    for msg_id in range(start_message_id, end_message_id, -1):
        try:
            await bot.delete_message(user_id, msg_id)
            deleted_count += 1
        except (MessageToDeleteNotFound, MessageCantBeDeleted, BadRequest):
            # Пропустить ошибки удаления
            continue



if __name__ == '__main__':
    asyncio.run(dp.start_polling())