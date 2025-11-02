from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import mysql.connector
from typing import List
from decimal import Decimal

# ==============================
# CONFIGURAÇÃO DO APP
# ==============================
app = FastAPI(title="Suplementos Pro API")
security = HTTPBearer()

# 🔒 Agora usando Argon2 (mais seguro e sem limite de 72 bytes)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# CORS (permite frontend em localhost ou qualquer origem)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção: ["https://seusite.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# CONFIGURAÇÃO DO BANCO (XAMPP)
# ==============================
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # padrão do XAMPP
    'database': 'suplementos_pro'
}

def get_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

# ==============================
# MODELOS (Pydantic)
# ==============================
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class CartAdd(BaseModel):
    product_id: int
    quantity: int = 1

class Checkout(BaseModel):
    shipping_address: str
    payment_method: str = "credit_card"

# ==============================
# JWT (Autenticação)
# ==============================
SECRET_KEY = "suplementos-pro-secret-key-2025-change-in-production"
ALGORITHM = "HS256"

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        return {"sub": user_id, "username": username}
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

# ==============================
# ROTAS
# ==============================

@app.post("/auth/register", response_model=Token)
def register(user: UserCreate, db = Depends(get_db)):
    cursor = db.cursor()

    # Hash seguro com Argon2
    hashed_password = pwd_context.hash(user.password)

    try:
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, full_name) VALUES (%s, %s, %s, %s)",
            (user.username, user.email, hashed_password, user.full_name)
        )
        db.commit()
        user_id = cursor.lastrowid
    except mysql.connector.IntegrityError:
        raise HTTPException(status_code=400, detail="Usuário ou email já existe")
    finally:
        cursor.close()

    token = create_token({"sub": str(user_id), "username": user.username})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/login", response_model=Token)
def login(user: UserLogin, db = Depends(get_db)):
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (user.username,))
    db_user = cursor.fetchone()
    cursor.close()

    if not db_user or not pwd_context.verify(user.password, db_user['password_hash']):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")

    token = create_token({"sub": str(db_user['id']), "username": db_user['username']})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/products")
def get_products(db = Depends(get_db)):
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products ORDER BY id")
    products = cursor.fetchall()
    cursor.close()
    return products


@app.post("/cart/add")
def add_to_cart(item: CartAdd, user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO cart (user_id, product_id, quantity)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE quantity = quantity + %s
    """, (user['sub'], item.product_id, item.quantity, item.quantity))
    db.commit()
    cursor.close()
    return {"message": "Produto adicionado ao carrinho"}


@app.get("/cart")
def get_cart(user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            c.product_id, c.quantity,
            p.name, p.price, p.image_url,
            (c.quantity * p.price) AS subtotal
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = %s
    """, (user['sub'],))
    items = cursor.fetchall()
    cursor.close()

    total = sum(item['subtotal'] for item in items) if items else 0
    return {"items": items, "total": float(total)}


@app.post("/checkout")
def checkout(data: Checkout, user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()

    # Calcular total
    cursor.execute("""
        SELECT SUM(c.quantity * p.price)
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = %s
    """, (user['sub'],))
    total_result = cursor.fetchone()[0]
    total = float(total_result) if total_result else 0.0

    if total == 0:
        raise HTTPException(status_code=400, detail="Carrinho vazio")

    # Criar pedido
    cursor.execute("""
        INSERT INTO orders (user_id, total, shipping_address, payment_method)
        VALUES (%s, %s, %s, %s)
    """, (user['sub'], total, data.shipping_address, data.payment_method))
    order_id = cursor.lastrowid

    # Mover itens do carrinho para order_items
    cursor.execute("SELECT product_id, quantity FROM cart WHERE user_id = %s", (user['sub'],))
    cart_items = cursor.fetchall()
    for item in cart_items:
        prod_id, qty = item
        cursor.execute("SELECT price FROM products WHERE id = %s", (prod_id,))
        price = cursor.fetchone()[0]
        cursor.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, price)
            VALUES (%s, %s, %s, %s)
        """, (order_id, prod_id, qty, price))
        # Reduzir estoque
        cursor.execute("UPDATE products SET stock = stock - %s WHERE id = %s", (qty, prod_id))

    # Limpar carrinho
    cursor.execute("DELETE FROM cart WHERE user_id = %s", (user['sub'],))
    db.commit()
    cursor.close()

    return {
        "message": "Pedido realizado com sucesso!",
        "order_id": order_id,
        "total": total
    }

# ==============================
# RODAR O SERVIDOR
# ==============================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
