import os
import json
import requests
import telebot
from telebot import types
from datetime import datetime
from dotenv import load_dotenv
import time
import uuid
import logging

# Настройка логирования
logging.basicConfig(
    filename='bot.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# Загрузка переменных окружения
load_dotenv()

# Проверка переменных окружения
bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
owm_api_key = os.getenv('OPENWEATHERMAP_API_KEY')
logging.debug(f"TELEGRAM_BOT_TOKEN: {bot_token}")
logging.debug(f"OPENWEATHERMAP_API_KEY: {owm_api_key}")

if not bot_token or not owm_api_key:
    logging.error("Отсутствует TELEGRAM_BOT_TOKEN или OPENWEATHERMAP_API_KEY в переменных окружения")
    raise ValueError("Отсутствует TELEGRAM_BOT_TOKEN или OPENWEATHERMAP_API_KEY в переменных окружения")

# Инициализация бота
try:
    bot = telebot.TeleBot(bot_token)
    logging.info("Бот успешно инициализирован")
except Exception as e:
    logging.error(f"Ошибка при инициализации бота: {str(e)}")
    raise

OWM_API_KEY = owm_api_key

# Списки иконок
ICONS = {
    'weather': {
        'ясно': '☀️',
        'облачно': '⛅️',
        'пасмурно': '☁️',
        'дождь': '🌧',
        'снег': '❄️',
        'разнообразно': '🌈'
    },
    'mood': {
        'активное': '🏃‍♂️',
        'расслабленное': '🧘‍♀️',
        'экстремальное': '⚡'
    },
    'budget': {
        'низкий': '💰',
        'средний': '💵',
        'неограниченный': '💎'
    },
    'people': {
        'один': '👤',
        'пара': '👫',
        'компания': '👪'
    },
    'actions': {
        'restart': '🔄',
        'city': '🏙️',
        'weather': '☀️',
        'budget': '💰',
        'people': '👥',
        'history': '📜',
        'favorites': '⭐'
    }
}

# Файлы для хранения данных
HISTORY_FILE = 'history.json'
FAVORITES_FILE = 'favorites.json'
ACTIVITIES_FILE = 'activities.json'

# Инициализация файлов данных
for file in [HISTORY_FILE, FAVORITES_FILE, ACTIVITIES_FILE]:
    if not os.path.exists(file):
        logging.info(f"Создание файла: {file}")
        with open(file, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False)

# Загрузка активностей из activities.json
def load_activities():
    try:
        with open(ACTIVITIES_FILE, 'r', encoding='utf-8') as f:
            activities = json.load(f)
            logging.debug(f"Активности загружены: {activities}")
            return activities
    except Exception as e:
        logging.error(f"Ошибка при загрузке из {ACTIVITIES_FILE}: {e}")
        return {}

ACTIVITIES = load_activities()

# Состояния пользователей
user_data = {}

# Функции для работы с данными
def save_to_file(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.debug(f"Данные сохранены в {filename}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении в {filename}: {e}")

def load_from_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logging.debug(f"Данные загружены из {filename}")
            return data
    except Exception as e:
        logging.error(f"Ошибка при загрузке из {filename}: {e}")
        return {}

def add_favorite(user_id, item_type, item):
    favorites = load_from_file(FAVORITES_FILE)
    user_id = str(user_id)
    if user_id not in favorites:
        favorites[user_id] = {"venues": [], "activities": [], "queries": []}

    if item not in favorites[user_id][item_type]:
        favorites[user_id][item_type].append(item)
        save_to_file(FAVORITES_FILE, favorites)
        logging.debug(f"Добавлено в избранное: {item_type} - {item}")
        return True
    return False

def get_favorites(user_id):
    return load_from_file(FAVORITES_FILE).get(str(user_id), {"venues": [], "activities": [], "queries": []})

def save_history(user_id, username, data):
    history = load_from_file(HISTORY_FILE)
    entry = {
        'user_id': user_id,
        'username': username,
        'timestamp': datetime.now().isoformat(),
        'city': data.get('city'),
        'weather': data.get('weather'),
        'temp': data.get('temp'),
        'mood': data.get('mood'),
        'budget': data.get('budget'),
        'people': data.get('people'),
        'activities': data.get('activities', [])
    }

    user_id = str(user_id)
    if user_id not in history:
        history[user_id] = []

    history[user_id].append(entry)
    save_to_file(HISTORY_FILE, history)
    logging.debug(f"История сохранена для user_id: {user_id}")

def get_user_history(user_id):
    history = load_from_file(HISTORY_FILE)
    return history.get(str(user_id), [])

# Overpass API для поиска мест
def search_places(city, category):
    category_mapping = {
        "Кафе": ["amenity=cafe"],
        "Рестораны": ["amenity=restaurant"],
        "Кинотеатры": ["amenity=cinema"],
        "Парки": ["leisure=park"],
        "Музеи": ["tourism=museum"],
        "Торговые центры": ["shop=mall"]
    }

    overpass_url = "https://overpass-api.de/api/interpreter"

    if category not in category_mapping:
        logging.warning(f"Категория не найдена: {category}")
        return []

    queries = category_mapping[category]
    results = []

    for query in queries:
        overpass_query = f"""
        [out:json];
        area["name"="{city}"]->.searchArea;
        (
          node[{query}](area.searchArea);
          way[{query}](area.searchArea);
          relation[{query}](area.searchArea);
        );
        out center;
        """

        try:
            response = requests.post(overpass_url, data=overpass_query.encode('utf-8'), timeout=10)
            response.raise_for_status()
            data = response.json()
            logging.debug(f"Overpass API response: {data}")

            for element in data.get("elements", []):
                name = element.get("tags", {}).get("name", "Без названия")
                address = element.get("tags", {}).get("address", "Адрес не указан")

                results.append({
                    "id": element.get("id"),
                    "type": element.get("type"),
                    "name": name,
                    "address": address,
                    "lat": element.get("lat") or element.get("center", {}).get("lat"),
                    "lon": element.get("lon") or element.get("center", {}).get("lon")
                })

                if len(results) >= 15:
                    break

        except Exception as e:
            logging.error(f"Ошибка при запросе к Overpass API: {e}")

    return results

# Клавиатуры
def create_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎯 Найти занятия", "🏢 Найти заведения")
    keyboard.add("⭐ Избранное", "📜 История")
    logging.debug("Основная клавиатура создана")
    return keyboard

def create_categories_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    categories = ["Кафе", "Рестораны", "Кинотеатры", "Парки", "Музеи", "Торговые центры"]
    buttons = [types.InlineKeyboardButton(text=cat, callback_data=f"category_{cat}") for cat in categories]
    keyboard.add(*buttons)
    logging.debug("Клавиатура категорий создана")
    return keyboard

def create_places_keyboard(places, query_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for place in places:
        callback_data = f"place_{query_id}_{place['type']}_{place['id']}"
        keyboard.add(types.InlineKeyboardButton(
            text=f"🏢 {place['name']}",
            callback_data=callback_data
        ))
    keyboard.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_categories"))
    logging.debug(f"Клавиатура мест создана для query_id: {query_id}")
    return keyboard

def create_place_details_keyboard(place_id, place_type, query_id, is_favorite=False):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    if not is_favorite:
        callback_data = f"favplace_{query_id}_{place_type}_{place_id}"
        keyboard.add(types.InlineKeyboardButton(
            text="❤️ В избранное",
            callback_data=callback_data
        ))

    map_callback = f"map_{place_type}_{place_id}"
    back_callback = f"back_to_places_{query_id}"
    keyboard.add(
        types.InlineKeyboardButton(text="📍 На карте", callback_data=map_callback),
        types.InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)
    )
    logging.debug(f"Клавиатура деталей места создана для place_id: {place_id}")
    return keyboard

def create_inline_keyboard(items, prefix="", add_back=False, add_cancel=False):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for item in items:
        callback_data = f"{prefix}_{item}"
        buttons.append(types.InlineKeyboardButton(
            text=f"{ICONS.get(prefix, {}).get(item, '')} {item.capitalize()}",
            callback_data=callback_data
        ))
        logging.debug(f"Добавлена кнопка: {item}, callback_data: {callback_data}")
    if add_back:
        buttons.append(types.InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
        logging.debug("Добавлена кнопка 'Назад'")
    if add_cancel:
        buttons.append(types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
        logging.debug("Добавлена кнопка 'Отмена'")
    if not buttons:
        logging.warning("Клавиатура пуста, кнопки не добавлены")
    keyboard.add(*buttons)
    logging.debug(f"Клавиатура создана для {prefix}: {items}")
    return keyboard

# Обработчики команд
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "Добро пожаловать в АнТиСкУкА БОТ (OSM версия)!\n\n"
        "Я помогу найти:\n"
        "🎯 - Интересные занятия по погоде и настроению\n"
        "🏢 - Лучшие заведения из OpenStreetMap\n\n"
        "Используйте меню или кнопки ниже:"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard())
    logging.info(f"Отправлено приветственное сообщение для chat_id: {message.chat.id}")

@bot.message_handler(commands=['history'])
def show_history_command(message):
    history = get_user_history(message.chat.id)
    if not history:
        bot.send_message(message.chat.id, "У вас пока нет истории запросов.")
        logging.info(f"История пуста для chat_id: {message.chat.id}")
        return

    history_text = "📜 Ваша история запросов:\n\n"
    for i, entry in enumerate(history[-5:], 1):
        history_text += (
            f"{i}. {entry['timestamp'][:10]} {entry['timestamp'][11:16]}\n"
            f"🏙️ Город: {entry['city']}\n"
            f"{ICONS['weather'][entry['weather']]} Погода: {entry['weather']} ({entry['temp']}°C)\n"
            f"{ICONS['mood'][entry['mood']]} Настроение: {entry['mood']}\n"
            f"{ICONS['budget'][entry['budget']]} Бюджет: {entry['budget']}\n"
            f"{ICONS['people'][entry['people']]} Участники: {entry['people']}\n"
            "Варианты:\n"
        )
        for j, activity in enumerate(entry.get('activities', [])[:3], 1):
            history_text += f"   {j}. {activity}\n"
        history_text += "\n"

    bot.send_message(message.chat.id, history_text)
    logging.info(f"Отправлена история для chat_id: {message.chat.id}")

@bot.message_handler(commands=['favorites'])
def show_favorites_command(message):
    show_favorites(message)

@bot.message_handler(func=lambda msg: msg.text == "⭐ Избранное")
def show_favorites(message):
    favorites = get_favorites(message.chat.id)
    if not any(favorites.values()):
        bot.send_message(message.chat.id, "У вас пока нет избранного.")
        logging.info(f"Избранное пусто для chat_id: {message.chat.id}")
        return

    text = "⭐ <b>Ваше избранное</b>\n\n"
    if favorites["venues"]:
        text += "🏢 <b>Заведения:</b>\n"
        for venue in favorites["venues"]:
            text += f"- {venue['name']} ({venue['address']})\n"
        text += "\n"

    if favorites["activities"]:
        text += "🎯 <b>Активности:</b>\n"
        for activity in favorites["activities"]:
            text += f"- {activity}\n"
        text += "\n"

    if favorites["queries"]:
        text += "🔍 <b>Запросы:</b>\n"
        for query in favorites["queries"]:
            text += f"- {query['city']} ({query['weather']}, {query['mood']})\n"

    bot.send_message(message.chat.id, text, parse_mode="HTML")
    logging.info(f"Отправлено избранное для chat_id: {message.chat.id}")

@bot.message_handler(func=lambda msg: msg.text == "🏢 Найти заведения")
def ask_city_for_places(message):
    msg = bot.send_message(message.chat.id, "В каком городе ищем заведения?")
    bot.register_next_step_handler(msg, process_city_for_places)
    logging.info(f"Запрошен город для поиска заведений, chat_id: {message.chat.id}")

def process_city_for_places(message):
    user_data[message.chat.id] = {
        "city": message.text.strip(),
        "step": "places_category"
    }
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=create_categories_keyboard())
    logging.debug(f"Сохранён город {message.text.strip()} для chat_id: {message.chat.id}")

@bot.message_handler(func=lambda msg: msg.text == "🎯 Найти занятия")
def ask_city_for_activities(message):
    msg = bot.send_message(message.chat.id, "Введите название вашего города:")
    bot.register_next_step_handler(msg, process_city_for_activities)
    logging.info(f"Запрошен город для поиска занятий, chat_id: {message.chat.id}")

def process_city_for_activities(message):
    try:
        city = message.text.strip()
        logging.debug(f"Обработка города: {city}")

        weather = get_weather_data(city)
        weather_desc = get_weather_description(weather['weather_code'])
        logging.debug(f"Погода: {weather_desc}, температура: {weather['temp']}°C")

        user_data[message.chat.id] = {
            'step': 'mood',
            'city': city,
            'weather': weather_desc,
            'temp': weather['temp']
        }
        logging.debug(f"Сохранено в user_data: {user_data[message.chat.id]}")

        weather_text = (
            f"{ICONS['weather'][weather_desc]} Погода в {city}:\n"
            f"• Состояние: {weather['description']}\n"
            f"• Температура: {weather['temp']}°C\n"
            f"• Влажность: {weather['humidity']}%\n"
            f"• Ветер: {weather['wind']} м/с\n\n"
            f"Какое у вас настроение?"
        )

        keyboard = create_inline_keyboard(['активное', 'расслабленное', 'экстремальное'], 'mood', add_back=True, add_cancel=True)
        bot.send_message(
            message.chat.id,
            weather_text,
            reply_markup=keyboard
        )
        logging.info(f"Отправлено сообщение с клавиатурой настроений для chat_id: {message.chat.id}")

    except Exception as e:
        error_text = (
            f"{ICONS['weather']['разнообразно']} Ошибка!\n"
            f"Не удалось получить данные для города {city}.\n"
            "Попробуйте ввести другой город:"
        )
        bot.send_message(message.chat.id, error_text)
        msg = bot.send_message(message.chat.id, "Введите название вашего города:")
        bot.register_next_step_handler(msg, process_city_for_activities)
        logging.error(f"Ошибка в process_city_for_activities: {str(e)}")

def get_weather_data(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
    logging.debug(f"Запрос погоды для города: {city}, URL: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        logging.debug(f"Ответ API: {data}")

        if data['cod'] != 200:
            raise Exception(data.get('message', 'Unknown error'))

        return {
            'temp': data['main']['temp'],
            'weather_code': data['weather'][0]['id'],
            'description': data['weather'][0]['description'],
            'humidity': data['main']['humidity'],
            'wind': data['wind']['speed']
        }
    except Exception as e:
        logging.error(f"Ошибка при получении погоды: {str(e)}")
        raise Exception(f"Ошибка при получении погоды: {str(e)}")

def get_weather_description(weather_code):
    if weather_code == 800:
        return "ясно"
    elif weather_code in [801, 802]:
        return "облачно"
    elif weather_code in [803, 804]:
        return "пасмурно"
    elif weather_code in [300, 301, 302, 310, 311, 312, 313, 314, 321, 500, 501, 502, 503, 504, 511, 520, 521, 522, 531]:
        return "дождь"
    elif weather_code in [600, 601, 602, 611, 612, 613, 615, 616, 620, 621, 622]:
        return "снег"
    else:
        return "разнообразно"

@bot.callback_query_handler(func=lambda call: call.data.startswith('category_'))
def show_places(call):
    category = call.data.split('_')[1]
    chat_id = call.message.chat.id
    city = user_data.get(chat_id, {}).get("city")

    if not city:
        bot.answer_callback_query(call.id, "Город не указан")
        logging.warning(f"Город не указан для chat_id: {chat_id}")
        return

    bot.answer_callback_query(call.id, f"Ищем {category.lower()} в {city}...")
    logging.info(f"Поиск заведений: {category} в {city} для chat_id: {chat_id}")

    try:
        places = search_places(city, category)
        if not places:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"Не найдено {category.lower()} в {city}",
                reply_markup=None
            )
            logging.info(f"Заведения не найдены: {category} в {city}")
            return

        query_id = str(uuid.uuid4())
        user_data[chat_id]["current_query"] = {
            "id": query_id,
            "category": category,
            "places": places
        }

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"🏢 {category} в {city} (найдено {len(places)}):",
            reply_markup=create_places_keyboard(places, query_id)
        )
        logging.debug(f"Отправлен список заведений для chat_id: {chat_id}")

    except Exception as e:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"Ошибка при поиске: {str(e)}",
            reply_markup=None
        )
        logging.error(f"Ошибка при поиске заведений: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('place_'))
def show_place_details(call):
    try:
        _, query_id, place_type, place_id = call.data.split('_')
        chat_id = call.message.chat.id

        place = next((p for p in user_data[chat_id]["current_query"]["places"]
                     if str(p["id"]) == place_id and p["type"] == place_type), None)
        if not place:
            bot.answer_callback_query(call.id, "Место не найдено")
            logging.warning(f"Место не найдено: {place_id}, type: {place_type}")
            return

        favorites = get_favorites(chat_id)
        is_favorite = any(v['id'] == place["id"] and v['type'] == place_type
                         for v in favorites["venues"])

        text = (
            f"🏢 <b>{place['name']}</b>\n"
            f"📍 Адрес: {place['address']}\n"
            f"🗺️ Категория: {user_data[chat_id]['current_query']['category']}\n"
        )

        keyboard = create_place_details_keyboard(place["id"], place_type, query_id, is_favorite)

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        logging.debug(f"Отправлены детали места для chat_id: {chat_id}")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в show_place_details: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('favplace_'))
def add_place_to_favorites(call):
    try:
        _, query_id, place_type, place_id = call.data.split('_')
        chat_id = call.message.chat.id

        place = next((p for p in user_data[chat_id]["current_query"]["places"]
                     if str(p["id"]) == place_id and p["type"] == place_type), None)
        if not place:
            bot.answer_callback_query(call.id, "Место не найдено")
            logging.warning(f"Место не найдено для добавления в избранное: {place_id}")
            return

        venue_data = {
            "id": place["id"],
            "type": place_type,
            "name": place["name"],
            "address": place["address"],
            "category": user_data[chat_id]["current_query"]["category"],
            "city": user_data[chat_id]["city"],
            "lat": place.get("lat"),
            "lon": place.get("lon")
        }

        if add_favorite(chat_id, "venues", venue_data):
            bot.answer_callback_query(call.id, "Добавлено в избранное!")
            text = call.message.text
            keyboard = create_place_details_keyboard(place["id"], place_type, query_id, True)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            logging.info(f"Место добавлено в избранное для chat_id: {chat_id}")
        else:
            bot.answer_callback_query(call.id, "Уже в избранном")
            logging.info(f"Место уже в избранном для chat_id: {chat_id}")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в add_place_to_favorites: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('map_'))
