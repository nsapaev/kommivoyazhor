from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, geocode, osrm
from .auth import Me, current_user
from .auth import router as auth_router
from .driver import router as driver_router
from .importer import router as import_router
from .plans import router as plans_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    yield


app = FastAPI(title="Маршруты", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(plans_router)
app.include_router(driver_router)
app.include_router(import_router)


@app.get("/api/health")
def health():
    return {"ok": True, "osrm": osrm.OSRM_URL}


@app.get("/api/geocode")
async def api_geocode(q: str, _: Me = Depends(current_user)):
    try:
        return await geocode.search(q)
    except Exception:
        raise HTTPException(502, "Сервис поиска адресов недоступен, попробуйте позже")


# В продакшене отдаём собранный React из frontend/dist
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    @app.get("/d/{token}", include_in_schema=False)
    def driver_page(token: str):
        """Страница водителя — то же React-приложение, оно само смотрит на адрес."""
        return FileResponse(_dist / "index.html")

    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
