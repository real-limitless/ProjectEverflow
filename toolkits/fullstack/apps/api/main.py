from fastapi import FastAPI

app = FastAPI(title="Everflow Full-stack API")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