def show_on_map(call):
    try:
        _, place_type, place_id = call.data.split('_')
        chat_id = call.message.chat.id

        place = None
        if "current_query" in user_data.get(chat_id, {}):
            place = next((p for p in user_data[chat_id]["current_query"]["places"]
                         if str(p["id"]) == place_id and p["type"] == place_type), None)

        if not place:
            favorites = get_favorites(chat_id)
            place = next((p for p in favorites["venues"]
                         if str(p["id"]) == place_id and p["type"] == place_type), None)

        if place and "lat" in place and "lon" in place:
            map_url = f"https://www.openstreetmap.org/?mlat={place['lat']}&mlon={place['lon']}#map=18/{place['lat']}/{place['lon']}"
            bot.answer_callback_query(call.id, "Открываю карту...", url=map_url)
            logging.debug(f"Открыта карта для места: {place['name']}")
        else:
            bot.answer_callback_query(call.id, "Координаты места не найдены")
            logging.warning(f"Координаты не найдены для места: {place_id}")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в show_on_map: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_'))
def handle_back(call):
    try:
        action = call.data.split('_')[2]
        chat_id = call.message.chat.id

        if action == "categories":
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="Выберите категорию:",
                reply_markup=create_categories_keyboard()
            )
            logging.debug(f"Возврат к категориям для chat_id: {chat_id}")
        elif action == "places":
            query_id = call.data.split('_')[3]
            if "current_query" in user_data.get(chat_id, {}):
                places = user_data[chat_id]["current_query"]["places"]
                category = user_data[chat_id]["current_query"]["category"]
                city = user_data[chat_id]["city"]

                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=f"🏢 {category} в {city} (найдено {len(places)}):",
                    reply_markup=create_places_keyboard(places, query_id)
                )
                logging.debug(f"Возврат к списку мест для chat_id: {chat_id}")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в handle_back: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == 'back')
