"""Moliya: xarajatlar va daromad hisobi — sherik (investor) uchun shaffoflik.

Daromad mavjud ma'lumotlardan hisoblanadi (yangi narsa kiritish shart emas):
  • tayyor mebel — «🤝 Mijoz qabul qildi» bo'lgan buyurtmalar: tushum = buyurtma summasi,
    tannarx = mahsulotlarning kirim narxi (admin kiritgan bo'lsa);
  • o'lchamga — «🤝 Yakunlandi» bo'lgan arizalar: tushum = kelishilgan narx, tannarx = ustaxonaga to'lov.
Xarajatlar (ijara, reklama, maosh va h.k.) — shu modulda alohida jadvalda saqlanadi.
"""
import csv
import io
import json
import os
import re
import time
import uuid

TZ = 5 * 3600  # Toshkent

CATS = {
    "material": "🪵 Material",
    "ustaxona": "🏭 Ustaxona / usta",
    "reklama": "📣 Reklama",
    "ijara": "🏠 Ijara",
    "maosh": "👷 Maosh",
    "transport": "🚚 Transport",
    "asbob": "🛠 Asbob-uskuna",
    "kommunal": "💡 Kommunal",
    "soliq": "🧾 Soliq",
    "boshqa": "📦 Boshqa",
}
# botga yozilganda turini so'z bo'yicha topish
ALIASES = {
    "material": ("material", "lmdf", "ldsp", "mdf", "plita", "furnitura", "kromka", "material"),
    "ustaxona": ("ustaxona", "usta", "sex", "seh", "ishlab"),
    "reklama": ("reklama", "instagram", "insta", "target", "telegram", "olx", "banner", "smm", "facebook", "meta"),
    "ijara": ("ijara", "arenda", "rent"),
    "maosh": ("maosh", "oylik", "zarplata", "ish haqi", "ishhaqi"),
    "transport": ("transport", "dostavka", "yetkazish", "taksi", "benzin", "yoqilg'i", "mashina", "yuk"),
    "asbob": ("asbob", "uskuna", "instrument", "stanok", "kompyuter"),
    "kommunal": ("kommunal", "svet", "elektr", "gaz", "suv", "internet", "telefon"),
    "soliq": ("soliq", "nalog", "bank", "komissiya"),
    "boshqa": ("boshqa",),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, amount INTEGER, cat TEXT DEFAULT 'boshqa',
    note TEXT DEFAULT '', photo TEXT DEFAULT '', tg_photo TEXT DEFAULT '', by_name TEXT DEFAULT '',
    created INTEGER, deleted INTEGER DEFAULT 0, deleted_by TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS capital (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, partner TEXT, amount INTEGER, kind TEXT DEFAULT 'in',
    note TEXT DEFAULT '', by_name TEXT DEFAULT '', created INTEGER, deleted INTEGER DEFAULT 0, deleted_by TEXT DEFAULT ''
);
"""

# Sheriklar: foyda teng (50/50) bo'linadi. Kapital har biri bo'yicha alohida hisoblanadi.
PARTNERS = ["Ravshanbek", "Shaxzod"]
PARTNER_ALIASES = {
    "Ravshanbek": ("ravshanbek", "ravshan", "равшанбек", "равшан"),
    "Shaxzod": ("shaxzod", "shahzod", "shohzod", "shoxzod", "шахзод", "шохзод"),
}


class FinanceError(Exception):
    pass


def money(n) -> str:
    return f"{int(n or 0):,}".replace(",", " ") + " so'm"


def short_money(n) -> str:
    n = int(n or 0)
    a = abs(n)
    if a >= 1_000_000:
        v = f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{v} mln"
    if a >= 1000:
        return f"{round(n / 1000)} ming"
    return str(n)


def parse_amount(text: str):
    """«500000», «500 000», «1,5 mln», «1.5mln», «800k», «300 ming» → (summa, qolgan matn)."""
    s = (text or "").strip()
    m = re.match(r"^\s*([\d][\d\s.,]*)\s*(mln|million|млн|m\b|ming|минг|k\b|к\b|тыс)?\.?", s, re.I)
    if not m:
        return 0, s
    num, unit = m.group(1).strip(), (m.group(2) or "").lower()
    rest = s[m.end():].strip()
    if unit:
        num = num.replace(" ", "").replace(",", ".")
        try:
            v = float(num)
        except ValueError:
            return 0, s
        mult = 1_000_000 if unit in ("mln", "million", "млн", "m") else 1000
        return int(round(v * mult)), rest
    digits = re.sub(r"\D", "", num)
    return (int(digits) if digits else 0), rest


def guess_cat(text: str):
    """Matnning birinchi so'zi tur bo'lsa — (tur, qolgan izoh), aks holda butun matn bo'yicha taxmin."""
    t = (text or "").strip()
    first = t.split(maxsplit=1)
    low = t.lower()
    if first:
        w = first[0].lower().strip(".,:;-")
        for cat, words in ALIASES.items():
            if w == cat or w in words:
                return cat, (first[1] if len(first) > 1 else "").strip()
    for cat, words in ALIASES.items():
        if any(x in low for x in words):
            return cat, t
    return "boshqa", t


def find_partner(text: str):
    """Matnning birinchi so'zi sherik ismi bo'lsa — (ism, qolgan matn), aks holda ("", matn)."""
    t = (text or "").strip()
    parts = t.split(maxsplit=1)
    if not parts:
        return "", t
    w = parts[0].lower().strip(".,:;-")
    for name, words in PARTNER_ALIASES.items():
        if w == name.lower() or w in words:
            return name, (parts[1] if len(parts) > 1 else "").strip()
    return "", t


def local_day(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts + TZ))


