import subprocess
import re
import time
import logging
from datetime import datetime
import requests
import os
import sys

TOKEN = "YOUR_BOT_TOKEN_HERE"
CHAT_ID = "YOUR_CHAT_ID_HERE"
CHECK_INTERVAL = 5
DEAUTH_THRESHOLD = 5
MONITOR_INTERFACE = "wlan0"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

last_alert_time = {}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logging.info("Алерт отправлен в Telegram")
        else:
            logging.error(f"Ошибка отправки: {response.text}")
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение: {e}")

def check_openwrt_logs():
    try:
        result = subprocess.run(
            ['logread', '-t', '-l', '50'],
            capture_output=True,
            text=True,
            timeout=10
        )
        logs = result.stdout
        
        patterns = [
            r'deauth',
            r'disassoc',
            r'SA Query timeout',
            r'station left',
            r'authentication failed',
            r'wlan.*: STA.*disconnected',
            r'Deauthentication'
        ]
        
        detected = []
        for pattern in patterns:
            matches = re.findall(pattern, logs, re.IGNORECASE)
            detected.extend(matches)
        
        return len(detected)
    except Exception as e:
        logging.error(f"Ошибка при проверке логов: {e}")
        return 0

def check_dmesg():
    try:
        result = subprocess.run(
            ['dmesg', '|', 'tail', '-50'],
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        logs = result.stdout
        
        patterns = [r'deauth', r'disassoc', r'tx failed']
        
        detected = []
        for pattern in patterns:
            matches = re.findall(pattern, logs, re.IGNORECASE)
            detected.extend(matches)
        
        return len(detected)
    except Exception as e:
        return 0

def check_wireless_interfaces():
    try:
        result = subprocess.run(
            ['iw', 'dev', MONITOR_INTERFACE, 'get', 'power_save'],
            capture_output=True,
            text=True,
            timeout=3
        )
        return result.returncode == 0
    except:
        return False

def get_wifi_clients():
    try:
        result = subprocess.run(
            ['iw', 'dev', MONITOR_INTERFACE, 'station', 'dump'],
            capture_output=True,
            text=True,
            timeout=5
        )
        station_count = result.stdout.count('Station')
        return station_count
    except:
        return 0

def detect_attack():
    log_count = check_openwrt_logs()
    dmesg_count = check_dmesg()
    total = log_count + dmesg_count
    return total

def main():
    logging.info("Wi-Fi Guard запущен")
    
    interface_ok = check_wireless_interfaces()
    if not interface_ok:
        logging.warning(f"Интерфейс {MONITOR_INTERFACE} недоступен")
    
    clients = get_wifi_clients()
    send_telegram_message(f"🟢 Wi-Fi Guard активирован\nИнтерфейс: {MONITOR_INTERFACE}\nКлиентов в сети: {clients}\nПорог срабатывания: {DEAUTH_THRESHOLD} пакетов")
    
    attack_count = 0
    
    while True:
        try:
            deauth_count = detect_attack()
            
            if deauth_count >= DEAUTH_THRESHOLD:
                attack_count += 1
                now = datetime.now()
                key = 'deauth_alert'
                
                if key not in last_alert_time or (now - last_alert_time[key]).seconds > 60:
                    clients_now = get_wifi_clients()
                    message = f"""🚨 ВНИМАНИЕ! Обнаружена деаут-атака!

📊 Зафиксировано подозрительных событий: {deauth_count}
🔁 Атак за сессию: {attack_count}
📱 Подключенных клиентов: {clients_now}
⏰ Время: {now.strftime('%H:%M:%S')}

Рекомендации:
1. Проверьте подключенные устройства
2. Смените пароль Wi-Fi
3. Обновите прошивку роутера
4. Отключите WPS"""
                    
                    send_telegram_message(message)
                    last_alert_time[key] = now
                    
                    if attack_count >= 3:
                        critical_message = f"🔴 КРИТИЧЕСКИ ВАЖНО! Зафиксировано {attack_count} атаки на вашу сеть! Рекомендуется немедленно отключить Wi-Fi и обратиться к специалисту."
                        send_telegram_message(critical_message)
            else:
                if attack_count > 0:
                    logging.info(f"Атака завершена. Всего было {attack_count} атак")
                    attack_count = 0
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logging.info("Wi-Fi Guard остановлен пользователем")
            send_telegram_message("🔴 Wi-Fi Guard остановлен")
            break
        except Exception as e:
            logging.error(f"Ошибка в основном цикле: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
