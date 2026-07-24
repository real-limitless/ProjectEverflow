from fastapi import FastAPI

app = FastAPI(title="Everflow Python API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, bool | str]:
    return {"ok": True, "service": "everflow-toolkit-python-api"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Python API starter — edit main.py",
        "docs": "/docs",
    }