def day_start(day: str) -> int:
    import calendar
    y, m, d = (int(x) for x in day.split("-"))
    return calendar.timegm((y, m, d, 0, 0, 0)) - TZ


def month_range(ym: str) -> tuple:
    import calendar
    y, m = (int(x) for x in ym.split("-"))
    a = calendar.timegm((y, m, 1, 0, 0, 0)) - TZ
    y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
    return a, calendar.timegm((y2, m2, 1, 0, 0, 0)) - TZ


MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def month_name(ym: str) -> str:
    y, m = ym.split("-")
    return f"{MONTHS[int(m) - 1].capitalize()} {y}"


def _done_ts(row: dict) -> int:
    for e in reversed(row.get("events") or []):
        if e and e[0] == "done":
            return int(e[1])
    return int(row.get("updated") or row.get("created") or 0)


class Finance:
    def __init__(self, shop, cs, photo_dir: str):
        self.shop, self.cs, self.db = shop, cs, shop.db
        self.photo_dir = photo_dir
        os.makedirs(photo_dir, exist_ok=True)
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ------------------------------------------------ xarajatlar
    def add(self, amount: int, cat: str, note: str = "", day: str = "", photo: bytes = b"", tg_photo: str = "",
            by: str = "") -> dict:
        amount = int(amount or 0)
        if amount <= 0:
            raise FinanceError("Summani kiriting (masalan: 500000)")
        if amount > 10_000_000_000:
            raise FinanceError("Summa juda katta — tekshirib qayta kiriting")
        cat = cat if cat in CATS else "boshqa"
        now = int(time.time())
        ts = now
        if day:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise FinanceError("Sana noto'g'ri")
            ts = day_start(day) + 12 * 3600
            if ts > now + 86400:
                raise FinanceError("Kelajakdagi sana kiritib bo'lmaydi")
        fname = ""
        if photo:
            fname = self._save_photo(photo)
        cur = self.db.execute(
            "INSERT INTO expenses(ts,amount,cat,note,photo,tg_photo,by_name,created) VALUES (?,?,?,?,?,?,?,?)",
            (ts, amount, cat, (note or "").strip()[:300], fname, tg_photo or "", (by or "")[:80], now))
        self.db.commit()
        return self.get(cur.lastrowid)

    def _save_photo(self, data: bytes) -> str:
        try:
            return os.path.basename(self.shop._save_jpeg(data, self.photo_dir, 1600, 82))
        except Exception as e:  # noqa: BLE001
            raise FinanceError(f"Rasmni saqlab bo'lmadi: {e}")

    def set_tg_photo(self, eid: int, file_id: str):
        self.db.execute("UPDATE expenses SET tg_photo=? WHERE id=?", (file_id, eid))
        self.db.commit()

    def get(self, eid: int) -> dict:
        r = self.db.execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone()
        if not r:
            raise FinanceError("Xarajat topilmadi")
        return self._exp(r)

    @staticmethod
    def _exp(r) -> dict:
        d = dict(r)
        d["cat_name"] = CATS.get(d["cat"], d["cat"])
        d["day"] = local_day(d["ts"])
        d["has_photo"] = bool(d.get("photo") or d.get("tg_photo"))
        return d

    def photo_path(self, e: dict) -> str:
        if not e.get("photo"):
            return ""
        p = os.path.join(self.photo_dir, os.path.basename(e["photo"]))
        return p if os.path.isfile(p) else ""

    def delete(self, eid: int, by: str = "") -> dict:
        e = self.get(eid)
        if e["deleted"]:
            raise FinanceError("Bu xarajat allaqachon o'chirilgan")
        self.db.execute("UPDATE expenses SET deleted=1, deleted_by=? WHERE id=?", ((by or "")[:80], eid))
        self.db.commit()
        return self.get(eid)

    def expenses(self, a: int, b: int) -> list:
        return [self._exp(r) for r in self.db.execute(
            "SELECT * FROM expenses WHERE deleted=0 AND ts>=? AND ts<? ORDER BY ts DESC, id DESC", (a, b))]

    def last_expenses(self, n: int = 10) -> list:
        return [self._exp(r) for r in self.db.execute(
            "SELECT * FROM expenses WHERE deleted=0 ORDER BY id DESC LIMIT ?", (n,))]

    # ------------------------------------------------ kapital (sheriklar kiritgan / qaytarib olgan pul)
    def add_capital(self, partner: str, amount: int, kind: str = "in", note: str = "", day: str = "", by: str = "") -> dict:
        if partner not in PARTNERS:
            raise FinanceError("Sherik ismini yozing: " + " yoki ".join(PARTNERS))
        amount = int(amount or 0)
        if amount <= 0:
            raise FinanceError("Summani kiriting (masalan: 5000000 yoki 5mln)")
        if amount > 10_000_000_000:
            raise FinanceError("Summa juda katta — tekshirib qayta kiriting")
        kind = "out" if kind == "out" else "in"
        if kind == "out" and amount > self.capital_totals()[partner]["net"]:
            raise FinanceError(f"{partner} kapitalida buncha pul yo'q "
                               f"(hozir: {money(self.capital_totals()[partner]['net'])})")
        now = int(time.time())
        ts = now
        if day:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise FinanceError("Sana noto'g'ri")
            ts = day_start(day) + 12 * 3600
            if ts > now + 86400:
                raise FinanceError("Kelajakdagi sana kiritib bo'lmaydi")
        cur = self.db.execute(
            "INSERT INTO capital(ts,partner,amount,kind,note,by_name,created) VALUES (?,?,?,?,?,?,?)",
            (ts, partner, amount, kind, (note or "").strip()[:300], (by or "")[:80], now))
        self.db.commit()
        return self.get_capital(cur.lastrowid)

    def get_capital(self, cid: int) -> dict:
        r = self.db.execute("SELECT * FROM capital WHERE id=?", (cid,)).fetchone()
        if not r:
            raise FinanceError("Kapital yozuvi topilmadi")
        d = dict(r)
        d["day"] = local_day(d["ts"])
        d["when"] = time.strftime("%d.%m.%Y, %H:%M", time.gmtime(d["ts"] + TZ))
        return d

    def delete_capital(self, cid: int, by: str = "") -> dict:
        c = self.get_capital(cid)
        if c["deleted"]:
            raise FinanceError("Bu yozuv allaqachon o'chirilgan")
        self.db.execute("UPDATE capital SET deleted=1, deleted_by=? WHERE id=?", ((by or "")[:80], cid))
        self.db.commit()
        return self.get_capital(cid)

    def capitals(self, a: int = 0, b: int = 2 ** 62) -> list:
        return [self.get_capital(r["id"]) for r in self.db.execute(
            "SELECT id FROM capital WHERE deleted=0 AND ts>=? AND ts<? ORDER BY ts DESC, id DESC", (a, b))]

    def last_capitals(self, n: int = 10) -> list:
        return [self.get_capital(r["id"]) for r in self.db.execute(
            "SELECT id FROM capital WHERE deleted=0 ORDER BY id DESC LIMIT ?", (n,))]

    def capital_totals(self, until: int = 2 ** 62) -> dict:
        """Har bir sherik: kiritgan, qaytarib olgan, oborotdagi (net). Oxirida «_all» — umumiy."""
        out = {p: {"in": 0, "out": 0, "net": 0} for p in PARTNERS}
        for r in self.db.execute("SELECT partner, kind, SUM(amount) s FROM capital WHERE deleted=0 AND ts<? "
                                 "GROUP BY partner, kind", (until,)):
            d = out.setdefault(r["partner"], {"in": 0, "out": 0, "net": 0})
            d["out" if r["kind"] == "out" else "in"] += int(r["s"] or 0)
        for d in out.values():
            d["net"] = d["in"] - d["out"]
        out["_all"] = {k: sum(v[k] for p, v in out.items() if p != "_all") for k in ("in", "out", "net")}
        return out

    # ------------------------------------------------ savdolar (daromad)
    def order_sale(self, o: dict) -> dict:
        items = o.get("items") or []
        known = [i for i in items if (i.get("sup") or {}).get("cost")]
        cost = sum(int(i["sup"]["cost"]) * int(i.get("qty") or 1) for i in known)
        income = int(o.get("total") or 0)
        names = ", ".join(f"{i.get('name', '')}" + (f" × {i['qty']}" if int(i.get("qty") or 1) > 1 else "") for i in items)
        return {"kind": "o", "id": o["id"], "ts": _done_ts(o), "type": "Tayyor mebel", "items": names,
                "phone": o.get("phone") or "", "income": income, "cost": cost,
                "cost_known": bool(items) and len(known) == len(items), "cost_partial": 0 < len(known) < len(items),
                "profit": income - cost}

    def custom_sale(self, r: dict) -> dict:
        import custom as cust
        kinds = r.get("kinds") or [r.get("kind")]
        names = ", ".join(cust.KINDS.get(k, {}).get("uz", k) for k in kinds if k)
        if r.get("model_name"):
            names += f" ({r['model_name']})"
        income, cost = int(r.get("price") or 0), int(r.get("workshop_cost") or 0)
        return {"kind": "c", "id": r["id"], "ts": _done_ts(r), "type": "O'lchamga", "items": names or "Mebel",
                "phone": r.get("phone") or "", "income": income, "cost": cost, "cost_known": bool(cost),
                "cost_partial": False, "profit": income - cost, "workshop": r.get("workshop") or ""}

    def sales(self, a: int, b: int) -> list:
        out = []
        for row in self.db.execute("SELECT * FROM orders WHERE status='done' AND updated>=?", (a,)):
            o = self.shop._order(row)
            s = self.order_sale(o)
            if a <= s["ts"] < b:
                out.append(s)
        for row in self.db.execute("SELECT * FROM custom_requests WHERE status='done' AND updated>=?", (a,)):
            r = self.cs._row(row)
            s = self.custom_sale(r)
            if a <= s["ts"] < b:
                out.append(s)
        return sorted(out, key=lambda x: -x["ts"])

    def pipeline(self) -> dict:
        """Hali yakunlanmagan, lekin kelishilgan ishlar (shartnoma bor) — kelajakdagi tushum."""
        rows = [self.cs._row(r) for r in self.db.execute(
            "SELECT * FROM custom_requests WHERE status IN ('contract','production','ready','delivered')")]
        orders = [self.shop._order(r) for r in self.db.execute(
            "SELECT * FROM orders WHERE status IN ('confirmed','delivering','delivered','assembled')")]
        return {"n": len(rows) + len(orders),
                "sum": sum(int(r.get("price") or 0) for r in rows) + sum(int(o.get("total") or 0) for o in orders),
                "prepay": sum(int(r.get("prepay") or 0) for r in rows) + sum(int(o.get("prepay") or 0) for o in orders)}

    # ------------------------------------------------ hisobot
    def summary(self, a: int, b: int) -> dict:
        sales, exps = self.sales(a, b), self.expenses(a, b)
        income = sum(s["income"] for s in sales)
        cost = sum(s["cost"] for s in sales)
        by_cat = {}
        for e in exps:
            by_cat[e["cat"]] = by_cat.get(e["cat"], 0) + e["amount"]
        exp_sum = sum(by_cat.values())
        gross = income - cost
        return {"income": income, "cost": cost, "gross": gross, "expenses": exp_sum, "net": gross - exp_sum,
                "sales_n": len(sales), "exp_n": len(exps),
                "no_cost": sum(1 for s in sales if not s["cost_known"]),
                "by_cat": [{"cat": k, "name": CATS.get(k, k), "sum": v} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
                "sales": sales, "exps": exps}

    def months(self, n: int = 12) -> list:
        t = time.gmtime(time.time() + TZ)
        y, m = t.tm_year, t.tm_mon
        out = []
        for _ in range(n):
            ym = f"{y:04d}-{m:02d}"
            a, b = month_range(ym)
            s = self.summary(a, b)
            out.append({"ym": ym, "name": month_name(ym), "income": s["income"], "cost": s["cost"],
                        "expenses": s["expenses"], "net": s["net"]})
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        return out[::-1]

    def report_text(self, a: int, b: int, title: str) -> str:
        s = self.summary(a, b)
        lines = [f"📊 <b>{title}</b>", "",
                 f"💰 Tushum: <b>{money(s['income'])}</b> ({s['sales_n']} ta savdo)",
                 f"📦 Tannarx (mahsulot / ustaxona): {money(s['cost'])}",
                 f"📈 Yalpi foyda: <b>{money(s['gross'])}</b>",
                 f"🧾 Xarajatlar: {money(s['expenses'])} ({s['exp_n']} ta)"]
        for c in s["by_cat"]:
            lines.append(f"     {c['name']}: {money(c['sum'])}")
        lines.append(f"\n✅ <b>Sof foyda: {money(s['net'])}</b>")
        lines += [""] + split_lines(s["net"])
        lines += [""] + capital_lines(self.capital_totals(b), self.capitals(a, b))
        if s["no_cost"]:
            lines.append(f"\nℹ️ {s['no_cost']} ta savdoda tannarx kiritilmagan — foydasi to'liq hisoblanmagan.")
        p = self.pipeline()
        if p["n"]:
            lines.append(f"\n⏳ Jarayonda: {p['n']} ta ish, {money(p['sum'])}"
                         + (f" (oldindan olingan: {money(p['prepay'])})" if p["prepay"] else ""))
        return "\n".join(lines)

    def csv_bytes(self, a: int, b: int) -> bytes:
        s = self.summary(a, b)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["SAVDOLAR"])
        w.writerow(["Sana", "Turi", "Raqam", "Mahsulot", "Mijoz telefoni", "Tushum", "Tannarx", "Foyda", "Izoh"])
        for x in s["sales"]:
            w.writerow([local_day(x["ts"]), x["type"], x["id"], x["items"], x["phone"], x["income"], x["cost"], x["profit"],
                        "" if x["cost_known"] else "tannarx to'liq kiritilmagan"])
        w.writerow([])
        w.writerow(["XARAJATLAR"])
        w.writerow(["Sana", "Raqam", "Turi", "Summa", "Izoh", "Kiritgan"])
        for e in s["exps"]:
            w.writerow([e["day"], e["id"], CATS.get(e["cat"], e["cat"]).split(" ", 1)[-1], e["amount"], e["note"], e["by_name"]])
        w.writerow([])
        w.writerow(["KAPITAL"])
        w.writerow(["Sana", "Raqam", "Sherik", "Turi", "Summa", "Izoh", "Kiritgan"])
        for c in self.capitals(a, b):
            w.writerow([c["day"], c["id"], c["partner"], "Kiritdi" if c["kind"] == "in" else "Qaytarib oldi",
                        c["amount"], c["note"], c["by_name"]])
        w.writerow([])
        w.writerow(["FOYDA TAQSIMOTI (teng)"])
        share = s["net"] // len(PARTNERS)
        for i, p in enumerate(PARTNERS):
            w.writerow([p, s["net"] - share * (len(PARTNERS) - 1) if i == 0 else share])
        w.writerow([])
        w.writerow(["JAMI"])
        for k, v in (("Tushum", s["income"]), ("Tannarx", s["cost"]), ("Yalpi foyda", s["gross"]),
                     ("Xarajatlar", s["expenses"]), ("Sof foyda", s["net"])):
            w.writerow([k, v])
        return ("﻿" + buf.getvalue()).encode("utf-8")


