from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from pathlib import Path
from datetime import datetime


# ========================================
# BUY PAY — SERVER
# ========================================

app = FastAPI(title="BuyPay API")


# ========================================
# CORS
# ========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://babijontop.github.io"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================================
# DATABASE
# ========================================

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "buypay.db"


def get_db():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():

    connection = get_db()
    cursor = connection.cursor()

    # USERS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # DEPOSITS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)

    # TRANSACTIONS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()


init_database()


# ========================================
# MODELS
# ========================================

class UserData(BaseModel):

    telegram_id: int
    username: str = ""
    first_name: str = ""


class DepositData(BaseModel):

    telegram_id: int
    amount: int


# ========================================
# HOME
# ========================================

@app.get("/")
def home():

    return {
        "status": "ok",
        "service": "BuyPay",
        "message": "BuyPay server работает!"
    }


# ========================================
# CREATE / UPDATE USER
# ========================================

@app.post("/user")
def create_user(data: UserData):

    if data.telegram_id <= 0:

        raise HTTPException(
            status_code=400,
            detail="Неверный Telegram ID"
        )

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT telegram_id
        FROM users
        WHERE telegram_id = ?
        """,
        (data.telegram_id,)
    )

    existing_user = cursor.fetchone()

    now = datetime.now().isoformat()

    if existing_user:

        cursor.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?
            WHERE telegram_id = ?
            """,
            (
                data.username,
                data.first_name,
                data.telegram_id
            )
        )

    else:

        cursor.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                first_name,
                balance,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data.telegram_id,
                data.username,
                data.first_name,
                0,
                now
            )
        )

    connection.commit()
    connection.close()

    return {
        "status": "ok",
        "telegram_id": data.telegram_id
    }


# ========================================
# GET BALANCE
# ========================================

@app.get("/balance/{telegram_id}")
def get_balance(telegram_id: int):

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT balance
        FROM users
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )

    user = cursor.fetchone()

    connection.close()

    if not user:

        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден"
        )

    return {
        "telegram_id": telegram_id,
        "balance": user["balance"]
    }


# ========================================
# CREATE DEPOSIT
# ========================================

@app.post("/deposit")
def create_deposit(data: DepositData):

    if data.amount < 1000:

        raise HTTPException(
            status_code=400,
            detail="Минимальная сумма пополнения — 1000 сум"
        )

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT telegram_id
        FROM users
        WHERE telegram_id = ?
        """,
        (data.telegram_id,)
    )

    user = cursor.fetchone()

    if not user:

        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден"
        )

    now = datetime.now().isoformat()

    cursor.execute(
        """
        INSERT INTO deposits (
            telegram_id,
            amount,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            data.telegram_id,
            data.amount,
            "pending",
            now
        )
    )

    deposit_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return {
        "status": "pending",
        "deposit_id": deposit_id,
        "telegram_id": data.telegram_id,
        "amount": data.amount
    }


# ========================================
# GET USER DEPOSITS
# ========================================

@app.get("/deposits/{telegram_id}")
def get_deposits(telegram_id: int):

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            amount,
            status,
            created_at
        FROM deposits
        WHERE telegram_id = ?
        ORDER BY id DESC
        """,
        (telegram_id,)
    )

    deposits = cursor.fetchall()

    connection.close()

    return {
        "telegram_id": telegram_id,

        "deposits": [
            {
                "id": deposit["id"],
                "amount": deposit["amount"],
                "status": deposit["status"],
                "created_at": deposit["created_at"]
            }

            for deposit in deposits
        ]
    }


# ========================================
# ADMIN — CONFIRM DEPOSIT
# ========================================

@app.post("/admin/deposit/{deposit_id}/confirm")
def confirm_deposit(deposit_id: int):

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM deposits
        WHERE id = ?
        """,
        (deposit_id,)
    )

    deposit = cursor.fetchone()

    if not deposit:

        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена"
        )

    if deposit["status"] != "pending":

        connection.close()

        raise HTTPException(
            status_code=400,
            detail="Заявка уже обработана"
        )

    telegram_id = deposit["telegram_id"]
    amount = deposit["amount"]

    now = datetime.now().isoformat()

    # Меняем статус заявки
    cursor.execute(
        """
        UPDATE deposits
        SET status = 'confirmed'
        WHERE id = ?
        """,
        (deposit_id,)
    )

    # Добавляем деньги на баланс
    cursor.execute(
        """
        UPDATE users
        SET balance = balance + ?
        WHERE telegram_id = ?
        """,
        (
            amount,
            telegram_id
        )
    )

    # Создаём транзакцию
    cursor.execute(
        """
        INSERT INTO transactions (
            telegram_id,
            type,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            telegram_id,
            "deposit",
            amount,
            f"Пополнение #{deposit_id}",
            now
        )
    )

    connection.commit()
    connection.close()

    return {
        "status": "confirmed",
        "deposit_id": deposit_id,
        "telegram_id": telegram_id,
        "added": amount
    }


# ========================================
# ADMIN — REJECT DEPOSIT
# ========================================

@app.post("/admin/deposit/{deposit_id}/reject")
def reject_deposit(deposit_id: int):

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM deposits
        WHERE id = ?
        """,
        (deposit_id,)
    )

    deposit = cursor.fetchone()

    if not deposit:

        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена"
        )

    if deposit["status"] != "pending":

        connection.close()

        raise HTTPException(
            status_code=400,
            detail="Заявка уже обработана"
        )

    cursor.execute(
        """
        UPDATE deposits
        SET status = 'rejected'
        WHERE id = ?
        """,
        (deposit_id,)
    )

    connection.commit()
    connection.close()

    return {
        "status": "rejected",
        "deposit_id": deposit_id
    }


# ========================================
# TRANSACTIONS
# ========================================

@app.get("/transactions/{telegram_id}")
def get_transactions(telegram_id: int):

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            type,
            amount,
            description,
            created_at
        FROM transactions
        WHERE telegram_id = ?
        ORDER BY id DESC
        """,
        (telegram_id,)
    )

    transactions = cursor.fetchall()

    connection.close()

    return {
        "telegram_id": telegram_id,

        "transactions": [
            {
                "id": transaction["id"],
                "type": transaction["type"],
                "amount": transaction["amount"],
                "description": transaction["description"],
                "created_at": transaction["created_at"]
            }

            for transaction in transactions
        ]
    }