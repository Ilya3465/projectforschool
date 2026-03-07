
import asyncio
import json
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database as db

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8707711583:AAGpuFf9nhHmsqtEFkshTkMj-XMGTYPbjDQ"
QUESTIONS_FILE = "questions.json"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- МАШИНА СОСТОЯНИЙ (FSM) ---
class QuizState(StatesGroup):
    choosing_subject = State()
    answering = State()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def load_questions():
    with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_subject_keyboard():
    questions = load_questions()
    keyboard = []

    # Словарь для красивых названий (ключ из JSON : Красивое имя)
    nice_names = {
        "math_profile_10": "📐 Профильная математика (10 класс)",
        "math_base_10": "📏 Базовая математика (10 класс)",
        "physics_10": "⚛️ Физика (10 класс)",
        "russian_lang": "📝 Русский язык",
        "history": "📜 История"
    }

    for subject_key in questions.keys():
        # Если есть красивое имя в словаре — берем его, иначе просто убираем подчеркивания
        if subject_key in nice_names:
            name = nice_names[subject_key]
        else:
            # Заменяем _ на пробел и делаем Заглавными Каждое Слово
            name = subject_key.replace("_", " ").title()

        # Важно: в callback_data передаем технический ключ (subject_key)
        keyboard.append([InlineKeyboardButton(text=name, callback_data=f"start_{subject_key}")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_answer_keyboard(options, q_index):
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(text=option, callback_data=f"ans_{q_index}_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- ОБРАБОТЧИКИ (HANDLERS) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await db.add_user(message.from_user.id, message.from_user.username)
    await state.clear()
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\nЯ бот-тренажер для подготовки к экзаменам.\n\nВыбери предмет:",
        reply_markup=create_subject_keyboard()
    )
    await state.set_state(QuizState.choosing_subject)


@dp.callback_query(F.data.startswith("start_"))
async def process_subject_choice(callback: types.CallbackQuery, state: FSMContext):
    subject = callback.data.split("_")[1]
    questions = load_questions()[subject]

    if not questions:
        await callback.answer("В этом предмете пока нет вопросов :(", show_alert=True)
        return

    # Сохраняем данные в память (state)
    await state.update_data(subject=subject, questions=questions, current_q=0, score=0)

    await send_question(callback, state)


async def send_question(callback_or_message, state: FSMContext):
    data = await state.get_data()
    q_index = data['current_q']
    questions = data['questions']

    if q_index >= len(questions):
        await finish_quiz(callback_or_message, state)
        return

    question_data = questions[q_index]

    # Формируем текст вопроса
    text = f"❓ **Вопрос {q_index + 1}/{len(questions)}**\n\n{question_data['question']}"

    # Создаем кнопки с вариантами
    keyboard = create_answer_keyboard(question_data['options'], q_index)

    if isinstance(callback_or_message, types.CallbackQuery):
        await callback_or_message.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await callback_or_message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("ans_"))
async def process_answer(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q_index = data['current_q']
    questions = data['questions']
    score = data['score']

    # Парсим данные из callback_data: ans_0_1 (вопрос 0, ответ 1)
    parts = callback.data.split("_")
    selected_option = int(parts[2])

    correct_option = questions[q_index]['correct']

    # Проверка ответа
    if selected_option == correct_option:
        score += 1
        await callback.answer("✅ Верно!", show_alert=False)
    else:
        await callback.answer(f"❌ Ошибка! Правильный ответ: {questions[q_index]['options'][correct_option]}",
                              show_alert=True)

    # Переход к следующему вопросу
    data['current_q'] += 1
    data['score'] = score
    await state.set_data(data)

    await send_question(callback, state)


async def finish_quiz(callback_or_message, state: FSMContext):
    data = await state.get_data()
    score = data['score']
    total = len(data['questions'])
    subject = data['subject']

    # Сохраняем в БД
    await db.save_result(callback_or_message.from_user.id, subject, score, total)

    percentage = int((score / total) * 100)
    emoji = "🏆" if percentage == 100 else "🔥" if percentage > 70 else "📚"

    text = f"{emoji} **Тест завершен!**\n\nПредмет: {subject.capitalize()}\nТвой результат: {score} из {total}\nУспешность: {percentage}%"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Пройти еще раз", callback_data=f"start_{subject}")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="stats")]
    ])

    if isinstance(callback_or_message, types.CallbackQuery):
        await callback_or_message.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await callback_or_message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

    await state.clear()


@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    results = await db.get_user_stats(user_id)

    if not results:
        text = "📭 У тебя пока нет пройденных тестов."
    else:
        text = "📊 **Твоя статистика:**\n\n"
        for subject, score, total in results[-5:]:  # Показываем последние 5
            text += f"📌 {subject.capitalize()}: {score}/{total}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В меню", callback_data="start_menu")]  # Можно доработать логику возврата
    ])
    # Для простоты просто отправим сообщение, так как edit_text может выдать ошибку, если клавиатура изменилась кардинально
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "leaderboard")
async def show_leaderboard(callback: types.CallbackQuery):
    top_users = await db.get_leaderboard()

    text = "🏆 **Топ учеников:**\n\n"
    for i, (username, avg_score) in enumerate(top_users, 1):
        text += f"{i}. {username or 'Аноним'} — {avg_score:.1f}% успеха\n"

    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


# Команда для просмотра топа
@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    top_users = await db.get_leaderboard()
    text = "🏆 **Топ учеников:**\n\n"
    for i, (username, avg_score) in enumerate(top_users, 1):
        text += f"{i}. {username or 'Аноним'} — {avg_score:.1f}% успеха\n"
    await message.answer(text, parse_mode="Markdown")


# --- ЗАПУСК ---
async def main():
    await db.init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())