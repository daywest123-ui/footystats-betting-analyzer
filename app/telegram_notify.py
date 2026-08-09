import os
import json
import urllib.request


def telegram_request(method, payload=None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode())


def send_message(text):
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    result = telegram_request("sendMessage", {"chat_id": chat_id, "text": text})
    if not result.get("ok"):
        raise RuntimeError(result)


if __name__ == "__main__":
    send_message("⚽ FootyStats Analyzer bağlantı testi başarılı. Telegram bildirimleri hazır.")
    print("Telegram message sent successfully")
