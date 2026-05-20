import os
import logging
import threading
import asyncio
from datetime import datetime
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiohttp
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8889330904:AAG4SO4Bxqi4f3cFlSE9Tu0lMlmW7fWBFjU"
YOUR_CHAT_ID = "8804129581"
# =====================

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Создание Flask-приложения
app = Flask(__name__)

# Список валют
CURRENCIES = ["USD", "EUR", "GBP", "CNY"]

# --- ФУНКЦИИ БОТА (твои старые работают) ---
async def get_cbr_rates():
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            xml_data = await response.text()
    root = ET.fromstring(xml_data)
    rates = {}
    for valute in root.findall("Valute"):
        char_code = valute.find("CharCode").text
        if char_code in CURRENCIES:
            value = valute.find("Value").text.replace(",", ".")
            nominal = int(valute.find("Nominal").text)
            rates[char_code] = float(value) / nominal
    return rates

async def get_xe_rate(currency):
    url = f"https://www.xe.com/currencyconverter/convert/?Amount=1&From={currency}&To=RUB"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=15) as response:
                html = await response.text()
        except Exception as e:
            logging.error(f"Ошибка запроса XE для {currency}: {e}")
            return None
    soup = BeautifulSoup(html, "html.parser")
    rate_element = soup.find("p", class_="result__BigRate-sc-1bsrppl-1")
    if not rate_element:
        rate_element = soup.find("div", {"data-testid": "converter-result"})
    if rate_element:
        rate_text = rate_element.text.strip()
        import re
        match = re.search(r"([\d,\.]+)", rate_text)
        if match:
            return float(match.group(1).replace(",", ""))
    return None

async def compare_and_alert():
    cbr_rates = await get_cbr_rates()
    if not cbr_rates:
        await bot.send_message(YOUR_CHAT_ID, "❌ Не удалось получить курсы ЦБ")
        return
    for currency in CURRENCIES:
        if currency not in cbr_rates:
            continue
        cbr_rate = cbr_rates[currency]
        xe_rate = await get_xe_rate(currency)
        if xe_rate is None:
            continue
        if xe_rate < cbr_rate:
            difference = ((cbr_rate - xe_rate) / cbr_rate) * 100
            message = (
                f"🔔 <b>ВНИМАНИЕ! Выгодный курс</b>\n"
                f"💵 {currency} → RUB\n"
                f"📉 <b>XE.com:</b> {xe_rate:.2f}\n"
                f"🏦 <b>ЦБ РФ:</b> {cbr_rate:.2f}\n"
                f"📊 <b>Выгода:</b> {difference:.2f}% в пользу XE\n"
                f"🕒 {datetime.now().strftime('%H:%M:%S')}"
            )
            await bot.send_message(YOUR_CHAT_ID, message, parse_mode="HTML")
        else:
            logging.info(f"{currency}: ЦБ={cbr_rate:.2f}, XE={xe_rate:.2f}")

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🤖 Бот для сравнения курсов ЦБ и XE.com запущен!\n"
        "Проверка курсов происходит каждый час.\n\n"
        "➡️ Для ручной проверки отправь /check"
    )

@dp.message(Command("check"))
async def check_now(message: types.Message):
    await message.answer("🔄 Проверяю курсы сейчас...")
    await compare_and_alert()

# --- ФУНКЦИЯ ДЛЯ ФОНОВОЙ ЗАДАЧИ ---
async def scheduler():
    while True:
        await compare_and_alert()
        await asyncio.sleep(3600)  # Каждый час

# --- ВЕБ-ИНТЕРФЕЙС ДЛЯ RENDER ---
@app.route('/')
def home():
    return "Бот работает! 🤖", 200

@app.route('/health')
def health():
    return "OK", 200

# --- ТОЧКА ВХОДА ДЛЯ RENDER ---
def run_web_app():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start():
        # Запускаем планировщик в фоне
        asyncio.create_task(scheduler())
        # Запускаем поллинг
        await dp.start_polling(bot)
    
    loop.run_until_complete(start())

if __name__ == '__main__':
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    # Запускаем веб-сервер
    run_web_app()