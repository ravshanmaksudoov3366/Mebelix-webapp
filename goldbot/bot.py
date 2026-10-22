"""Oltin savdo boti: MetaApi orqali MT5 hisobida avtomatik savdo, Telegram orqali boshqaruv."""
import html
import logging
import os
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import backtest
from metaapi import MetaApi, MetaApiError, drop_unclosed, parse_time
from risk import lot_size
from strategy import Params, evaluate, in_session, managed_stop
from telegram import Telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("goldbot")
UTC = timezone.utc


def env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


class Config:
    def __init__(self):
        self.metaapi_token = os.getenv("METAAPI_TOKEN", "")
        self.account_id = os.getenv("METAAPI_ACCOUNT_ID", "")
        self.tg_token = os.getenv("TELEGRAM_TOKEN", "")
        self.owner_id = int(os.getenv("OWNER_ID", "0") or 0)
        self.symbol = os.getenv("SYMBOL", "")  # bo'sh bo'lsa — avtomatik topiladi (GOLD / XAUUSD)
        self.risk = env_float("RISK_PERCENT", 5)
        self.max_consec_losses = int(env_float("MAX_CONSEC_LOSSES", 5))
        self.max_trades_per_day = int(env_float("MAX_TRADES_PER_DAY", 10))
        self.max_drawdown = env_float("MAX_DRAWDOWN_PCT", 50)
        self.auto_start = os.getenv("AUTO_START", "0") == "1"
        self.magic = int(env_float("MAGIC", 770077))
        self.backtest_days = int(env_float("BACKTEST_DAYS", 180))
        self.port = int(env_float("PORT", 10000))

    def missing(self):
        names = {"METAAPI_TOKEN": self.metaapi_token, "METAAPI_ACCOUNT_ID": self.account_id,
                 "TELEGRAM_TOKEN": self.tg_token, "OWNER_ID": self.owner_id}
        return [k for k, v in names.items() if not v]


def find_symbol(names):
    """Brokerdagi oltin belgisini topadi: XM'da odatda GOLD, boshqalarda XAUUSD (qo'shimchasi bilan)."""
    names = list(names)
    for pref in ("XAUUSD", "GOLD"):
        exact = [n for n in names if n.upper() == pref]
        if exact:
            return exact[0]
    for pref in ("XAUUSD", "GOLD"):
        cands = sorted((n for n in names if n.upper().startswith(pref)), key=len)
        cands = [n for n in cands if "EUR" not in n.upper() and "AUD" not in n.upper()]
        if cands:
            return cands[0]
    return None


def esc(x):
    return html.escape(str(x), quote=False)


def fmt_money(x, cur="USD"):
    return f"{x:,.2f} {cur}".replace(",", " ")


