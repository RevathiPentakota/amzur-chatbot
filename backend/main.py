from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, chat, threads
from app.db.session import init_db

app = FastAPI(title="amzur-chatbot")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router)
app.include_router(auth.router)
app.include_router(auth.router, prefix="/api")
app.include_router(threads.router)


@app.on_event("startup")
async def startup_event() -> None:
    await init_db()


@app.get("/")
def root():
    return {"status": "ok", "service": "amzur-chatbot", "message": "Welcome to amzur-chatbot API!"}
