import json
import time
import requests
from pathlib import Path

WIN_URL   = "https://api.tiantiantiaosheng.com/api2/sports_island/treasure/win"
REWARD_URL = "https://api.tiantiantiaosheng.com/api2/sports_island/treasure/reward"

HEADERS_TEMPLATE = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; 21091116AC Build/V417IR; wv) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Mobile Safari/537.36",
    "Connection": "Keep-Alive",
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json;charset=utf-8",
    "Cookie": "acw_tc=ac11000117548776969314902e71e9f61785c338103c8c564ed1cb92aec6c5",
    "X-Gkid-RequestId": "323289732362920217",
    "x_littlelights_source": "gkid",
    "X-Gkid-uuid": "201E50F3-E817-4BC3-98DE-551ABEA5DC8A",
    "X-Gkid-flavor": "vivoUser",
    "X-Gkid-no": "66015086",
    "X-Gkid-appVersion": "4.0.63",
    "X-Gkid-systemVersion": "12",
    "X-Gkid-deviceName": "21091116AC"
}

PAYLOADS = [
    {"is_win": False, "win_count": 0},
    {"is_win": True,  "win_count": 1},
    {"is_win": True,  "win_count": 2},
    {"is_win": True,  "win_count": 3},
    {"is_win": True,  "win_count": 4},
    {"is_win": True,  "win_count": 5},
    {"is_win": True,  "win_count": 6},
    {"is_win": True,  "win_count": 7},
    {"is_win": False, "win_count": 7}
]

def load_accounts(path: str = "accounts.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def select_user(accounts: dict) -> tuple[str, dict]:
    users = list(accounts.keys())
    print("可用用户：")
    for idx, name in enumerate(users, 1):
        print(f"{idx}. {name}")

    while True:
        try:
            choice = int(input("请输入序号选择用户：").strip())
            if 1 <= choice <= len(users):
                name = users[choice - 1]
                return name, accounts[name]
            print("无效序号，请重新输入！")
        except ValueError:
            print("请输入有效的数字！")

def send_win_requests(bearer: str) -> bool:
    headers = HEADERS_TEMPLATE.copy()
    headers["Authorization"] = bearer

    start_index = 0
    while True:
        for idx in range(start_index, len(PAYLOADS)):
            payload = PAYLOADS[idx]
            try:
                resp = requests.post(WIN_URL, headers=headers, json=payload, timeout=10)
                if resp.status_code != 200:
                    print(f"[{idx+1}/9] 失败，HTTP {resp.status_code}，内容：{resp.text[:200]}")
                    break
                print(f"[{idx+1}/9] OK {payload},{resp.text}")
            except requests.RequestException as e:
                print(f"[{idx+1}/9] 网络异常：{e}")
                break

            if idx < len(PAYLOADS) - 1:
                time.sleep(0.23)
        else:
            return True  # 全部成功

        retry = input("是否重试并从失败处继续？(y/n): ").strip().lower()
        if retry != "y":
            print("已取消，程序结束。")
            return False
        start_index = idx
        print("即将重试...")

def claim_reward(bearer: str) -> None:
    headers = HEADERS_TEMPLATE.copy()
    headers["Authorization"] = bearer
    payload = {"win_count": 7, "is_ad": False}
    try:
        resp = requests.post(REWARD_URL, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            print("奖励领取成功：", resp.text)
        else:
            print("奖励领取失败，HTTP", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        print("奖励领取失败，网络异常：", e)
    print("请手动检查奖励是否到账！")

def main():
    accounts = load_accounts()
    name, info = select_user(accounts)
    print(f"\n已选择用户：{name}")
    for i in range(10):
        print(f"第 {i+1} 次循环")
        if send_win_requests(info["bearer"]):
            claim_reward(info["bearer"])

if __name__ == "__main__":
    main()