# ------------------------------------------------ xabar matnlari (sherik guruhi)
def sale_text(s: dict) -> str:
    e = lambda x: str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    head = "🛋 Tayyor mebel" if s["kind"] == "o" else "📐 O'lchamga buyurtma"
    lines = [f"💰 <b>Savdo yakunlandi</b> — {head} #{s['id']}",
             f"🪑 {e(s['items'])}",
             f"📞 {e(s['phone'])}",
             "",
             f"Tushum: <b>{money(s['income'])}</b>"]
    if s["cost"]:
        lines.append(f"Tannarx{' (ustaxona)' if s['kind'] == 'c' else ''}: {money(s['cost'])}")
        lines.append(f"📈 Foyda: <b>{money(s['profit'])}</b>"
                     + (" (ba'zi mahsulotlar kirim narxisiz)" if s.get("cost_partial") else ""))
    else:
        lines.append("ℹ️ Tannarx kiritilmagan — foyda hisoblanmadi")
    return "\n".join(lines)


def split_lines(net: int) -> list:
    """Sof foyda (yoki zarar) sheriklar o'rtasida teng bo'linadi."""
    n = len(PARTNERS)
    share = net // n
    title = "🤝 <b>Foyda taqsimoti (50/50):</b>" if net >= 0 else "🤝 <b>Zarar taqsimoti (50/50):</b>"
    out = [title]
    for i, p in enumerate(PARTNERS):
        v = net - share * (n - 1) if i == 0 else share   # qoldiq so'm birinchi sherikka
        out.append(f"• {p}: <b>{money(v)}</b>")
    return out


