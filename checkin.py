import os
import json
import requests
import time
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# 解析用户信息
def fetch_and_extract_info(domain, headers):
    url = f"{domain}/user"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("❌ 用户信息获取失败")
        return "❌ 用户信息获取失败\n"

    soup = BeautifulSoup(response.text, 'html.parser')
    script_tags = soup.find_all('script')

    chatra_script = next((script.string for script in script_tags if script.string and 'window.ChatraIntegration' in script.string), None)
    if not chatra_script:
        print("⚠️ 未识别到用户信息")
        return "⚠️ 未识别到用户信息\n"

    user_info = {
        '到期时间': re.search(r"'Class_Expire': '(.*?)'", chatra_script),
        '剩余流量': re.search(r"'Unused_Traffic': '(.*?)'", chatra_script)
    }

    for key in user_info:
        user_info[key] = user_info[key].group(1) if user_info[key] else "未知"

    # 提取 Clash 和 v2ray 订阅链接
    link_match = next((re.search(r"'https://checkhere.top/link/(.*?)\?sub=1'", str(script)) for script in script_tags if 'index.oneclickImport' in str(script) and 'clash' in str(script)), None)
    
    sub_links = ""
    if link_match:
        clash_link = f"https://checkhere.top/link/{link_match.group(1)}?clash=1"
        v2ray_link = f"https://checkhere.top/link/{link_match.group(1)}?sub=3"
        sub_links = f"\n🔗 <a href=\"{clash_link}\">Clash 订阅</a>\n🔗 <a href=\"{v2ray_link}\">V2ray 订阅</a>\n"

    return f"📅 到期时间: {user_info['到期时间']}\n📊 剩余流量: {user_info['剩余流量']}{sub_links}\n"

# 读取环境变量并生成配置
def generate_config():
    domain = "https://69yun69.com"
    
    # Telegram 配置
    tg_enable = os.getenv('TELEGRAM_ENABLE', 'false').lower() == 'true'
    bot_token = os.getenv('BOT_TOKEN', '')
    chat_id = os.getenv('CHAT_ID', '')
    
    # Ntfy 配置
    ntfy_enable = os.getenv('NTFY_ENABLE', 'false').lower() == 'true'
    ntfy_topic = os.getenv('NTFY_TOPIC', '')
    ntfy_server = os.getenv('NTFY_SERVER', 'https://ntfy.sh')
    ntfy_user = os.getenv('NTFY_USER', '')
    ntfy_pass = os.getenv('NTFY_PASS', '')

    accounts = []
    index = 1
    while True:
        user, password = os.getenv(f'USER{index}'), os.getenv(f'PASS{index}')
        if not user or not password:
            break
        accounts.append({'user': user, 'pass': password})
        index += 1

    return {
        'domain': domain,
        'accounts': accounts,
        'telegram': {
            'enable': tg_enable,
            'bot_token': bot_token,
            'chat_id': chat_id
        },
        'ntfy': {
            'enable': ntfy_enable,
            'topic': ntfy_topic,
            'server': ntfy_server,
            'user': ntfy_user,
            'password': ntfy_pass
        }
    }

# 发送 Telegram 消息
def send_telegram_message(msg, config):
    tg_config = config.get('telegram', {})
    if not tg_config.get('enable'):
        return

    bot_token = tg_config.get('bot_token')
    chat_id = tg_config.get('chat_id')

    if not bot_token or not chat_id:
        return

    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    payload = {
        "chat_id": chat_id,
        "text": f"⏰ 执行时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n{msg}",
        "parse_mode": "HTML",
        "disable_web_page_preview": True  # 防止 Telegram 预览链接
    }
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data=payload)
    except Exception as e:
        print(f"❌ 发送 Telegram 消息失败: {e}")

# 发送 ntfy 消息
def send_ntfy_message(msg, config):
    ntfy_config = config.get('ntfy', {})
    if not ntfy_config.get('enable') or not ntfy_config.get('topic'):
        return

    # 清理 ntfy 不支持的 HTML 标签
    clean_msg = re.sub('<[^<]+?>', '', msg)

    server_url = ntfy_config.get('server')
    topic = ntfy_config.get('topic')
    user = ntfy_config.get('user')
    password = ntfy_config.get('password')

    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    full_msg = f"⏰ 执行时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n{clean_msg}"

    auth = None
    if user and password:
        auth = (user, password)

    try:
        requests.post(
            f"{server_url}/{topic}",
            data=full_msg.encode('utf-8'),
            headers={"Title": "69yun 签到提醒"},
            auth=auth
        )
    except Exception as e:
        print(f"❌ 发送 ntfy 消息失败: {e}")

# 登录并签到
def checkin(account, config):
    domain = config['domain']
    user, password = account['user'], account['pass']
    account_info = f"🔹 地址: {domain}\n🔑 账号: {user}\n"

    # 登录
    login_response = requests.post(
        f"{domain}/auth/login",
        json={'email': user, 'passwd': password, 'remember_me': 'on', 'code': ""},
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Origin': domain,
            'Referer': f"{domain}/auth/login",
        }
    )

    if login_response.status_code != 200 or login_response.json().get("ret") != 1:
        err_msg = f"❌ 登录失败: {login_response.json().get('msg', '未知错误')}"
        full_err_msg = account_info + err_msg
        send_telegram_message(full_err_msg, config)
        send_ntfy_message(full_err_msg, config)
        return err_msg

    cookies = login_response.cookies
    time.sleep(1)

    # 签到
    checkin_response = requests.post(
        f"{domain}/user/checkin",
        headers={
            'Cookie': '; '.join([f"{key}={value}" for key, value in cookies.items()]),
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Origin': domain,
            'Referer': f"{domain}/user/panel"
        }
    )

    checkin_result = checkin_response.json() if checkin_response.status_code == 200 else {}
    result_msg = checkin_result.get('msg', '签到结果未知')
    result_emoji = "✅" if checkin_result.get('ret') == 1 else "⚠️"

    user_info_msg = fetch_and_extract_info(domain, {'Cookie': '; '.join([f"{key}={value}" for key, value in cookies.items()])})
    final_msg = f"{account_info}{user_info_msg}🎉 签到结果: {result_emoji} {result_msg}\n"

    send_telegram_message(final_msg, config)
    send_ntfy_message(final_msg, config)
    return final_msg

# 主函数
if __name__ == "__main__":
    config = generate_config()
    for account in config.get("accounts", []):
        print("📌 正在签到...")
        print(checkin(account, config))