def handle_back_button(call):
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Введите название вашего города:",
        reply_markup=None
    )
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, process_city_for_activities)
    logging.info(f"Обработка кнопки 'Назад' для chat_id: {call.message.chat.id}")

@bot.callback_query_handler(func=lambda call: call.data == 'cancel')
def handle_cancel_button(call):
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Действие отменено. Выберите действие:",
        reply_markup=create_main_keyboard()
    )
    cleanup_user_data(call.message.chat.id)
    logging.info(f"Обработка кнопки 'Отмена' для chat_id: {call.message.chat.id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('mood_'))
def process_mood(call):
    try:
        mood = call.data.split('_')[1]
        chat_id = call.message.chat.id

        user_data[chat_id]['mood'] = mood
        user_data[chat_id]['step'] = 'budget'

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"{call.message.text}\n\nВыбрано: {ICONS['mood'][mood]} {mood.capitalize()}",
            reply_markup=None
        )

        bot.send_message(
            chat_id,
            f"{ICONS['actions']['budget']} Выберите ваш бюджет:",
            reply_markup=create_inline_keyboard(['низкий', 'средний', 'неограниченный'], 'budget', add_back=True, add_cancel=True)
        )
        logging.debug(f"Выбрано настроение: {mood} для chat_id: {chat_id}")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в process_mood: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('budget_'))