def capital_lines(tot: dict, moves: list = None) -> list:
    out = ["💼 <b>Kapital holati:</b>"]
    for p in PARTNERS:
        d = tot.get(p) or {"in": 0, "out": 0, "net": 0}
        out.append(f"• {p} kiritgan: {money(d['in'])}" + (f" (qaytarib olgan: {money(d['out'])})" if d["out"] else ""))
    out.append(f"• Oborotdagi jami kapital: <b>{money(tot['_all']['net'])}</b>")
    if moves:
        ins = sum(c["amount"] for c in moves if c["kind"] == "in")
        outs = sum(c["amount"] for c in moves if c["kind"] == "out")
        out.append(f"  Shu davrda: +{money(ins)} kiritildi" + (f", −{money(outs)} qaytarildi" if outs else ""))
    return out


def capital_text(c: dict, tot: dict, deleted: bool = False) -> str:
    e = lambda v: str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if deleted:
        head = f"🗑 <b>Kapital yozuvi #{c['id']} bekor qilindi</b>"
    elif c["kind"] == "in":
        head = f"💰 <b>KAPITAL KIRITILDI</b> (#{c['id']})"
    else:
        head = f"💸 <b>KAPITAL QAYTARIB OLINDI</b> (#{c['id']})"
    lines = [head, "",
             f"👤 Kim: <b>{e(c['partner'])}</b>",
             f"💵 Summa: <b>{money(c['amount'])}</b>",
             f"📝 Maqsad: {e(c['note']) if c.get('note') else '—'}",
             f"📅 Sana: {c['when']}", "",
             "📊 <b>Jami kiritilgan kapital:</b>"]
    for p in PARTNERS:
        d = tot.get(p) or {"net": 0}
        lines.append(f"• {p}: {money(d['net'])}")
    lines.append(f"• Umumiy: <b>{money(tot['_all']['net'])}</b>")
    return "\n".join(lines)


