from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt
import datetime

app = FastAPI()

# CORS (permite frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CHAVE SECRETA (mude depois!)
SECRET_KEY = "suplementospro2025"

# MODELOS
class UserRegister(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

# BANCO FAKE (em produção use MySQL)
users_db = {}

# GERAR TOKEN JWT
def create_token(email: str):
    payload = {
        "email": email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

# PRODUTOS
MOCK_PRODUCTS = [
    {"id": 1, "name": "WHEY PROTEIN 1KG", "description": "Isolado + Concentrado", "price": 179.90, "image_url": "https://images.unsplash.com/photo-1583454110502-cf5c4c7add63?w=400"},
    {"id": 2, "name": "CREATINA 300G", "description": "100% Pura", "price": 89.90, "image_url": "https://images.unsplash.com/photo-1622483767028-3f66f32aef1a?w=400"},
    {"id": 3, "name": "PRÉ-TREINO 300G", "description": "Explosão de energia", "price": 129.90, "image_url": "https://images.unsplash.com/photo-1549570652-97324981a6fd?w=400"},
    {"id": 4, "name": "BCAA 240CAPS", "description": "Recuperação muscular", "price": 99.90, "image_url": "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=400"},
    {"id": 5, "name": "MULTIVITAMÍNICO", "description": "60 doses", "price": 69.90, "image_url": "https://images.unsplash.com/photo-1607613009820-8661a6c6b6b7?w=400"},
    {"id": 6, "name": "ÔMEGA 3 120CAPS", "description": "Saúde cardiovascular", "price": 79.90, "image_url": "https://images.unsplash.com/photo-1625772299848-391b6a037d0b?w=400"}
]

# CADASTRO
@app.post("/register")
def register(user: UserRegister):
    if user.email in users_db:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    
    users_db[user.email] = {
        "name": user.name,
        "password": user.password  # Em produção: use hash!
    }
    token = create_token(user.email)
    return {"token": token, "message": "Cadastro realizado!"}

# LOGIN
@app.post("/login")
def login(user: UserLogin):
    if user.email not in users_db:
        raise HTTPException(status_code=400, detail="Email não encontrado")
    
    if users_db[user.email]["password"] != user.password:
        raise HTTPException(status_code=400, detail="Senha incorreta")
    
    token = create_token(user.email)
    return {"token": token, "message": "Login realizado!"}

# PRODUTOS
@app.get("/products")
def get_products():
    return MOCK_PRODUCTS

# RAIZ
@app.get("/")
def root():
    return {"message": "SUPLEMENTOS PRO API - ONLINE!"}