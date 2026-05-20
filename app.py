import os
import logging
import asyncio
from datetime import datetime
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiohttp
import cloudscraper
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8889330904:AAG4SO4Bxqi4f3cFlSE9Tu0lMlmW7fWBFjU"
YOUR_CHAT_ID = "8804129581"
# =====================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

CURRENCIES = ["USD", "EUR", "GBP", "CNY"]

async def get_cbr_rates():
    """Получает официальные курсы ЦБ РФ"""
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

def get_xe_rate_sync(currency):
    """Синхронная версия парсинга XE.com с обходом Cloudflare"""
    url = f"https://www.xe.com/currencyconverter/convert/?Amount=1&From={currency}&To=RUB"
    
    # Создаём scraper с имитацией реального браузера
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        },
        delay=15
    )
    
    try:
        response = scraper.get(url, timeout=20)
        html = response.text
        
        # Парсим курс
        soup = BeautifulSoup(html, "html.parser")
        
        # Пробуем разные селекторы (на случай изменения верстки)
        rate_element = soup.find("p", class_="result__BigRate-sc-1bsrppl-1")
        if not rate_element:
            rate_element = soup.find("div", {"data-testid": "converter-result"})
        if not rate_element:
            # Fallback: ищем любой элемент с числом и словом "Russian Rubles"
            text = soup.get_text()
            match = re.search(r"(\d+[.,]\d+)\s*Russian\s*Rubles", text)
            if match:
                return float(match.group(1).replace(",", ""))
        
        if rate_element:
            rate_text = rate_element.text.strip()
            match = re.search(r"([\d,\.]+)", rate_text)
            if match:
                return float(match.group(1).replace(",", ""))
        
        return None
        
    except Exception as e:
        logging.error(f"Ошибка запроса XE для {currency}: {e}")
        return None
    finally:
        scraper.close()

async def get_xe_rate(currency):
    """Асинхронная обёртка для синхронного scraper'а"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_xe_rate_sync, currency)

async def compare_and_alert():
    """Сравнивает курсы и отправляет уведомление"""
    cbr_rates = await get_cbr_rates()
    if not cbr_rates:
        await bot.send_message(YOUR_CHAT_ID, "❌ Не удалось получить курсы ЦБ")
        return
    
    results = []
    for currency in CURRENCIES:
        if currency not in cbr_rates:
            continue
        cbr_rate = cbr_rates[currency]
        xe_rate = await get_xe_rate(currency)
        
        if xe_rate is None:
            results.append(f"❌ {currency}: не удалось получить курс XE")
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
            results.append(f"✅ {currency}: выгодно! Разница {difference:.2f}%")
        else:
            results.append(f"📊 {currency}: ЦБ={cbr_rate:.2f}, XE={xe_rate:.2f}")
    
    # Отправляем сводку в чат (необязательно)
    summary = "\n".join(results)
    logging.info(summary)

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🤖 Бот для сравнения курсов ЦБ и XE.com запущен!\n"
        "Использую обход Cloudflare для получения курсов XE.\n"
        "Проверка курсов происходит каждый час.\n\n"
        "➡️ Для ручной проверки отправь /check"
    )

@dp.message(Command("check"))
async def check_now(message: types.Message):
    await message.answer("🔄 Проверяю курсы сейчас (это может занять 10-15 секунд)...")
    await compare_and_alert()

async def scheduler():
    while True:
        await compare_and_alert()
        await asyncio.sleep(3600)

@app.route('/')
def home():
    return "Бот работает! 🤖", 200

@app.route('/health')
def health():
    return "OK", 200

async def main():
    await bot.send_message(YOUR_CHAT_ID, "✅ Бот запущен! Использую обход Cloudflare для XE.com.")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot, handle_signals=False)

if __name__ == "__main__":
    import threading
    port = int(os.environ.get('PORT', 8080))
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True)
    flask_thread.start()
    asyncio.run(main())