CAPITAL_HELP = ("💰 <b>Kapital kiritish</b>\n"
                "Yozing: <code>/kapital ism summa maqsad</code>\n\n"
                "Misollar:\n"
                "<code>/kapital Shaxzod 5mln material xaridi</code>\n"
                "<code>/kapital Ravshanbek 3 000 000 oborot uchun</code>\n\n"
                "Sherik pulini qaytarib olsa:\n"
                "<code>/kapital_qaytar Shaxzod 1mln</code>\n\n"
                "Ro'yxat: /kapitallar\nO'chirish: <code>/kapital_ochir 3</code>\n\n"
                "Sheriklar: " + ", ".join(PARTNERS) + ". Kapital daromad hisoblanmaydi — foyda 50/50 bo'linadi.")


def expense_text(x: dict, deleted: bool = False) -> str:
    e = lambda v: str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if deleted:
        return (f"🗑 <b>Xarajat #{x['id']} bekor qilindi</b>\n{x['cat_name']}: {money(x['amount'])}"
                + (f"\n📝 {e(x['note'])}" if x.get("note") else ""))
    return (f"🧾 <b>Xarajat #{x['id']}</b> — {x['cat_name']}\n"
            f"Summa: <b>{money(x['amount'])}</b>\n📅 {x['day']}"
            + (f"\n📝 {e(x['note'])}" if x.get("note") else ""))


HELP = ("🧾 <b>Xarajat kiritish</b>\n"
        "Yozing: <code>/xarajat summa turi izoh</code>\n\n"
        "Misollar:\n"
        "<code>/xarajat 500000 reklama Instagram</code>\n"
        "<code>/xarajat 1.5mln ijara oktabr</code>\n"
        "<code>/xarajat 300 ming transport yuk tashish</code>\n\n"
        "Chek rasmini ham yuborishingiz mumkin — rasm izohiga xuddi shunday yozing.\n\n"
        "Turlari: " + ", ".join(k for k in CATS) + "\n\n"
        "Oxirgi xarajatlar: /xarajatlar\nO'chirish: <code>/xarajat_ochir 12</code>\nHisobot: /hisobot")