class Bot:
    def __init__(self, cfg: Config, api: MetaApi, tg: Telegram, params: Params = Params()):
        self.cfg, self.api, self.tg, self.p = cfg, api, tg, params
        self.lock = threading.RLock()
        self.paused = not cfg.auto_start
        self.risk = cfg.risk
        self.max_consec = cfg.max_consec_losses
        self.symbol = None
        self.spec = {}
        self.point = 0.01
        self.currency = "USD"
        self.known_positions = {}      # id -> pozitsiya (yopilishini aniqlash uchun)
        self.last_bar_eval = None      # oxirgi tekshirilgan M15 sham vaqti
        self.peak_equity = None
        self.confirm_close = False
        self.last_daily_report = None
        self.status_line = "ishga tushyapti"
        self.backtest_running = False
        self.last_entry_time = None
        self.missing_ticks = {}        # pozitsiya ro'yxatda nechta tekshiruvdan beri yo'q
        self.modified = {}             # pozitsiya -> oxirgi o'rnatilgan stop (takror yubormaslik uchun)

    # ---------- tayyorlov ----------
    def setup(self):
        acc = self.api.ensure_connected()
        names = self.api.symbols()
        self.symbol = self.cfg.symbol or find_symbol(names)
        if not self.symbol:
            raise MetaApiError("brokerda oltin belgisi topilmadi (GOLD/XAUUSD). SYMBOL o'zgaruvchisini kiriting")
        self.spec = self.api.spec(self.symbol) or {}
        digits = int(self.spec.get("digits", 2))
        self.point = float(self.spec.get("point") or 10 ** -digits)
        self.api.set_point(self.point)
        info = self.api.account_info() or {}
        self.currency = info.get("currency", "USD")
        self.peak_equity = float(info.get("equity", 0) or 0)
        for p in self.my_positions():
            self.known_positions[p["id"]] = p
        log.info("ulandi: %s, belgi %s, kontrakt %s, valyuta %s", acc.get("server"), self.symbol,
                 self.spec.get("contractSize"), self.currency)
        warn = ""
        if self.currency != "USD":
            warn = (f"\n⚠️ Hisob valyutasi {self.currency}. Lot hajmi USD deb hisoblanadi — "
                    f"risk biroz farq qilishi mumkin.")
        self.tg.send(
            f"✅ <b>Oltin boti ulandi</b>\nServer: {acc.get('server')}, login {acc.get('login')}\n"
            f"Belgi: {self.symbol} (1 lot = {self.spec.get('contractSize')} unsiya)\n"
            f"Balans: {fmt_money(float(info.get('balance', 0)), self.currency)}\n"
            f"Risk: {self.risk:g}% har savdoda, kunlik to'xtash: ketma-ket {self.max_consec} yutqazish"
            f"{warn}\n\n"
            + ("▶️ Savdo YOQILGAN." if not self.paused else
               "⏸ Savdo hozircha PAUZADA. Sinov natijasini ko'rib, «▶️ Boshlash» ni bosing."))

    # ---------- yordamchilar ----------
    def my_positions(self):
        return [p for p in self.api.positions()
                if p.get("symbol") == self.symbol and int(p.get("magic", 0) or 0) == self.cfg.magic]

    def today_stats(self, now=None):
        """(bugungi savdolar soni, oxiridagi ketma-ket yutqazishlar, bugungi natija $)."""
        now = now or datetime.now(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = self.api.deals_between(start - timedelta(days=3), now + timedelta(minutes=1))
        mine = {d.get("positionId") for d in deals
                if int(d.get("magic", 0) or 0) == self.cfg.magic and d.get("entryType") == "DEAL_ENTRY_IN"}
        today = sorted((d for d in deals if d.get("positionId") in mine and parse_time(d["time"]) >= start),
                       key=lambda d: d["time"])
        ins = [parse_time(d["time"]) for d in deals if d.get("positionId") in mine
               and d.get("entryType") == "DEAL_ENTRY_IN"]
        self.last_entry_time = max(ins) if ins else None
        opened = sum(1 for d in today if d.get("entryType") == "DEAL_ENTRY_IN")
        closes = [d for d in today if d.get("entryType") in ("DEAL_ENTRY_OUT", "DEAL_ENTRY_OUT_BY")]
        results = [float(d.get("profit", 0)) + float(d.get("commission", 0)) + float(d.get("swap", 0))
                   for d in closes]
        streak = 0
        for r in reversed(results):
            if r < 0:
                streak += 1
            else:
                break
        return opened, streak, sum(results)

    def position_result(self, pid):
        deals = self.api.deals_for_position(pid)
        return sum(float(d.get("profit", 0)) + float(d.get("commission", 0)) + float(d.get("swap", 0))
                   for d in deals if d.get("entryType") in ("DEAL_ENTRY_OUT", "DEAL_ENTRY_OUT_BY"))

    # ---------- asosiy sikl ----------
    def tick(self, now=None):
        now = now or datetime.now(UTC)
        with self.lock:
            positions = self.my_positions()
            self._detect_closed(positions)
            info = self.api.account_info() or {}
            equity = float(info.get("equity", 0) or 0)
            self._check_drawdown(equity)
            if now.weekday() == 4 and (now.hour, now.minute) >= (20, 30) and positions:
                self._close_all("juma kechqurun — dam olish kunlari narx sakrashidan himoya")
                return
            for p in positions:
                self._manage(p)
            self._maybe_daily_report(now, info)
            bar = self._last_closed_m15(now)
            if self.last_bar_eval == bar:
                return
            self.last_bar_eval = bar
            if self.paused or positions:
                return
            self._maybe_enter(now, equity)

    @staticmethod
    def _last_closed_m15(now):
        t = now.replace(second=0, microsecond=0)
        return t - timedelta(minutes=t.minute % 15) - timedelta(minutes=15)

    def _detect_closed(self, positions):
        current = {p["id"]: p for p in positions}
        for pid, old in list(self.known_positions.items()):
            if pid in current:
                self.missing_ticks.pop(pid, None)
                continue
            self.missing_ticks[pid] = self.missing_ticks.get(pid, 0) + 1
            if self.missing_ticks[pid] < 2:  # broker ro'yxati bir lahzaga bo'sh kelishi mumkin
                continue
            del self.known_positions[pid]
            self.missing_ticks.pop(pid, None)
            self.modified.pop(pid, None)
            try:
                res = self.position_result(pid)
            except MetaApiError:
                res = float(old.get("profit", 0) or 0)
            side = "SOTIB OLISH" if old.get("type") == "POSITION_TYPE_BUY" else "SOTISH"
            emoji = "✅" if res >= 0 else "🔻"
            _, streak, day = self.today_stats()
            extra = ""
            if streak >= self.max_consec:
                extra = f"\n⛔ Bugun ketma-ket {streak} yutqazish — bugunga savdo to'xtatildi, ertaga davom etadi."
            self.tg.send(f"{emoji} Savdo yopildi ({side} {old.get('volume')} lot): "
                         f"<b>{res:+.2f} {self.currency}</b>\nBugungi natija: {day:+.2f} {self.currency}{extra}")
        for pid, p in current.items():
            self.known_positions[pid] = p
            self.missing_ticks.pop(pid, None)

    def _check_drawdown(self, equity):
        if equity <= 0:
            return
        self.peak_equity = max(self.peak_equity or equity, equity)
        dd = (self.peak_equity - equity) / self.peak_equity * 100
        if dd >= self.cfg.max_drawdown and not self.paused:
            self.paused = True
            self.tg.send(f"🛑 Hisob eng yuqori nuqtasidan {dd:.0f}% pasaydi (chegara {self.cfg.max_drawdown:g}%). "
                         f"Yangi savdolar TO'XTATILDI. Davom ettirish uchun «▶️ Boshlash».")

    def _manage(self, p):
        side = "buy" if p.get("type") == "POSITION_TYPE_BUY" else "sell"
        price = float(p.get("currentPrice") or 0)
        if not price:
            return
        ns = managed_stop(side, float(p["openPrice"]), float(p.get("stopLoss") or 0),
                          float(p.get("takeProfit") or 0), price, self.p)
        if ns is None:
            return
        digits = int(self.spec.get("digits", 2))
        ns = round(ns, digits)
        if self.modified.get(p["id"]) == ns:
            return  # allaqachon yuborilgan, broker ro'yxati hali yangilanmagan
        try:
            body = {"actionType": "POSITION_MODIFY", "positionId": p["id"], "stopLoss": ns}
            if p.get("takeProfit"):
                body["takeProfit"] = float(p["takeProfit"])
            self.api.trade(body)
            self.modified[p["id"]] = ns
            self.tg.send(f"🔒 Stop-loss foydaga surildi: {ns} (savdo endi zarar bilan yopilmaydi)")
        except MetaApiError as e:
            log.warning("stopni surib bo'lmadi: %s", e)

    def _maybe_enter(self, now, equity):
        if not in_session(now, self.p):
            self.status_line = "savdo vaqti emas (07:00–20:00 UTC, ish kunlari)"
            return
        opened, streak, _ = self.today_stats(now)
        if streak >= self.max_consec:
            self.status_line = f"bugun ketma-ket {streak} yutqazish — ertagacha kutyapman"
            return
        if self.last_entry_time and now - self.last_entry_time < timedelta(minutes=15):
            self.status_line = "oxirgi 15 daqiqada savdo ochilgan — kutyapman"
            return
        if opened >= self.cfg.max_trades_per_day:
            self.status_line = "bugungi savdolar chegarasi to'ldi"
            return
        h1 = drop_unclosed(self.api.candles(self.symbol, "1h", backtest.WIN_H1 + 2), "1h", now)
        m15 = drop_unclosed(self.api.candles(self.symbol, "15m", backtest.WIN_M15 + 2), "15m", now)
        sig = evaluate(h1, m15, self.p)
        if sig is None:
            self.status_line = f"signal yo'q (oxirgi tekshiruv {now:%H:%M} UTC)"
            return
        q = self.api.price(self.symbol)
        bid, ask = float(q["bid"]), float(q["ask"])
        entry = ask if sig.side == "buy" else bid
        dist = (entry - sig.sl) if sig.side == "buy" else (sig.sl - entry)
        if dist <= 0:
            self.status_line = "narx stop nuqtasidan o'tib ketgan — signal o'tkazib yuborildi"
            return
        tp = entry + self.p.rr * dist if sig.side == "buy" else entry - self.p.rr * dist  # haqiqiy narxdan RR
        if ask - bid > self.p.max_spread_frac * dist:
            self.status_line = f"spred juda katta ({ask - bid:.2f}) — kirmadim"
            return
        min_stop = float(self.spec.get("stopsLevel", 0) or 0) * self.point
        if dist <= min_stop or abs(tp - entry) <= min_stop:
            self.status_line = "stop broker ruxsat bergan masofadan yaqin — kirmadim"
            return
        vol, risk_money, note = lot_size(equity, self.risk, dist, float(self.spec.get("contractSize", 100)),
                                         float(self.spec.get("minVolume", 0.01)),
                                         float(self.spec.get("maxVolume", 100)),
                                         float(self.spec.get("volumeStep", 0.01)))
        if vol <= 0:
            self.status_line = f"savdo ochilmadi: {note}"
            self.tg.send(f"⚠️ Signal bor edi, lekin savdo ochilmadi: {note}")
            return
        digits = int(self.spec.get("digits", 2))
        body = {"actionType": "ORDER_TYPE_BUY" if sig.side == "buy" else "ORDER_TYPE_SELL",
                "symbol": self.symbol, "volume": vol, "stopLoss": round(sig.sl, digits),
                "takeProfit": round(tp, digits), "magic": self.cfg.magic, "comment": "goldbot"}
        try:
            res = self.api.trade(body)
        except MetaApiError as e:
            time.sleep(5)  # javob kelmay qolgan bo'lsa ham savdo ochilgan bo'lishi mumkin — tekshiramiz
            try:
                opened_anyway = bool(self.my_positions())
            except MetaApiError:
                opened_anyway = False
            if not opened_anyway:
                self.status_line = f"broker savdoni rad etdi: {e}"
                self.tg.send(f"⚠️ Savdo ochilmadi — broker rad etdi: {esc(e)}")
                return
            res = {}
            log.warning("javob kelmadi (%s), lekin pozitsiya ochilgan", e)
        side = "🟢 SOTIB OLDIM" if sig.side == "buy" else "🔴 SOTDIM"
        self.status_line = f"savdo ochildi {now:%H:%M} UTC"
        self.tg.send(f"{side} {self.symbol} {vol} lot ≈ {entry:.{digits}f}\n"
                     f"Stop-loss: {body['stopLoss']}  |  Take-profit: {body['takeProfit']}\n"
                     f"Xavf: ≈{fmt_money(risk_money, self.currency)} ({self.risk:g}%), "
                     f"mo'ljallangan foyda ≈{fmt_money(risk_money * self.p.rr, self.currency)}\n"
                     f"Sabab: {sig.reason}")
        log.info("savdo ochildi: %s %s %s", body, res.get("positionId"), res.get("orderId"))

    def _close_all(self, why):
        closed = 0
        for p in self.my_positions():
            try:
                self.api.trade({"actionType": "POSITION_CLOSE_ID", "positionId": p["id"]})
                closed += 1
            except MetaApiError as e:
                self.tg.send(f"⚠️ Pozitsiya {p['id']} yopilmadi: {esc(e)}")
        if closed:
            self.tg.send(f"❌ {closed} ta pozitsiya yopildi ({why}).")
        return closed

    def _maybe_daily_report(self, now, info):
        if now.hour != 21 or self.last_daily_report == now.date() or now.weekday() >= 5:
            return
        self.last_daily_report = now.date()
        opened, streak, day = self.today_stats(now)
        self.tg.send(f"🌙 Kun yakuni: {opened} ta savdo, natija {day:+.2f} {self.currency}\n"
                     f"Balans: {fmt_money(float(info.get('balance', 0)), self.currency)}")

    # ---------- Telegram buyruqlari ----------
    def handle(self, text):
        t = text.lower().strip()
        if t in ("/start", "📊 holat", "holat", "/holat"):
            return self.cmd_status()
        if t in ("▶️ boshlash", "boshlash", "/boshlash"):
            self.paused = False
            with self.lock:
                info = self.api.account_info() or {}
                self.peak_equity = float(info.get("equity", 0) or 0)
            return self.tg.send(f"▶️ Savdo yoqildi. Risk {self.risk:g}%, kunlik to'xtash: ketma-ket "
                                f"{self.max_consec} yutqazish.")
        if t in ("⏸ to'xtatish", "to'xtatish", "/toxtatish"):
            self.paused = True
            return self.tg.send("⏸ Yangi savdolar to'xtatildi. Ochiq savdo bo'lsa, u o'z stop/take-profit "
                                "bilan yopiladi. Hammasini hozir yopish uchun «❌ Hammasini yopish».")
        if t in ("⚙️ risk", "risk"):
            return self.tg.send(f"Hozirgi risk: <b>{self.risk:g}%</b> har savdoda.\n"
                                f"Kunlik to'xtash: ketma-ket <b>{self.max_consec}</b> yutqazish.\n\n"
                                "O'zgartirish uchun yozing, masalan:\n<code>risk 3</code> (0.5 – 10)\n"
                                "<code>seriya 5</code> (1 – 10)")
        if t.startswith("risk "):
            try:
                v = float(t.split()[1].replace(",", ".").rstrip("%"))
            except (ValueError, IndexError):
                return self.tg.send("Raqam yozing, masalan: risk 3")
            if not 0.5 <= v <= 10:
                return self.tg.send("Risk 0.5% dan 10% gacha bo'lishi mumkin.")
            self.risk = v
            return self.tg.send(f"✅ Risk endi {v:g}% har savdoda (keyingi savdodan).")
        if t.startswith("seriya "):
            try:
                v = int(t.split()[1])
            except (ValueError, IndexError):
                return self.tg.send("Raqam yozing, masalan: seriya 5")
            if not 1 <= v <= 10:
                return self.tg.send("1 dan 10 gacha bo'lishi mumkin.")
            self.max_consec = v
            return self.tg.send(f"✅ Endi bir kunda ketma-ket {v} yutqazishdan keyin bot o'sha kuni to'xtaydi.")
        if t in ("🧪 sinov", "sinov", "/sinov"):
            return self.start_backtest()
        if t in ("📜 tarix", "tarix", "/tarix"):
            return self.cmd_history()
        if t in ("❌ hammasini yopish", "/yopish"):
            self.confirm_close = True
            return self.tg.send("Barcha ochiq savdolar hozirgi narxda yopiladi va bot pauzaga o'tadi.\n"
                                "Tasdiqlash uchun <b>ha yopish</b> deb yozing.")
        if t == "ha yopish" and self.confirm_close:
            self.confirm_close = False
            self.paused = True
            with self.lock:
                n = self._close_all("egasining buyrug'i")
            if not n:
                self.tg.send("Ochiq savdo yo'q edi. Bot pauzada.")
            return None
        return self.tg.send("Pastdagi tugmalardan foydalaning 👇")

    def cmd_status(self):
        with self.lock:
            info = self.api.account_info() or {}
            positions = self.my_positions()
            opened, streak, day = self.today_stats()
        cur = self.currency
        lines = [f"📊 <b>Holat</b>: {'⏸ PAUZA' if self.paused else '▶️ ishlayapti'}",
                 f"Balans: {fmt_money(float(info.get('balance', 0)), cur)}, "
                 f"mablag' (equity): {fmt_money(float(info.get('equity', 0)), cur)}",
                 f"Risk: {self.risk:g}%, kunlik to'xtash: ketma-ket {self.max_consec} yutqazish",
                 f"Bugun: {opened} ta savdo, natija {day:+.2f} {cur}, ketma-ket yutqazish: {streak}",
                 f"Bot: {self.status_line}"]
        for p in positions:
            side = "SOTIB OLINGAN" if p.get("type") == "POSITION_TYPE_BUY" else "SOTILGAN"
            lines.append(f"• {side} {p.get('volume')} lot @ {p.get('openPrice')}, SL {p.get('stopLoss')}, "
                         f"TP {p.get('takeProfit')}, hozir {float(p.get('profit', 0)):+.2f} {cur}")
        if not positions:
            lines.append("Ochiq savdo yo'q.")
        self.tg.send("\n".join(lines))

    def cmd_history(self):
        now = datetime.now(UTC)
        with self.lock:
            deals = self.api.deals_between(now - timedelta(days=30), now)
        mine = {d.get("positionId") for d in deals
                if int(d.get("magic", 0) or 0) == self.cfg.magic and d.get("entryType") == "DEAL_ENTRY_IN"}
        closes = sorted((d for d in deals if d.get("positionId") in mine
                         and d.get("entryType") in ("DEAL_ENTRY_OUT", "DEAL_ENTRY_OUT_BY")),
                        key=lambda d: d["time"])
        if not closes:
            return self.tg.send("📜 Oxirgi 30 kunda yopilgan savdo yo'q.")
        res = [float(d.get("profit", 0)) + float(d.get("commission", 0)) + float(d.get("swap", 0)) for d in closes]
        wins = sum(1 for r in res if r > 0)
        lines = [f"📜 <b>Oxirgi 30 kun</b>: {len(res)} savdo, yutgan {wins}, jami {sum(res):+.2f} {self.currency}"]
        for d, r in list(zip(closes, res))[-10:]:
            lines.append(f"{parse_time(d['time']):%d.%m %H:%M} — {r:+.2f}")
        self.tg.send("\n".join(lines))

    def start_backtest(self):
        if self.backtest_running:
            return self.tg.send("🧪 Sinov allaqachon ketyapti, biroz kuting.")
        self.backtest_running = True
        self.tg.send(f"🧪 Oxirgi {self.cfg.backtest_days} kunlik narxlarda sinov boshlandi (1–3 daqiqa)...")
        threading.Thread(target=self._backtest_job, daemon=True).start()

    def _backtest_job(self):
        try:
            api = MetaApi(self.cfg.metaapi_token, self.cfg.account_id)
            api.region = self.api.region
            api.set_point(self.point)
            now = datetime.now(UTC)
            n15 = self.cfg.backtest_days * 24 * 4
            m15 = drop_unclosed(api.candles(self.symbol, "15m", n15), "15m", now)
            h1 = drop_unclosed(api.candles(self.symbol, "1h", n15 // 4 + backtest.WIN_H1), "1h", now)
            res = backtest.run(h1, m15, self.p, backtest.Limits(self.cfg.max_trades_per_day, self.max_consec))
            s = backtest.summary(res, risks=sorted({2, 5, 10, self.risk}))
            log.info("sinov: %s", {k: v for k, v in s.items() if k != "by_risk"} | {"by_risk": s["by_risk"]})
            self.tg.send(backtest.format_summary(s))
        except Exception as e:  # noqa: BLE001
            log.error("sinov xatosi: %s\n%s", e, traceback.format_exc())
            self.tg.send(f"⚠️ Sinov bajarilmadi: {esc(e)}")
        finally:
            self.backtest_running = False


# ---------- ishga tushirish ----------
STATUS = {"text": "starting"}


class Health(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = f"goldbot: {STATUS['text']}\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    do_HEAD = do_GET  # noqa: N815

    def log_message(self, *a):
        pass


def telegram_loop(bot: Bot):
    while True:
        for text in bot.tg.updates():
            try:
                bot.handle(text)
            except Exception as e:  # noqa: BLE001
                log.error("buyruq xatosi: %s\n%s", e, traceback.format_exc())
                bot.tg.send(f"⚠️ Xatolik: {esc(e)}")


def main():
    cfg = Config()
    server = ThreadingHTTPServer(("0.0.0.0", cfg.port), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("health server: %s", cfg.port)
    miss = cfg.missing()
    if miss:
        STATUS["text"] = "sozlanmagan: " + ", ".join(miss)
        log.error("Muhit o'zgaruvchilari yetishmaydi: %s", ", ".join(miss))
        while True:
            time.sleep(3600)
    tg = Telegram(cfg.tg_token, cfg.owner_id)
    api = MetaApi(cfg.metaapi_token, cfg.account_id)
    bot = Bot(cfg, api, tg)
    while True:
        try:
            bot.setup()
            break
        except Exception as e:  # noqa: BLE001
            STATUS["text"] = f"ulanish xatosi: {e}"
            log.error("MetaApi ulanmadi: %s", e)
            tg.send(f"⚠️ Broker hisobiga ulanib bo'lmadi: {esc(e)}\n5 daqiqadan keyin qayta urinaman.", keyboard=False)
            time.sleep(300)
    STATUS["text"] = "ishlayapti"
    threading.Thread(target=telegram_loop, args=(bot,), daemon=True).start()
    bot.start_backtest()
    errors = 0
    while True:
        try:
            bot.tick()
            STATUS["text"] = ("pauza" if bot.paused else "ishlayapti") + f" — {bot.status_line}"
            errors = 0
        except Exception as e:  # noqa: BLE001
            errors += 1
            log.error("sikl xatosi: %s\n%s", e, traceback.format_exc())
            if errors in (3, 30):  # vaqtinchalik uzilishlarda egasini bezovta qilmaymiz
                tg.send(f"⚠️ Bot broker bilan bog'lana olmayapti ({errors} marta): {esc(e)}")
        time.sleep(15)


if __name__ == "__main__":
    main()
