import asyncio
import logging
import sys
import station_parser, bus_tracker, live_transport, database, balance_card
import os
from fuzzywuzzy import process
from math import radians, cos, sin, sqrt, atan2
import re

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import ChatMemberUpdated, Message
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.deep_linking import decode_payload, create_start_link
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, KICKED, LEFT, MEMBER, RESTRICTED, \
    ADMINISTRATOR, CREATOR
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from aiogram import types, F
from aiogram.filters import Command
import json


def load_stations(file_path):
    if not os.path.exists(file_path):
        print(f"Файл {file_path} не найден.")
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump([], file, ensure_ascii=False, indent=4)
        return []

    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def stations_connector():
    city = "Ufa" + "/"
    stations = load_stations(city + 'сhernikovka.json')
    stations += load_stations(city + 'sipajlovo.json')
    stations += load_stations(city + 'center.json')
    stations += load_stations(city + 'novostroyki.json')
    stations += load_stations(city + 'soviet.json')
    stations += load_stations(city + 'oktyabrskij.json')
    stations += load_stations(city + 'zelyonaya_roshcha.json')
    stations += load_stations(city + 'ordzhonikidzevskij_yug.json')
    stations += load_stations(city + 'inors.json')
    return stations


def load_routes_data():
    routes = {}
    try:
        with open('Ufa/routes.txt', 'r', encoding='utf-8') as file:
            for line in file:
                route_info = line.split(', Направление: ')
                route_name = route_info[0].split('Маршрут: ')[1].split('  ')[0].strip().replace("\xa0", "")
                route_info = route_info[1].split('Ссылка: ')
                route_direction = route_info[0].split(',')[0].strip().replace("Уфа - АВТОВАЗ", "Уфа   АВТОВАЗ").replace(
                    "(СУ - 820)", "(СУ   820)")
                route_link = route_info[1].strip()
                if route_name not in routes:
                    routes[route_name] = []

                if ' - ' in route_direction:
                    direction = route_direction.split(' - ')[1]
                else:
                    direction = [route_direction]
                routes[route_name].append(
                    {'direction': direction.replace("Уфа   АВТОВАЗ", "Уфа - АВТОВАЗ").replace("(СУ   820)",
                                                                                              "(СУ - 820)"),
                     'link': route_link})
        return routes
    except FileNotFoundError:
        print("Файл не найден.")
    except Exception as e:
        print(f"Ошибка при загрузке данных маршрутов: {e}")


def info_bot():
    info = ""
    try:
        with open('info_bot.txt', 'r', encoding='utf-8') as file:
            for line in file:
                info += line
        return info
    except FileNotFoundError:
        print("Файл не найден.")
    except Exception as e:
        print(f"Ошибка при загрузке данных: {e}")


abbreviations = {
    "ТК": "торговый комплекс",
    "БГАУ": "башкирский государственный аграрный университет",
    "ТЦ": "торговый центр",
    "ТСК": "торгово-сервисный комплекс",
    "УТЭК": "уфимский топливно-энергетический колледж",
    "БГУ": "Башкирский государственный университет (БГУ)",
    "УГАТУ": "Уфимский государственный авиационный технический университет (УГАТУ)",
    "ГК РБ по делам юстиции": "Государственный комитет Республики Башкортостан по делам юстиции (ГК РБ по делам юстиции)",
    "УГНТУ": "Уфимский государственный нефтяной технический университет",
    "ГДК": "городской дворец культуры",
    "Горсовет": "совет городского округа город уфа (горсовет)",
    "Авиатехникум": "уфимский авиационный техникум (авиатехникум)",
    "ДК УМПО": "Дворец культуры Уфимского моторостроительного производственного объединения (ДК УМПО)",
    "Отдел кадров УМПО": "Отдел кадров Уфимского моторостроительного производственного объединения (Отдел кадров УМПО)",
    "ТЭЦ-1": "Теплоэнергоцентраль-1 (ТЭЦ-1)",
    "ТЭЦ-2": "Теплоэнергоцентраль-2 (ТЭЦ-2)",
    "ГУП ИНХП РБ": "ГУП \"Институт нефтехимпереработки\" РБ (ГУП ИНХП РБ)",
    "БХП \"Агидель\"": "Башкирские художественные промыслы \"Агидель\" (БХП \"Агидель\")",
    "АТП КПД": "Автотранспортное предприятие ОАО \"Крупнопанельное домостроение\" (АТП КПД)",
    "Гимназия-интернат №1": "Башкирская Республиканская гимназия-интернат №1 им. Рами Гарипова",
    "ПКиО \"им. М. Гафури\"": "Парк культуры и отдыха им. М. Гафури (ПКиО \"им. М. Гафури\")",
    "Уфагаз": "Филиал \"Уфагаз\" ОАО \"Газсервис\" (Уфагаз)",
    "РКБ им. Куватова": "Республиканская клиническая больница им. Куватова (РКБ им. Куватова)",
    "ТК \"Караидель\"": "Торговый комплекс \"Караидель\""
}
district = {"Ufimsky": "Уфимский",
            "Abzelilovsky": "Абзелиловский"
            }
