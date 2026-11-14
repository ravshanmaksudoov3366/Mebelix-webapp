"""iSofa Bazis (namuna): mebel loyihalari, detallar, raskroy va smeta — server qismi.

Hisob-kitob brauzerda (webapp/bazis.html). Server faqat loyihalar va narxlarni saqlaydi.
Olib tashlash: app.py dagi `bazis.setup(...)` qatorini va shu faylni o'chirish kifoya.
"""
import json
import time

MAX_PROJECT = 400_000  # bayt


class BazisStore:
    def __init__(self, db):
        self.db = db
        db.execute("CREATE TABLE IF NOT EXISTS bazis_projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, "
                   "client TEXT, data TEXT, total INTEGER DEFAULT 0, author TEXT, created INTEGER, updated INTEGER)")
        db.commit()

    def list(self) -> list:
        rows = self.db.execute("SELECT id,name,client,total,author,created,updated FROM bazis_projects "
                               "ORDER BY updated DESC LIMIT 300").fetchall()
        keys = ("id", "name", "client", "total", "author", "created", "updated")
        return [dict(zip(keys, r)) for r in rows]

    def get(self, pid: int) -> dict | None:
        r = self.db.execute("SELECT id,name,client,data,total,updated FROM bazis_projects WHERE id=?", (pid,)).fetchone()
        if not r:
            return None
        return {"id": r[0], "name": r[1], "client": r[2], "data": json.loads(r[3] or "{}"), "total": r[4],
                "updated": r[5]}

    def save(self, pid: int | None, name: str, client: str, data: dict, total: int, author: str) -> int:
        blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if len(blob) > MAX_PROJECT:
            raise ValueError("Loyiha juda katta")
        now = int(time.time())
        name, client = (name or "Loyiha").strip()[:120], (client or "").strip()[:120]
        if pid and self.db.execute("SELECT 1 FROM bazis_projects WHERE id=?", (pid,)).fetchone():
            self.db.execute("UPDATE bazis_projects SET name=?, client=?, data=?, total=?, updated=? WHERE id=?",
                            (name, client, blob, int(total or 0), now, pid))
        else:
            pid = self.db.execute("INSERT INTO bazis_projects(name,client,data,total,author,created,updated) "
                                  "VALUES (?,?,?,?,?,?,?)", (name, client, blob, int(total or 0), author[:80], now,
                                                            now)).lastrowid
        self.db.commit()
        return pid

    def delete(self, pid: int):
        self.db.execute("DELETE FROM bazis_projects WHERE id=?", (pid,))
        self.db.commit()


def setup(app, web, shop, get_admin, base_dir):
    """Marshrutlarni ulaydi: /bazis sahifasi va /api/admin/bazis/* (faqat admin)."""
    store = BazisStore(shop.db)

    async def page(request):
        return web.FileResponse(base_dir / "webapp" / "bazis.html", headers={"Cache-Control": "no-cache"})

    async def api_list(request):
        get_admin(request)
        return web.json_response({"projects": store.list()})

    async def api_get(request):
        get_admin(request)
        p = store.get(int(request.match_info["id"]))
        if not p:
            return web.json_response({"error": "Loyiha topilmadi"}, status=404)
        return web.json_response({"project": p})

    async def api_save(request):
        u = get_admin(request)
        d = await request.json()
        try:
            pid = store.save(int(d.get("id") or 0) or None, str(d.get("name") or ""), str(d.get("client") or ""),
                             d.get("data") or {}, int(d.get("total") or 0),
                             str(u.get("first_name") or u.get("username") or "admin"))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"id": pid})

    async def api_delete(request):
        get_admin(request)
        store.delete(int(request.match_info["id"]))
        return web.json_response({"ok": True})

    async def api_prices(request):
        get_admin(request)
        if request.method == "POST":
            d = await request.json()
            shop.set_setting("bazis_prices", json.dumps(d.get("prices") or {}, ensure_ascii=False)[:50_000])
        try:
            prices = json.loads(shop.settings().get("bazis_prices") or "{}")
        except ValueError:
            prices = {}
        return web.json_response({"prices": prices})

    app.router.add_get("/bazis", page)
    app.router.add_get("/api/admin/bazis/projects", api_list)
    app.router.add_post("/api/admin/bazis/projects", api_save)
    app.router.add_get("/api/admin/bazis/projects/{id}", api_get)
    app.router.add_post("/api/admin/bazis/projects/{id}/delete", api_delete)
    app.router.add_get("/api/admin/bazis/prices", api_prices)
    app.router.add_post("/api/admin/bazis/prices", api_prices)
    return store