def process_budget(call):
    try:
        budget = call.data.split('_')[1]
        chat_id = call.message.chat.id

        user_data[chat_id]['budget'] = budget
        user_data[chat_id]['step'] = 'people'

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"{call.message.text}\n\nВыбрано: {ICONS['budget'][budget]} {budget.capitalize()}",
            reply_markup=None
        )

        bot.send_message(
            chat_id,
            f"{ICONS['actions']['people']} Сколько человек будет участвовать?",
            reply_markup=create_inline_keyboard(['один', 'пара', 'компания'], 'people', add_back=True, add_cancel=True)
        )
        logging.debug(f"Выбран бюджет: {budget} для chat_id: {chat_id}")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в process_budget: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('people_'))
def process_people(call):
    try:
        people = call.data.split('_')[1]
        chat_id = call.message.chat.id
        data = user_data[chat_id]

        data['people'] = people

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"{call.message.text}\n\nВыбрано: {ICONS['people'][people]} {people.capitalize()}",
            reply_markup=None
        )

        key = f"{data['weather']}_{data['mood']}_{data['budget']}_{data['people']}"
        options = ACTIVITIES.get(key, ["К сожалению, нет подходящих вариантов"])
        data['activities'] = options

        query_id = str(uuid.uuid4())[:8]
        data['query_id'] = query_id

        result_text = (
            f"Рекомендации для {data['city']}:\n\n"
            f"{ICONS['weather'][data['weather']]} Погода: {data['weather']}\n"
            f"{ICONS['mood'][data['mood']]} Настроение: {data['mood']}\n"
            f"{ICONS['budget'][data['budget']]} Бюджет: {data['budget']}\n"
            f"{ICONS['people'][data['people']]} Участники: {data['people']}\n\n"
            "Варианты досуга:\n"
        )

        for i, option in enumerate(options, 1):
            result_text += f"{i}. {option}\n"

        keyboard = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton(
                text=f"{ICONS['actions']['restart']} Новый поиск",
                callback_data="restart"
            ),
            types.InlineKeyboardButton(
                text=f"{ICONS['actions']['history']} История",
                callback_data="show_history"
            ),
            types.InlineKeyboardButton(
                text="🏢 Показать заведения",
                callback_data=f"venues_{query_id}"
            )
        ]

        for i, option in enumerate(options[:3], 1):
            callback_data = f"fav_{query_id}_{i-1}"
            buttons.append(types.InlineKeyboardButton(
                text=f"⭐ Вариант {i}",
                callback_data=callback_data
            ))

        keyboard.add(*buttons)

        user_data[chat_id]['current_activities'] = {
            'options': options,
            'query_id': query_id
        }

        bot.send_message(chat_id, result_text, reply_markup=keyboard)
        save_history(chat_id, call.from_user.username or call.from_user.first_name, data)
        logging.info(f"Отправлены рекомендации для chat_id: {chat_id}")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в process_people: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "restart")
