"""Juda oddiy Telegram Bot API mijozi (faqat egasi bilan gaplashadi)."""
import logging
import time

import requests

log = logging.getLogger("telegram")

KEYBOARD = {
    "keyboard": [
        [{"text": "📊 Holat"}, {"text": "📜 Tarix"}],
        [{"text": "▶️ Boshlash"}, {"text": "⏸ To'xtatish"}],
        [{"text": "⚙️ Risk"}, {"text": "🧪 Sinov"}],
        [{"text": "❌ Hammasini yopish"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


class Telegram:
    def __init__(self, token, owner_id):
        self.base = f"https://api.telegram.org/bot{token}"
        self.owner_id = int(owner_id)
        self.offset = None

    def send(self, text, keyboard=True):
        body = {"chat_id": self.owner_id, "text": text[:4000], "parse_mode": "HTML",
                "disable_web_page_preview": True}
        if keyboard:
            body["reply_markup"] = KEYBOARD
        try:
            r = requests.post(f"{self.base}/sendMessage", json=body, timeout=30)
            if r.status_code == 400:  # HTML belgilash buzilgan bo'lsa — oddiy matn sifatida qayta yuboramiz
                body.pop("parse_mode", None)
                r = requests.post(f"{self.base}/sendMessage", json=body, timeout=30)
            if r.status_code != 200:
                log.warning("Telegram xabar yuborilmadi: HTTP %s %s", r.status_code, r.text[:200])
        except requests.RequestException as e:
            log.warning("Telegram xabar yuborilmadi: %s", e)

    def updates(self, timeout=25):
        """Faqat egasidan kelgan matnli xabarlar ro'yxati (xatoda 5 soniya kutadi)."""
        params = {"timeout": timeout, "allowed_updates": '["message"]'}
        if self.offset is not None:
            params["offset"] = self.offset
        try:
            r = requests.get(f"{self.base}/getUpdates", params=params, timeout=timeout + 15)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("Telegram getUpdates xatosi: %s", e)
            time.sleep(5)
            return []
        if not data.get("ok"):
            log.warning("Telegram getUpdates: %s", data.get("description"))
            time.sleep(5)
            return []
        out = []
        for u in data.get("result", []):
            self.offset = u["update_id"] + 1
            m = u.get("message") or {}
            if (m.get("from") or {}).get("id") != self.owner_id:
                continue  # begonalar buyrug'ini e'tiborsiz qoldiramiz
            if m.get("text"):
                out.append(m["text"].strip())
        return out
