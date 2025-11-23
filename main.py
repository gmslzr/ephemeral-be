from typing import Union
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello, World!"}

@app.get("/healthcheck")
def read_root() -> dict[str, str]:
    return {"status": "gucci"}