def restart_bot(call):
    send_welcome(call.message)
    cleanup_user_data(call.message.chat.id)
    logging.info(f"Перезапуск бота для chat_id: {call.message.chat.id}")

@bot.callback_query_handler(func=lambda call: call.data == "show_history")
def show_history_callback(call):
    show_history_command(call.message)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fav_'))
def handle_fav_activity(call):
    try:
        _, query_id, option_idx = call.data.split('_')
        chat_id = call.message.chat.id

        activities_data = user_data.get(chat_id, {}).get('current_activities', {})
        if str(query_id) != activities_data.get('query_id', ''):
            bot.answer_callback_query(call.id, "Данные устарели, выполните новый поиск")
            logging.warning(f"Устаревший query_id: {query_id} для chat_id: {chat_id}")
            return

        option_idx = int(option_idx)
        activity = activities_data['options'][option_idx]

        if add_favorite(chat_id, "activities", activity):
            bot.answer_callback_query(call.id, "Добавлено в избранное!")
            logging.info(f"Активность добавлена в избранное: {activity} для chat_id: {chat_id}")
        else:
            bot.answer_callback_query(call.id, "Уже в избранном")
            logging.info(f"Активность уже в избранном: {activity} для chat_id: {chat_id}")

    except (IndexError, ValueError) as e:
        bot.answer_callback_query(call.id, f"Ошибка: неверный вариант ({str(e)})")
        logging.error(f"Ошибка в handle_fav_activity: {str(e)}")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в handle_fav_activity: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('venues_'))
