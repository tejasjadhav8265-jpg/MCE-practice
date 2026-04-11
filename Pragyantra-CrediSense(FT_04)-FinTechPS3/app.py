from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.api import router


app = FastAPI(
    title="AI Credit Scoring System",
    description="Alternative credit scoring for individuals without credit history using ML",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"message": "AI Credit Scoring API is running 🚀"}