ufa_fake_gps = ""
routes = load_routes_data()
# stations = load_stations('stations.json')
live_transport_list = ""
# bot_username = "test_bus_11092024052_bot"
request = 9
#TOKEN = ""
TOKEN = ""
dp = Dispatcher()
stations = stations_connector()
# db_main = database.DB().read_db()
db = database.DB()


class TransportCardAddDB(StatesGroup):
    pay_system = State()
    card = State()
    validate = State()


@dp.message(CommandStart(deep_link=True))
async def command_start_handler(message: Message, command: CommandObject) -> None:
    args = command.args
    payload = decode_payload(args)
    if payload.startswith('Маршрут '):
        payload = payload[10:]
        try:
            await message.delete()
        except:
            pass
        name_r = ""
        drc = ""
        for name in routes:
            if name.split(" ")[0] == payload:
                name_r = name.split(" ")[0]
                drc = name
                continue
        if payload == name_r:
            bot = message.bot
            index = 0
            buttons = []
            route_info = routes.get(drc, [])
            for info in route_info:
                direction = info['direction']
                link = info['link']
                abbr = await abbreviationer_with_original(direction)
                if len(abbr) > 1:
                    direction = abbr[1]
                else:
                    direction = abbr[0]
                if re.search(r"🚍|🚃|🚎", await bus_tracker.BusTracker(bot).route_tracker(link)):
                    direction = "🟢 " + direction
                else:
                    direction = "🔴 " + direction
                if index == 0:
                    direction = "🅰️ " + direction
                elif index == 1:
                    direction = "🅱️ " + direction
                buttons.append(
                    InlineKeyboardButton(
                        text=direction,
                        callback_data=str(link)
                    )
                )
                index += 1
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])
            await message.answer(f"Выбран маршрут: *{payload}*\nВыберите направление", reply_markup=keyboard,
                                 parse_mode="Markdown")
        else:
            await message.answer(f"Маршрут *{payload[8:]}* не найден", parse_mode="Markdown")
        try:
            await message.delete()
        except:
            pass
    elif payload.startswith('Рейс '):
        payload = payload[5:]
        try:
            await message.delete()
        except:
            pass
        if len(payload) > 0:
            bot = message.bot
            track = await bus_tracker.BusTracker(bot).current_bus_tracking(payload)
            msg = await message.answer(track, parse_mode="Markdown")
            await asyncio.sleep(0.5)
            for i in range(request):
                track = await bus_tracker.BusTracker(bot).current_bus_tracking(payload)
                await bot.edit_message_text(track, chat_id=msg.chat.id, message_id=msg.message_id,
                                            parse_mode="Markdown")
                await asyncio.sleep(60)
            track = await bus_tracker.BusTracker(bot).current_bus_tracking(payload)
            await bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id,
                                        text=track.replace("\nПолучение данных...", ""),
                                        parse_mode="Markdown")
        else:
            await message.answer(f"Рейс {payload[5:]} не найден")
    elif payload.startswith('ГЕО '):
        payload = payload[5:]
        try:
            await message.delete()
        except:
            pass
        if len(payload) > 0:
            bot = message.bot
            info = await bus_tracker.BusInfo(bot).get_bus_info("?" + payload)
            if info[0] != "00":
                for item in live_transport_list:
                    if item['u_statenum'] == info[0].split(" / ")[0]:
                        lat = item['u_lat']
                        long = item['u_long']
                        msg = await message.answer_location(
                            latitude=lat,
                            longitude=long,
                            live_period=900,
                        )
                        last_lat = lat
                        last_long = long
                        col_err = 0
                        for i in range(180):
                            for item in live_transport_list:
                                if item['u_statenum'] == info[0].split(" / ")[0]:
                                    lat = item['u_lat']
                                    long = item['u_long']
                                    try:
                                        if last_lat != lat or last_long != long:
                                            await bot.edit_message_live_location(
                                                chat_id=msg.chat.id,
                                                message_id=msg.message_id,
                                                latitude=lat,
                                                longitude=long,
                                            )
                                            last_lat = lat
                                            last_long = long
                                    except TelegramBadRequest:
                                        col_err += 1
                                        if col_err > 1:
                                            return
                            await asyncio.sleep(5)

    elif payload.startswith('ОСТ_ГЕО '):
        payload = payload[8:]
        try:
            await message.delete()
        except:
            pass
        if len(payload) > 0:
            lat = payload.split("/")[0]
            long = payload.split("/")[1]
            await message.answer_location(
                latitude=lat,
                longitude=long
            )
    elif payload.startswith('ST_F_A '):
        payload = payload[7:].strip("[]").strip("'")
        if payload.isdigit():
            await db.add_station_favorites(message.from_user.id, payload)
            await message.answer("Остановка добавлена в ⭐ Избранное")
        await message.delete()
    elif payload.startswith('ST_F_R '):
        payload = payload[7:].strip("[]").strip("'")
        if payload.isdigit():
            await db.remove_station_favorites(message.from_user.id, payload)
            await message.answer("Остановка удалена из ⭐ Избранное")
        await message.delete()
    elif payload.startswith('RD_F_A '):
        payload = payload[7:]
        if payload:
            await db.add_route_direction_favorites(message.from_user.id, payload)
            await message.answer("Маршрут добавлен в ⭐ Избранное")
        await message.delete()
    elif payload.startswith('RD_F_R '):
        payload = payload[7:]
        if payload:
            await db.remove_route_direction_favorites(message.from_user.id, payload)
            await message.answer("Маршрут удалён из ⭐ Избранное")
        await message.delete()
    elif payload == "info_bot":
        try:
            await message.delete()
        except:
            pass
        await message.answer(info_bot(), parse_mode="MarkdownV2")
    elif payload.startswith('РАЙОН '):
        payload = payload[6:]
        if payload and district.get(payload):
            await db.add_district_favorites(message.from_user.id, payload)
            await message.answer(f"Выбран район - *{district.get(payload)}*", parse_mode="Markdown")
        await message.delete()
    else:
        await start_message(message)


