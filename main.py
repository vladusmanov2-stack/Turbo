import logging
import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ContentType
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.default import DefaultBotProperties

from telegraph import Telegraph
import aiohttp

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Необходимо установить переменную окружения BOT_TOKEN")

# Инициализация
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- TELEGRAPH ---
telegraph = Telegraph()
telegraph.create_account(short_name='MyCoolBot')

# --- FSM STATES ---
class PageCreation(StatesGroup):
    waiting_media = State()
    waiting_title = State()
    waiting_text = State()

# --- КЛАВИАТУРЫ ---
create_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Создать страницу")],
        [KeyboardButton(text="❌ Отмена")]
    ],
    resize_keyboard=True
)
skip_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="➡️ Пропустить")]],
    resize_keyboard=True, one_time_keyboard=True
)

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(PageCreation.waiting_media)
    await message.answer(
        "Привет! Я помогу тебе создать красивую страницу на Telegraph.\n\n"
        "Отправляй мне фото или видео. Когда закончишь, нажми '✅ Создать страницу'."
    )

@dp.message(F.text == "❌ Отмена", StateFilter(PageCreation))
async def cancel_creation(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание страницы отменено.", reply_markup=types.ReplyKeyboardRemove())

@dp.message(PageCreation.waiting_media, F.content_type.in_({ContentType.PHOTO, ContentType.VIDEO}))
async def handle_media(message: Message, state: FSMContext):
    state_data = await state.get_data()
    media_files = state_data.get("media", [])
    file_id = ""
    media_type = ""
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
    
    media_files.append({"id": file_id, "type": media_type})
    await state.update_data(media=media_files)

    if len(media_files) == 1:
        await message.answer("Отлично! Файл добавлен. Можешь отправить еще или нажать 'Создать страницу'.", reply_markup=create_keyboard)
    else:
        await message.answer(f"Добавлено файлов: {len(media_files)}")

@dp.message(PageCreation.waiting_media, F.text.in_({"✅ Создать страницу", "/create"}))
async def ask_for_title(message: Message, state: FSMContext):
    state_data = await state.get_data()
    if not state_data.get("media"):
        await message.answer("Сначала отправь хотя бы один файл!")
        return
    await state.set_state(PageCreation.waiting_title)
    await message.answer("Теперь отправь мне заголовок для твоей страницы.", reply_markup=types.ReplyKeyboardRemove())

@dp.message(PageCreation.waiting_title, F.text)
async def ask_for_text(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(PageCreation.waiting_text)
    await message.answer("Отлично! Теперь отправь основной текст статьи. Если он не нужен, нажми 'Пропустить'.", reply_markup=skip_keyboard)

@dp.message(PageCreation.waiting_text, F.text)
async def create_page(message: Message, state: FSMContext):
    data = await state.get_data()
    page_text = "" if message.text == "➡️ Пропустить" else f"<p>{message.text.replace(r'n', '<br>')}</p>"
    await message.answer("Почти готово! Собираю все вместе и создаю страницу...", reply_markup=types.ReplyKeyboardRemove())
    media_content = ""
    for media in data.get("media", []):
        try:
            file = await bot.get_file(media["id"])
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
            if media["type"] == "photo":
                media_content += f'<img src="{url}"/>'
            elif media["type"] == "video":
                media_content += f'<figure><video src="{url}" controls=""></video></figure>'
        except Exception as e:
            logging.error(f"Ошибка при обработке файла {media['id']}: {e}")
    html_content = page_text + media_content
    try:
        response = telegraph.create_page(
            title=data.get("title", "Без заголовка"),
            html_content=html_content,
            author_name="Telegraph Bot"
        )
        await message.answer(f"✅ Готово!\nВот ссылка на твою страницу: https://telegra.ph/{response['path']}")
    except Exception as e:
        await message.answer(f"❌ Не удалось создать страницу на Telegraph: {e}")
    await state.clear()

@dp.message(StateFilter(None))
async def text_outside_state(message: Message):
    await message.answer("Я не понимаю. Нажми /start, чтобы начать.")
    
@dp.message(StateFilter(PageCreation))
async def any_other_message_in_state(message: Message):
     await message.answer("Пожалуйста, следуй инструкциям. Если хочешь начать заново, нажми /start.")

# --- ЗАПУСК ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