def show_venues_for_query(call):
    try:
        query_id = call.data.split('_')[1]
        chat_id = call.message.chat.id

        data = user_data.get(chat_id, {})
        if 'city' not in data or str(data.get('query_id', '')) != query_id:
            bot.answer_callback_query(call.id, "Данные устарели, выполните новый поиск")
            logging.warning(f"Устаревшие данные для query_id: {query_id} для chat_id: {chat_id}")
            return

        user_data[chat_id] = {
            "city": data['city'],
            "step": "places_category",
            "from_query_id": query_id
        }

        bot.send_message(chat_id, f"Выберите категорию заведений в {data['city']}:",
                        reply_markup=create_categories_keyboard())
        logging.debug(f"Запрошены категории заведений для города {data['city']} для chat_id: {chat_id}")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
        logging.error(f"Ошибка в show_venues_for_query: {str(e)}")

def cleanup_user_data(chat_id):
    if chat_id in user_data:
        keep_keys = ['city', 'step', 'current_query', 'current_activities']
        user_data[chat_id] = {k: v for k, v in user_data[chat_id].items() if k in keep_keys}
        logging.debug(f"Очищены данные пользователя для chat_id: {chat_id}")

if __name__ == '__main__':
    logging.info("Бот запущен (OSM версия)...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")
        time.sleep(5)
        bot.infinity_polling(timeout=10, long_polling_timeout=5)