@dp.message(Command(commands=['station']))
async def find_stop(message: types.Message):
    await message.reply("Введите название остановки:")


@dp.message(Command(commands=['test']))
async def test(message: types.Message):
    latitude = 0.0001
    longitude = 0.0001
    await message.answer_location(
        latitude=latitude,
        longitude=longitude,
        live_period=60,
    )


@dp.message(F.location)
async def handle_location(message: types.Message):
    user_location = message.location
    user_lat = user_location.latitude
    user_lon = user_location.longitude
    if not user_lat or not user_lon:
        await message.reply("Не удалось получить вашу геолокацию.")
        return

    def calculate_distance(lat1, lon1, lat2, lon2):
        R = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        # Формула Хаверсина
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    def get_station_coordinates(station):
        try:
            lat = float(station['st_lat'])
            lon = float(station['st_long'])
            return lat, lon
        except (ValueError, KeyError):
            return None

    nearest_stations = sorted(
        [station for station in stations if get_station_coordinates(station)],
        key=lambda station: calculate_distance(
            user_lat, user_lon, get_station_coordinates(station)[0], get_station_coordinates(station)[1])
    )

    buttons = []
    for station in nearest_stations[:5]:
        station_lat, station_lon = get_station_coordinates(station)
        distance = calculate_distance(user_lat, user_lon, station_lat, station_lon)
        abbr = await abbreviationer_with_original(station['st_title'])
        if len(abbr) > 1:
            name = abbr[1]
        else:
            name = abbr[0]
        button_text = f"{name} - {station.get('direction', '')} ({distance:.2f} км)"
        buttons.append(
            InlineKeyboardButton(
                text=button_text,
                callback_data=str(station['st_id'])
            )
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])
    await message.reply("Найдены ближайшие остановки:", reply_markup=keyboard)


# pip install fuzzywuzzy
# pip install python-Levenshtein
def fuzzy_bs(station, threshold=60):
    names = [stop["st_title"] for stop in stations]
    results = process.extract(station, names, limit=10)
    bs = []
    for name, score in results:
        if score >= threshold:
            stops = [stop for stop in stations if stop["st_title"] == name]
            bs.extend(stops)
    return bs


@dp.message(F.text == "⚙ Настройки")
async def user_settings(message: types.Message):
    for item in await database.DB().read_db():
        if item['id'] == message.from_user.id:
            keyboard = InlineKeyboardBuilder()
            keyboard.add(types.InlineKeyboardButton(
                text="Регион:",
                callback_data="Регион:")
            )
            keyboard.add(types.InlineKeyboardButton(
                text="Уфимский",
                callback_data="РАЙОН Уфимский")
            )
            keyboard.adjust(2)
            await message.answer("⚙ Настройки          ⠀          ⠀          ⠀          ⠀          ⠀",
                                 reply_markup=keyboard.as_markup(resize_keyboard=True))
            break
    await message.delete()


