from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "ok", "message": "API is working"}

@app.get("/alg/healthz")
def health():
    return {"status": "healthy", "version": "test"}