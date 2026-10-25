"""Mijozlar fikri: buyurtma yoki ariza yakunlangach bot baho (1–5 ⭐) va ixtiyoriy matn/rasm so'raydi.
Admin Telegram'dagi tugma bilan «✅ Ko'rsatish» yoki «🙈 Yashirish»ni tanlaydi — ko'rsatilganlar saytda va ilovada chiqadi.
"""
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, ref_id INTEGER NOT NULL, user_id INTEGER,
    name TEXT DEFAULT '', rating INTEGER DEFAULT 0, text TEXT DEFAULT '', photo TEXT DEFAULT '',
    status TEXT DEFAULT 'pending', lang TEXT DEFAULT 'uz', created INTEGER, updated INTEGER,
    UNIQUE(kind, ref_id)
);
"""
STATUSES = ("pending", "shown", "hidden")


def short_name(name: str) -> str:
    """«Ali Valiyev» → «Ali V.» (mijozning to'liq ismi ommaga chiqmasin)."""
    parts = (name or "").split()
    if not parts:
        return "Mijoz"
    return parts[0][:20] + (f" {parts[1][0]}." if len(parts) > 1 and parts[1] else "")


class ReviewStore:
    def __init__(self, shop):
        self.db = shop.db
        self.db.executescript(SCHEMA)
        self.db.commit()

    def get(self, rid: int) -> dict:
        r = self.db.execute("SELECT * FROM reviews WHERE id=?", (rid,)).fetchone()
        if not r:
            raise KeyError(rid)
        return dict(r)

    def by_ref(self, kind: str, ref_id: int):
        r = self.db.execute("SELECT * FROM reviews WHERE kind=? AND ref_id=?", (kind, ref_id)).fetchone()
        return dict(r) if r else None

    def rate(self, kind: str, ref_id: int, user_id: int, name: str, rating: int, lang: str = "uz") -> dict:
        rating = max(1, min(5, int(rating)))
        now = int(time.time())
        old = self.by_ref(kind, ref_id)
        if old:
            self.db.execute("UPDATE reviews SET rating=?, updated=? WHERE id=?", (rating, now, old["id"]))
            self.db.commit()
            return self.get(old["id"])
        cur = self.db.execute(
            "INSERT INTO reviews(kind, ref_id, user_id, name, rating, status, lang, created, updated) VALUES (?,?,?,?,?,?,?,?,?)",
            (kind, ref_id, user_id, (name or "").strip()[:80], rating, "pending", lang, now, now))
        self.db.commit()
        return self.get(cur.lastrowid)

    def add_text(self, rid: int, text: str):
        r = self.get(rid)
        t = ((r["text"] + "\n") if r["text"] else "") + (text or "").strip()
        self.db.execute("UPDATE reviews SET text=?, updated=? WHERE id=?", (t.strip()[:1000], int(time.time()), rid))
        self.db.commit()

    def add_photo(self, rid: int, path: str):
        self.db.execute("UPDATE reviews SET photo=?, updated=? WHERE id=?", (path, int(time.time()), rid))
        self.db.commit()

    def set_status(self, rid: int, status: str) -> dict:
        if status not in STATUSES:
            raise ValueError(status)
        self.db.execute("UPDATE reviews SET status=?, updated=? WHERE id=?", (status, int(time.time()), rid))
        self.db.commit()
        return self.get(rid)

    def shown(self, limit: int = 30) -> list:
        rows = self.db.execute("SELECT * FROM reviews WHERE status='shown' ORDER BY updated DESC LIMIT ?",
                               (limit,)).fetchall()
        return [dict(r) for r in rows]

    def public(self, limit: int = 30) -> list:
        """Saytda va ilovada ko'rsatish uchun: qisqa ism, baho, matn, rasm."""
        return [{"id": r["id"], "name": short_name(r["name"]), "rating": r["rating"], "text": r["text"],
                 "photo": ("/" + r["photo"]) if r["photo"] else "", "date": time.strftime("%d.%m.%Y", time.gmtime(r["created"] + 5 * 3600))}
                for r in self.shown(limit)]

    def summary(self) -> dict:
        r = self.db.execute("SELECT COUNT(*), COALESCE(AVG(rating),0) FROM reviews WHERE status='shown'").fetchone()
        return {"count": r[0], "avg": round(r[1], 1)}

    def stats(self, since: int = 0, until: int = 2 ** 40) -> dict:
        r = self.db.execute("SELECT COUNT(*), COALESCE(AVG(rating),0) FROM reviews WHERE rating>0 AND created>=? AND created<?",
                            (since, until)).fetchone()
        return {"count": r[0], "avg": round(r[1], 1)}


def stars(n: int) -> str:
    return "⭐" * max(0, min(5, int(n or 0)))


def admin_text(r: dict) -> str:
    import html
    e = lambda s: html.escape(str(s), quote=False)
    what = "Buyurtma" if r["kind"] == "order" else "Ariza (o'lchamga)"
    st = {"pending": "⏳ tekshirilmagan", "shown": "✅ saytda ko'rsatilmoqda", "hidden": "🙈 yashirilgan"}[r["status"]]
    t = (f"💬 <b>Mijoz fikri</b> — {what} #{r['ref_id']}\n{stars(r['rating'])} ({r['rating']}/5)\n"
         f"👤 {e(r['name'])}\n" + (f"\n«{e(r['text'])}»\n" if r["text"] else "") + f"\nHolati: {st}")
    if r["rating"] and r["rating"] <= 3:
        t += "\n\n⚠️ <b>Mijoz norozi — tezda qo'ng'iroq qilib, muammoni hal qiling.</b>"
    return t