@dp.message(F.text == "⬅ Назад")
async def user_exit_to_menu(message: types.Message):
    buttons = [
        [KeyboardButton(text="📍 Показать ближайшие остановки", request_location=True)],
        [KeyboardButton(text="⭐ Избранное")],
        [KeyboardButton(text="💳 Транспортные карты")],
        [KeyboardButton(text="⚙ Настройки")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer("🏠 Главное меню",
                         reply_markup=keyboard)
    await message.delete()


@dp.message(F.text == "💳 Добавить карту")
async def user_transport_card_add(message: types.Message, state: FSMContext):
    buttons = [[KeyboardButton(text="Отмена")]]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer("Добавление карты...", reply_markup=keyboard)
    await state.set_state(TransportCardAddDB.pay_system)
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(
        text="АЛҒА",
        callback_data=f"АЛҒА_ADD_TC")
    )
    keyboard.adjust(1)
    await message.answer("Выберите транспортную карту, которую хотите добавить:",
                         reply_markup=keyboard.as_markup(resize_keyboard=True))
    await message.delete()


@dp.message(F.text == "💳 Транспортные карты")
async def user_transport_card(message: types.Message):
    for item in await database.DB().read_db():
        if item['id'] == message.from_user.id:
            buttons = []
            try:
                if item['card']:
                    for tc in item['card'].split(","):
                        pay_system = tc.split("-")[0]
                        card = (tc.split("-")[1])
                        balance = await balance_card.BalanceTransportCard(pay_system, card).get_balance()
                        buttons.append([KeyboardButton(text=f"{balance} ₽ - 💳 {pay_system} - ** {card[-5:]}")])
                        await asyncio.sleep(0.1)
                if len(item['card'].split(",")) < 3:
                    buttons.append([KeyboardButton(text="💳 Добавить карту")])
            except:
                buttons.append([KeyboardButton(text="💳 Добавить карту")])
            buttons.append([KeyboardButton(text="⬅ Назад")])
            keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
            await message.answer("💳 Транспортные карты",
                                 reply_markup=keyboard)
            await message.delete()
            break


@dp.message(F.text == "⭐ Избранное")
async def user_favorites(message: types.Message):
    bot = message.bot
    for item in await database.DB().read_db():
        if item['id'] == message.from_user.id:
            keyboard = InlineKeyboardBuilder()
            if item['stop']:
                station = None
                for stop in item['stop'].split(","):
                    for s in stations:
                        if isinstance(s['st_id'], list) and stop in map(str, s['st_id']):
                            station = s
                            break
                        elif str(s['st_id']) == stop:
                            station = s
                            break
                    abbr = await abbreviationer_with_original(station['st_title'])
                    if len(abbr) > 1:
                        name = abbr[1]
                    else:
                        name = abbr[0]
                    direction = station['direction']
                    keyboard.add(types.InlineKeyboardButton(
                        text=f"{name} - {direction}",
                        callback_data=stop)
                    )
            if item['route_direction']:
                for rd in item['route_direction'].split(","):
                    route, dst = await bus_tracker.RouteInfo(bot).get_route_info(item['route_direction'])
                    keyboard.add(types.InlineKeyboardButton(
                        text=f"{route} - {dst}",
                        callback_data=rd)
                    )
            keyboard.adjust(1)
            await message.answer("⭐ Избранное          ⠀          ⠀          ⠀          ⠀          ⠀",
                                 reply_markup=keyboard.as_markup(resize_keyboard=True))
            await message.delete()
            break


@dp.message(F.text, TransportCardAddDB.pay_system)
async def reject_add_m(message: types.Message, state: FSMContext):
    if message.text == 'Отмена':
        await reject_add(message, state)


async def reject_add(message: types.Message, state: FSMContext):
    if message.text == 'Отмена':
        await state.clear()
        buttons = [
            [KeyboardButton(text="📍 Показать ближайшие остановки", request_location=True)],
            [KeyboardButton(text="⭐ Избранное")],
            [KeyboardButton(text="💳 Транспортные карты")],
            [KeyboardButton(text="⚙ Настройки")]
        ]
        keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        await message.answer("🏠 Главное меню",
                             reply_markup=keyboard)
        await message.delete()


@dp.message(F.text, TransportCardAddDB.card)
async def alga_num_add(message: types.Message, state: FSMContext):
    if message.text == 'Отмена':
        await reject_add(message, state)
        return
    ps = (await state.get_data())['pay_system']
    number = (message.text.replace(" ", "").replace("\t", ""))
    if len(number) == 19:
        def kb():
            buttons = [[KeyboardButton(text="⬅ Назад")]]
            keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
            return keyboard

        try:
            for item in await database.DB().read_db():
                if item['id'] == message.from_user.id:
                    cards = item['card'].split(",")
                    if f'{ps}-{number}' in cards:
                        await message.answer(
                            f'Данная карта уже добавлена!\nВведите номер карты {ps}',
                            keyboard=kb())
                        return
        except:
            pass
        ans = await balance_card.BalanceTransportCard(ps, number).get_balance()
        if ans == '--':
            await message.answer(
                f'Ошибка валидации карты!\nПроверьте корректность набора номера карты.\nВведите номер карты {ps}',
                keyboard=kb())
        else:
            await state.update_data(card=number)
            await state.set_state(TransportCardAddDB.validate)
            keyboard = InlineKeyboardBuilder()
            keyboard.add(
                InlineKeyboardButton(text="Неверно", callback_data='Отмена'),
                InlineKeyboardButton(text="Верно", callback_data='alga_add_final')
            )
            keyboard.adjust(2)
            await message.answer(
                f'Проверьте данные:\n\nТранспортная карта: {ps}\nНомер карты `{number}`\nБаланс: {ans} ₽',
                reply_markup=keyboard.as_markup(resize_keyboard=True), parse_mode="Markdown")
    else:
        await message.answer(f"Ошибка!\nНомер карты должен состоять из 19 чисел.\nВведите номер карты {ps}")


@dp.message(F.text)
async def search_st_mr_crd(message: types.Message):
    bot = message.bot
    if "₽ - 💳" in message.text:
        for item in await database.DB().read_db():
            if item['id'] == message.from_user.id:
                end_card = message.text[-5:]
                ps = message.text[message.text.find("💳 ") + 2:message.text.find(" - **")]
                cards = item['card'].split(",")
                for crd in cards:
                    full_crd = crd
                    pay_system = crd.split("-")[0]
                    crd = crd.split("-")[1]
                    crd_end = crd[-5:]
                    if ps == pay_system and end_card == crd_end:
                        keyboard = InlineKeyboardBuilder()
                        keyboard.add(
                            InlineKeyboardButton(text="Удалить карту", callback_data=f'DEL_CARD={full_crd}')
                        )
                        keyboard.adjust(2)
                        balance = await balance_card.BalanceTransportCard(pay_system, crd).get_balance()
                        await message.answer(f"Информация о карте\nТранспортная карта: {pay_system}\n"
                                             f"Номер карты: `{crd}`\n"
                                             f"Баланс: {balance} ₽",
                                             reply_markup=keyboard.as_markup(resize_keyboard=True),
                                             parse_mode='Markdown')
        return
    if message.text == 'Отмена':
        buttons = [
            [KeyboardButton(text="📍 Показать ближайшие остановки", request_location=True)],
            [KeyboardButton(text="⭐ Избранное")],
            [KeyboardButton(text="💳 Транспортные карты")],
            [KeyboardButton(text="⚙ Настройки")]
        ]
        keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        await message.answer("🏠 Главное меню",
                             reply_markup=keyboard)
        return
    if message.text != "/start":
        station = message.text.lower()
        station_abbr = await abbreviationer(station)
        bs = []
        for station in station_abbr:
            matches = [stop for stop in stations if station in stop["st_title"].lower()]
            bs.extend(matches)
        if not bs:
            bs = fuzzy_bs(station)
        if bs:
            seen_buttons = set()
            buttons = []
            for stop in bs:
                if isinstance(stop['st_id'], list):
                    stop_id = ','.join(map(str, stop['st_id']))
                else:
                    stop_id = str(stop['st_id'])
                abbr = await abbreviationer_with_original(stop['st_title'])
                if len(abbr) > 1:
                    name = abbr[1]
                else:
                    name = abbr[0]
                button_text = f"{name} - {stop['direction']}"
                if (button_text, stop_id) not in seen_buttons:
                    seen_buttons.add((button_text, stop_id))
                    buttons.append(
                        InlineKeyboardButton(
                            text=button_text,
                            callback_data=stop_id
                        )
                    )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])
            await message.reply("\nНайдены остановки:", reply_markup=keyboard)
        else:
            if re.match(r"^\d+[а-яА-Яa-zA-Z]*$", message.text) == False:
                await message.reply("Остановка не найдена.")
        if re.match(r"^\d+[а-яА-Яa-zA-Z]*$", message.text):
            payload = str(message.text)
            drc = drc_tm = drc_tb = drc_2 = drc_3 = ""
            ab = tm = tb = ab2 = ab3 = False
            for name in routes:
                if name.split(" ")[0].replace("_ТМ", "").replace("_ТР", "").replace("_АВ", "").replace("_АВ2",
                                                                                                       "") == payload:
                    if name.split(" ")[0].find("_ТМ") != -1:
                        tm = True
                        drc_tm = name
                    elif name.split(" ")[0].find("_ТР") != -1:
                        tb = True
                        drc_tb = name
                    elif name.split(" ")[0].find("_АВ") != -1:
                        ab2 = True
                        drc_2 = name
                    elif name.split(" ")[0].find("_АВ2") != -1:
                        ab3 = True
                        drc_3 = name
                    else:
                        ab = True
                        drc = name
            if ab or tm or tb or ab2 or ab3:
                async def keyboard_direction(drc):
                    index = 0
                    buttons = []
                    route_info = routes.get(drc, [])
                    for info in route_info:
                        direction = info['direction']
                        link = info['link']
                        abbr = await abbreviationer_with_original(direction)
                        if len(abbr) > 1:
                            direction = abbr[1]
                        else:
                            direction = abbr[0]
                        if re.search(r"🚍|🚃|🚎", await bus_tracker.BusTracker(bot).route_tracker(link, False)):
                            direction = "🟢 " + direction
                        else:
                            direction = "🔴 " + direction
                        if index == 0:
                            direction = "🅰️ " + direction
                        elif index == 1:
                            direction = "🅱️ " + direction
                        buttons.append(
                            InlineKeyboardButton(
                                text=direction,
                                callback_data=str(link)
                            )
                        )
                        index += 1
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])
                    return keyboard

                if ab:
                    await message.answer(f"Выбран маршрут: *{payload}*\nВид ТС: *Автобус*\nВыберите направление:",
                                         reply_markup=await keyboard_direction(drc),
                                         parse_mode="Markdown")
                if ab2:
                    await message.answer(f"Выбран маршрут: *{payload}*\nВид ТС: *Автобус*\nВыберите направление:",
                                         reply_markup=await keyboard_direction(drc_2),
                                         parse_mode="Markdown")
                if ab3:
                    await message.answer(f"Выбран маршрут: *{payload}*\nВид ТС: *Автобус*\nВыберите направление:",
                                         reply_markup=await keyboard_direction(drc_3),
                                         parse_mode="Markdown")
                if tm:
                    await message.answer(f"Выбран маршрут: *{payload}*\nВид ТС: *Трамвай*\nВыберите направление:",
                                         reply_markup=await keyboard_direction(drc_tm),
                                         parse_mode="Markdown")
                if tb:
                    await message.answer(f"Выбран маршрут: *{payload}*\nВид ТС: *Троллейбус*\nВыберите направление:",
                                         reply_markup=await keyboard_direction(drc_tb),
                                         parse_mode="Markdown")
            else:
                await message.answer(f"Маршрут *{payload}* не найден", parse_mode="Markdown")
            try:
                await message.delete()
            except:
                pass
    else:
        await start_message(message)


