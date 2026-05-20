import os
import logging
import asyncio
from datetime import datetime
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiohttp
import xml.etree.ElementTree as ET

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8889330904:AAG4SO4Bxqi4f3cFlSE9Tu0lMlmW7fWBFjU"
YOUR_CHAT_ID = "8804129581"
# =====================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

CURRENCIES = ["usd", "eur", "gbp", "cny"]

async def get_cbr_rates():
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            xml_data = await response.text()
    root = ET.fromstring(xml_data)
    rates = {}
    for valute in root.findall("Valute"):
        char_code = valute.find("CharCode").text
        if char_code.lower() in CURRENCIES:
            value = valute.find("Value").text.replace(",", ".")
            nominal = int(valute.find("Nominal").text)
            rates[char_code.upper()] = float(value) / nominal
    return rates

async def get_market_rate(currency):
    """Рыночный курс с currency-api (бесплатно, без ключа, без лимитов)"""
    url = f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{currency}.json"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                data = await response.json()
                rub_rate = data.get(currency, {}).get('rub')
                if rub_rate:
                    return float(rub_rate)
                else:
                    logging.error(f"Не найден курс для {currency}")
                    return None
        except Exception as e:
            logging.error(f"Ошибка запроса {currency}: {e}")
            return None

async def compare_and_alert():
    cbr_rates = await get_cbr_rates()
    if not cbr_rates:
        await bot.send_message(YOUR_CHAT_ID, "❌ Не удалось получить курсы ЦБ")
        return
    
    for currency in CURRENCIES:
        currency_upper = currency.upper()
        if currency_upper not in cbr_rates:
            continue
        cbr_rate = cbr_rates[currency_upper]
        market_rate = await get_market_rate(currency)
        
        if market_rate is None:
            continue
        
        if market_rate < cbr_rate:
            difference = ((cbr_rate - market_rate) / cbr_rate) * 100
            message = (
                f"🔔 <b>ВНИМАНИЕ! Выгодный курс</b>\n"
                f"💵 {currency_upper} → RUB\n"
                f"📉 <b>Рыночный курс:</b> {market_rate:.2f}\n"
                f"🏦 <b>ЦБ РФ:</b> {cbr_rate:.2f}\n"
                f"📊 <b>Выгода:</b> {difference:.2f}% в пользу рынка\n"
                f"🕒 {datetime.now().strftime('%H:%M:%S')}"
            )
            await bot.send_message(YOUR_CHAT_ID, message, parse_mode="HTML")
        else:
            logging.info(f"{currency_upper}: ЦБ={cbr_rate:.2f}, Рынок={market_rate:.2f}")

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🤖 Бот для сравнения курсов ЦБ и рыночных курсов запущен!\n"
        "Использую бесплатный API без лимитов.\n"
        "Проверка курсов происходит каждые 4 часа.\n\n"
        "➡️ Для ручной проверки отправь /check"
    )

@dp.message(Command("check"))
async def check_now(message: types.Message):
    await message.answer("🔄 Проверяю курсы сейчас...")
    await compare_and_alert()

async def scheduler():
    while True:
        await compare_and_alert()
        await asyncio.sleep(14400)  # 4 часа

@app.route('/')
def home():
    return "Бот работает! 🤖", 200

@app.route('/health')
def health():
    return "OK", 200

async def main():
    await bot.send_message(YOUR_CHAT_ID, "✅ Бот запущен! Рыночные курсы без лимитов.")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    import threading
    port = int(os.environ.get('PORT', 8080))
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True)
    flask_thread.start()
    asyncio.run(main())
