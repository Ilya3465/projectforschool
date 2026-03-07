import aiosqlite
import os

DB_NAME = "quiz_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """)
        # Таблица результатов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subject TEXT,
                score INTEGER,
                total_questions INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def add_user(user_id, username):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        await db.commit()

async def save_result(user_id, subject, score, total):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO results (user_id, subject, score, total_questions) VALUES (?, ?, ?, ?)",
                         (user_id, subject, score, total))
        await db.commit()

async def get_user_stats(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT subject, score, total_questions FROM results WHERE user_id = ?", (user_id,))
        return await cursor.fetchall()

async def get_leaderboard(limit=5):
    async with aiosqlite.connect(DB_NAME) as db:
        # Считаем средний процент правильных ответов
        cursor = await db.execute("""
            SELECT u.username, AVG(r.score * 1.0 / r.total_questions * 100) as avg_score
            FROM results r
            JOIN users u ON r.user_id = u.user_id
            GROUP BY r.user_id
            ORDER BY avg_score DESC
            LIMIT ?
        """, (limit,))
        return await cursor.fetchall()