@dp.callback_query(lambda call: call.data == 'Регион:')
async def clb_info_area(call):
    await call.answer('Регион:')


@dp.callback_query(lambda call: call.data.startswith('РАЙОН'))
async def clb_info_area(call):
    bot = call.message.bot
    await call.answer("Выберите район")
    await call.message.answer(
        # f'Выберите район:\n\n[Абзелиловский]({await create_start_link(bot, "РАЙОН Abzelilovsky", encode=True)})\n'
        f'[Уфимский]({await create_start_link(bot, "РАЙОН Ufimsky", encode=True)})\n',
        parse_mode="Markdown")


@dp.callback_query(lambda call: call.data.startswith('АЛҒА_ADD_TC'), TransportCardAddDB.pay_system)
async def alga_add_db(call, state: FSMContext):
    await state.update_data(pay_system='АЛҒА')
    await state.set_state(TransportCardAddDB.card)
    await call.message.answer('Введите номер карты АЛҒА')
    await call.message.delete()


@dp.callback_query(lambda call: call.data.startswith('alga_add_final'), TransportCardAddDB.validate)
async def alga_add_db(call, state: FSMContext):
    data = await state.get_data()
    ps = data['pay_system']
    number = data['card']
    data = f"{ps}-{number}"
    await db.add_transport_card(call.from_user.id, data)
    await state.clear()
    buttons = [
        [KeyboardButton(text="📍 Показать ближайшие остановки", request_location=True)],
        [KeyboardButton(text="⭐ Избранное")],
        [KeyboardButton(text="💳 Транспортные карты")],
        [KeyboardButton(text="⚙ Настройки")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await call.message.answer(f'Карта {ps}\n`{number}`\nДобавлена!', reply_markup=keyboard, parse_mode="Markdown")
    await call.message.delete()


@dp.callback_query(lambda call: call.data.startswith('Отмена'), TransportCardAddDB.validate)
async def call_reject_add(call, state: FSMContext):
    await state.clear()
    buttons = [
        [KeyboardButton(text="📍 Показать ближайшие остановки", request_location=True)],
        [KeyboardButton(text="⭐ Избранное")],
        [KeyboardButton(text="💳 Транспортные карты")],
        [KeyboardButton(text="⚙ Настройки")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await call.message.answer("🏠 Главное меню",
                              reply_markup=keyboard)
    await call.message.delete()


@dp.callback_query()
async def selection(call: types.CallbackQuery):
    if call.data.startswith('АЛҒА_ADD_TC'):
        await call.answer('Недоступно')
    elif call.data.startswith('alga_add_final'):
        await call.answer('Недоступно')
    elif call.data.startswith('Отмена'):
        await call.answer('Недоступно')
    elif call.data.startswith('DEL_CARD='):
        card = call.data[9:]
        await db.remove_transport_card(call.from_user.id, card)
        await call.answer('Карта удалена')
        buttons = [
            [KeyboardButton(text="📍 Показать ближайшие остановки", request_location=True)],
            [KeyboardButton(text="⭐ Избранное")],
            [KeyboardButton(text="💳 Транспортные карты")],
            [KeyboardButton(text="⚙ Настройки")]
        ]
        keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        await call.message.answer("🏠 Главное меню",
                                  reply_markup=keyboard)
        await call.message.delete()
    elif call.data.startswith('?rd'):
        async def db_check():
            for item in await database.DB().read_db():
                if item['id'] == tg_id:
                    txt_feature = "⭐ Добавить в избранное"
                    code = "RD_F_A"
                    if item['route_direction']:
                        for route_direction in item['route_direction'].split(","):
                            if route_direction == rd:
                                txt_feature = "❌ Убрать из избранного"
                                code = "RD_F_R"
                                break
                    return txt_feature, code

        tg_id = call.from_user.id
        rd = call.data
        bot = call.message.bot
        msg_id = await call.message.answer("Получение данных...", parse_mode="Markdown")
        try:
            await call.message.delete()
        except:
            pass
        old_answer = ""
        for i in range(request):
            txt_feature, code = await db_check()
            answer = await bus_tracker.BusTracker(bot).route_tracker(f"{rd}&fm=1")
            answer = answer[:answer.find("\n")] + "\nПолучение данных..." + answer[answer.find(
                "\n"):] + f"\n\n[{txt_feature}]({await create_start_link(bot, f'{code} {rd}', encode=True)})"
            if answer != old_answer:
                old_answer = answer
                await bot.edit_message_text(chat_id=call.message.chat.id, message_id=msg_id.message_id, text=answer,
                                            parse_mode="Markdown")
            await asyncio.sleep(60)
        await asyncio.sleep(60)
        txt_feature, code = await db_check()
        answer = await bus_tracker.BusTracker(bot).route_tracker(
            f"{rd}&fm=1") + f"\n\n[{txt_feature}]({await create_start_link(bot, f'{code} {rd}', encode=True)})"
        await bot.edit_message_text(chat_id=call.message.chat.id, message_id=msg_id.message_id, text=answer,
                                    parse_mode="Markdown")
    else:
        if '[' in call.data:
            ids_temp = json.loads(call.data)
            ids = []
            for id in ids_temp:
                ids.append(str(id))
        else:
            ids = [call.data]
        id = ids[0]
        station = None
        for s in stations:
            if isinstance(s['st_id'], list) and id in map(str, s['st_id']):
                station = s
                break
            elif str(s['st_id']) == id:
                station = s
                break
        if station:
            async def db_check():
                try:
                    for item in await database.DB().read_db():
                        if item['id'] == call.from_user.id:
                            txt_feature = "⭐ Добавить в избранное"
                            code = "ST_F_A"
                            if item['stop']:
                                for stop in item['stop'].split(","):
                                    if stop == id:
                                        txt_feature = "❌ Убрать из избранного"
                                        code = "ST_F_R"
                                        break
                            return txt_feature, code
                except:
                    return "⭐ Добавить в избранное", "ST_F_A"

            bot = call.message.bot
            abbr = await abbreviationer_with_original(station['st_title'])
            if len(abbr) > 1:
                name = abbr[1]
            else:
                name = abbr[0]
            direction = station['direction']
            lat = station['st_lat']
            long = station['st_long']
            msg_id = await call.message.answer(
                f"Остановка: *{name} - {direction}*\n[Геопозиция]({await create_start_link(bot, f'ОСТ_ГЕО {lat}/{long}', encode=True)})\nПолучение данных...",
                parse_mode="Markdown")
            try:
                await call.message.delete()
            except:
                pass
            await asyncio.sleep(0.5)
            for i in range(request):
                txt_feature, code = await db_check()
                data = await station_parser.StationParser(bot).parse(ids)
                await bot.edit_message_text(chat_id=call.message.chat.id, message_id=msg_id.message_id,
                                            text=f"Остановка: *{name} - {direction}*\n[Геопозиция]({await create_start_link(bot, f'ОСТ_ГЕО {lat}/{long}', encode=True)})\n" + ufa_fake_gps + data + f"\n[{txt_feature}]({await create_start_link(bot, f'{code} {ids}', encode=True)})",
                                            parse_mode="Markdown")
                await asyncio.sleep(60)
            txt_feature, code = await db_check()
            data = await station_parser.StationParser(bot).parse(ids)
            await bot.edit_message_text(chat_id=call.message.chat.id, message_id=msg_id.message_id,
                                        text=f"Остановка: *{name} - {direction}*\n[Геопозиция]({await create_start_link(bot, f'ОСТ_ГЕО {lat}/{long}', encode=True)})\n" + ufa_fake_gps + data.replace(
                                            "\nПолучение данных...",
                                            "") + f"\n[{txt_feature}]({await create_start_link(bot, f'{code} {ids}', encode=True)})",
                                        parse_mode="Markdown")
        else:
            await call.message.answer("Остановка не найдена.")


@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated):
    await db.remove_user(event.from_user.id)


async def start_message(message):
    bot = message.bot
    buttons = [
        KeyboardButton(text="📍 Показать ближайшие остановки", request_location=True),
        KeyboardButton(text="⭐ Избранное"),
        KeyboardButton(text="💳 Транспортные карты"),
        KeyboardButton(text="⚙ Настройки")
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=[[button] for button in buttons], resize_keyboard=True)
    await db.registration(message.from_user.id)
    await message.answer(
        f"Привет, *{message.from_user.full_name}*!\n[Нажмите, чтобы ознакомиться с ботом.]({await create_start_link(bot, f'info_bot', encode=True)})\nНажмите кнопку ниже, чтобы найти ближайшие остановки.",
        reply_markup=keyboard, parse_mode="Markdown")


async def abbreviationer(station):
    station = station.lower()
    answer = [station]
    abbrs = {}
    for abbr, full in abbreviations.items():
        abbrs[abbr.lower()] = full.lower()
    if station in abbrs:
        answer.append(abbrs[station])
    for abbr, full in abbrs.items():
        if station in full.lower():
            answer.append(abbr.upper())
    return answer


async def abbreviationer_with_original(station):
    def replacer(station):
        station = station.replace("Торговый центр", "ТЦ").replace("Торгово-сервисный комплекс", "ТСК").replace(
            "Торговый комплекс", "ТК").replace("Оздоровительный комплекс", "ОК").replace("Семейный торговый центр",
                                                                                         "СТЦ")
        station = station.replace("Уфимский государственный нефтяной технический университет (УГНТУ)", "УГНТУ")
        return station

    origin_station = station
    station_lower = re.sub(r'[\"\'«»]', '', station.lower())
    answer = [replacer(origin_station)]
    abbrs = {}
    for abbr, full in abbreviations.items():
        abbr_lower = abbr.lower()
        full_lower = re.sub(r'[\"\'«»]', '', full.lower())
        abbrs[abbr_lower] = (abbr, full_lower)
    if station_lower in abbrs:
        answer.append(abbrs[station_lower][0])
    for abbr_lower, (abbr_original, full_lower) in abbrs.items():
        if station_lower in full_lower:
            answer.append(abbr_original)
    return answer


async def get_live_data(live_data):
    global live_transport_list
    data = "None"
    while True:
        async for line in live_data:
            data = line
            break
        if data != "None":
            if isinstance(data, str):
                data = data.replace('\\"', '"')
                data = json.loads(data)
            if data.get('result'):
                live_transport_list = data.get('result')
                await ufa_fake_gps_locator(live_transport_list)


async def ufa_fake_gps_locator(live_transport_list):
    global ufa_fake_gps
    min_lat, max_lat = 54.68446, 54.73592
    min_lon, max_lon = 56.06572, 56.13439
    routes_in_zone = set()
    for transport in live_transport_list:
        lat = float(transport.get('u_lat', 0))
        lon = float(transport.get('u_long', 0))
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            if transport['mr_id'] == "40":
                route = "51"
            elif transport['mr_id'] == "530":
                route = "51А"
            else:
                route = transport['mr_num']
            routes_in_zone.add(route)
    if routes_in_zone:
        routes_in_zone = sorted(routes_in_zone,
                                key=lambda x: [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', x)])
        routes = ", ".join(routes_in_zone)
        ufa_fake_gps = f"Данные GPS на маршрутах {routes} некорректны!\n"


async def main() -> None:
    await db.init()
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    asyncio.create_task(get_live_data(live_transport.LiveGeo().live()))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main())
