from fastapi import FastAPI

app = FastAPI(title="flair2", version="0.1.0")


@app.get("/api/health")
def health():
    return {"status": "ok"}
