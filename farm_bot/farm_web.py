from flask import Flask, render_template, request, jsonify, send_file
import requests
import json
import time
import datetime
import os
from threading import Lock, Thread
import io
from datetime import datetime
import traceback

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# 获取当前脚本所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
headers_path = os.path.join(BASE_DIR, "headers.json")
accounts_path = os.path.join(BASE_DIR, "accounts.json")
crop_path = os.path.join(BASE_DIR, "crop_map.json")

# ---------- 加载配置 ----------
with open(headers_path, encoding="utf-8") as f:
    HEADERS = json.load(f)
with open(accounts_path, encoding="utf-8") as f:
    ACCOUNT_MAP = json.load(f)
try:
    with open(crop_path, encoding="utf-8") as f:
        CROP_MAP = json.load(f)
except FileNotFoundError:
    CROP_MAP = {}

# ---------- 全局变量 ----------
current_user = list(ACCOUNT_MAP.keys())[0] if ACCOUNT_MAP else None
current_auth = ACCOUNT_MAP[current_user]["bearer"] if current_user else None
current_user_id = ACCOUNT_MAP[current_user]["usid"] if current_user else None
farmland_data = []
friend_cache = {}
nick_cache = {}
result_lock = Lock()
results = []
fertilizer_products = []

# ---------- 肥料客户端 ----------
class FertilizerClient:
    def __init__(self):
        self.products = []
        self.auth = current_auth

    def load_product_names(self):
        try:
            with open("fertilizer_list.json", encoding="utf-8") as f:
                self.products = json.load(f)
        except FileNotFoundError:
            self.products = []

    def load_or_refresh(self):
        if not self.auth:
            return False
        try:
            headers = {**HEADERS, "Authorization": self.auth}
            resp = requests.get(
                "（不公开，提示：）ac_farm_fertilizer",
                headers=headers, timeout=10)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                self.products = resp.json()["data"]["product_list"]
                with open("fertilizer_list.json", "w", encoding="utf-8") as f:
                    json.dump(self.products, f, ensure_ascii=False, indent=2)
                return True
        except Exception as e:
            add_result("肥料列表", {"status": "error", "response": str(e)})
        return False

    def get_name(self, item_id):
        for p in self.products:
            if str(p.get("item_id")) == str(item_id):
                return p["name"]
        return str(item_id)

fertilizer_client = FertilizerClient()

# ---------- 工具函数 ----------
def add_result(action, result):
    t = time.strftime("%H:%M:%S")
    status_class = "success" if str(result.get("status", "")).startswith("2") or result.get("status") == "success" else "error"
    result_text = f"[{t}] "
    if status_class == "success":
        result_text += f"✅ {action} 执行成功\n"
    else:
        result_text += f"❌ {action} 执行失败\n"
    result_text += f"状态码: {result.get('status', 'N/A')}\n"
    if isinstance(result.get("response"), dict):
        result_text += f"响应:\n{json.dumps(result['response'], ensure_ascii=False, indent=2)}\n"
    else:
        result_text += f"响应: {result.get('response', 'N/A')}\n"
    result_text += "─" * 50 + "\n"
    with result_lock:
        results.append({"text": result_text, "status": status_class})
        if len(results) > 100:
            results.pop(0)

def api_get(url):
    try:
        headers = {**HEADERS, "Authorization": current_auth}
        resp = requests.get(url, headers=headers, timeout=10)
        return {"status": resp.status_code, "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text}
    except Exception as e:
        return {"status": "error", "response": str(e)}

def api_post(url, payload):
    try:
        headers = {**HEADERS, "Authorization": current_auth}
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return {"status": resp.status_code, "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text}
    except Exception as e:
        return {"status": "error", "response": str(e)}

def nickname_of(uid):
    return nick_cache.get(uid, uid[:8])

# ---------- 后台加载函数 ----------
# ---------- 后台加载函数 ----------
def background_loader():
    while True:
        try:
            fertilizer_client.load_or_refresh()
            if current_auth:
                friends_result = load_friends()
                if friends_result["status"] == "success":
                    for friend in friends_result["response"]:
                        uid = friend["user_id"]
                        nick = friend["nick_name"]
                        if uid not in friend_cache:          # ✅ 新增：跳过已缓存
                            farm_result = load_friend_farm(uid)
                            if farm_result["status"] == "success":
                                friend_cache[uid] = farm_result["response"]
                            time.sleep(0.23)
        except Exception as e:
            add_result("后台加载", {"status": "error", "response": str(e)})
        time.sleep(0.23)

# ---------- 一次性加载好友 ----------
def preload_all_friends_once():
    try:
        friends_result = load_friends()
        if friends_result["status"] == "success":
            for friend in friends_result["response"]:
                uid = friend["user_id"]
                nick = friend["nick_name"]
                farm_result = load_friend_farm(uid)
                if farm_result["status"] == "success":
                    friend_cache[uid] = farm_result["response"]
                time.sleep(0.23)
    except Exception as e:
        add_result("后台加载", {"status": "error", "response": str(e)})
        #traceback.print_exc()

# ---------- 农场操作 ----------
def refresh_farm():
    global farmland_data
    if not current_user_id:
        return {"status": "error", "response": "未选择用户"}
    result = api_get(f"（不公开，提示：）{current_user_id}")
    if result["status"] == 200 and isinstance(result["response"], dict) and result["response"].get("code") == 0:
        farmland_data = result["response"]["data"]["farmland_info"]
        return {"status": "success", "response": result["response"]["data"]}
    return result

def auto_harvest(land_indexes=None):
    if not farmland_data:
        return {"status": "error", "response": "请先刷新农场"}
    now = int(time.time())
    lands = [land for land in farmland_data if land.get("finish_ts", 0) <= now]
    if land_indexes:
        lands = [land for land in lands if land["farmland_index"] in land_indexes]
    count = 0
    for land in lands:
        payload = {
            "crop_id": land["crop_id"],
            "farmland_index": land["farmland_index"],
            "version": land["version"],
            "finish_guide": False
        }
        result = api_post("（不公开，提示：）harvest", payload)
        if result["status"] == 200 and isinstance(result["response"], dict) and result["response"].get("code") == 0:
            count += 1
        add_result(f"收获地块 {land['farmland_index'] + 1}", result)
        time.sleep(0.23)
    return {"status": "success", "response": f"共收获 {count} 块地"}

def auto_watering(land_indexes=None):
    if not farmland_data:
        return {"status": "error", "response": "请先刷新农场"}
    lands = farmland_data
    if land_indexes:
        lands = [land for land in lands if land["farmland_index"] in land_indexes]
    for land in lands:
        if land.get("crop_id") == 0:
            continue
        payload = {
            "farmland_index": land["farmland_index"],
            "crop_id": land["crop_id"],
            "version": land["version"],
            "finish_guide": False
        }
        result = api_post("（不公开，提示：）watering", payload)
        add_result(f"浇水地块 {land['farmland_index'] + 1}", result)
        time.sleep(0.25)
    return {"status": "success", "response": "浇水完毕"}

def auto_fertilize(fertilizer_id, land_indexes=None):
    if not farmland_data:
        return {"status": "error", "response": "请先刷新农场"}
    lands = [land for land in farmland_data if land.get("crop_id") != 0]
    if land_indexes:
        lands = [land for land in lands if land["farmland_index"] in land_indexes]
    count = 0
    for land in lands:
        payload = {
            "farmland_index": land["farmland_index"],
            "crop_id": land["crop_id"],
            "fertilizer_id": fertilizer_id,
            "version": land["version"]
        }
        result = api_post("（不公开，提示：）fertilize", payload)
        if result["status"] == 200 and isinstance(result["response"], dict) and result["response"].get("code") == 0:
            count += 1
        add_result(f"施肥地块 {land['farmland_index'] + 1}", result)
        time.sleep(0.25)
    return {"status": "success", "response": f"共施肥 {count} 块地"}

def clear_farm(land_indexes=None):
    if not farmland_data:
        return {"status": "error", "response": "请先刷新农场"}
    lands = [land for land in farmland_data if land.get("crop_id") != 0]
    if land_indexes:
        lands = [land for land in lands if land["farmland_index"] in land_indexes]
    for land in lands:
        payload = {
            "remove_list": [{
                "farmland_index": land["farmland_index"],
                "crop_id": land["crop_id"],
                "version": land["version"]
            }]
        }
        result = api_post("（不公开，提示：）remove", payload)
        add_result(f"清空地块 {land['farmland_index'] + 1}", result)
        time.sleep(0.3)
    return {"status": "success", "response": "清空操作完成"}

# ---------- 偷菜功能 ----------
def load_friends():
    result = api_get("（不公开，提示：）contains_farm=1")
    if result["status"] == 200 and isinstance(result["response"], dict) and result["response"].get("code") == 0:
        friends = result["response"]["data"]["friend_list"]
        for friend in friends:
            nick_cache[friend["user_id"]] = friend["nick_name"]
        return {"status": "success", "response": friends}
    return result

def load_friend_farm(uid):
    result = api_get(f"（不公开，提示：）host_user_id={uid}")
    if result["status"] == 200 and isinstance(result["response"], dict) and result["response"].get("code") == 0:
        friend_cache[uid] = result["response"]["data"]
        return {"status": "success", "response": result["response"]["data"]}
    return result

def steal_veg(uid, farmland_index, crop_id, version):
    payload = {
        "farmland_index": farmland_index,
        "host_user_id": uid,
        "crop_id": crop_id,
        "version": version
    }
    return api_post("（不公开，提示：）steal_veg", payload)

def auto_steal(friend_uids=None):
    if not friend_uids:
        friends_result = load_friends()
        if friends_result["status"] != "success":
            return friends_result
        friend_uids = [f["user_id"] for f in friends_result["response"]]
    total = 0
    for uid in friend_uids:
        farm_result = load_friend_farm(uid)
        if farm_result["status"] != "success":
            continue
        farm = farm_result["response"]
        lands = farm.get("farmland_info", [])
        now = int(time.time())
        nick = nick_cache.get(uid, uid[:8])
        for land in lands:
            if land.get("crop_id") == 0:
                continue
            if land.get("finish_ts", 0) <= now:
                result = steal_veg(uid, land["farmland_index"], land["crop_id"], land["version"])
                if result["status"] == 200 and isinstance(result["response"], dict):
                    code = result["response"].get("code")
                    msg = result["response"].get("msg", "")
                    if code == 0:
                        total += 1
                        add_result(f"偷 {nick} 地块 {land['farmland_index'] + 1}", {"status": "success", "response": msg})
                    elif "抢菜失败，请稍后再试" in msg:
                        time.sleep(0.5)
                        result = steal_veg(uid, land["farmland_index"], land["crop_id"], land["version"])
                        if result["status"] == 200 and isinstance(result["response"], dict) and result["response"].get("code") == 0:
                            total += 1
                            add_result(f"偷 {nick} 地块 {land['farmland_index'] + 1}", {"status": "success", "response": "重试成功"})
                        else:
                            add_result(f"偷 {nick} 地块 {land['farmland_index'] + 1}", {"status": "error", "response": "重试失败"})
                    elif "该地块没有可拿取的菜了" in msg:
                        add_result(f"跳过 {nick} 地块 {land['farmland_index'] + 1}", {"status": "info", "response": msg})
                    else:
                        add_result(f"偷 {nick} 地块 {land['farmland_index'] + 1}", {"status": "error", "response": msg})
                time.sleep(0.25)
    return {"status": "success", "response": f"共偷菜 {total} 次"}

# ---------- Flask 路由 ----------
@app.route('/')
def index():
    return render_template('index.html', 
                         accounts=list(ACCOUNT_MAP.keys()), 
                         current_user=current_user,
                         crop_map=CROP_MAP)

@app.route('/change_account', methods=['POST'])
def change_account():
    global current_user, current_auth, current_user_id
    account = request.form.get('account')
    if account in ACCOUNT_MAP:
        current_user = account
        current_auth = ACCOUNT_MAP[account]["bearer"]
        current_user_id = ACCOUNT_MAP[account]["usid"]
        fertilizer_client.auth = current_auth
        nick_cache.clear()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "无效的账号"})

@app.route('/add_account', methods=['POST'])
def add_account():
    global current_auth, current_user_id
    auth = request.form.get('auth')
    if not auth:
        return jsonify({"status": "error", "message": "请输入Authorization"})
    try:
        url = "（不公开，提示：）user_info"
        resp = requests.get(url, headers={"Authorization": auth}, timeout=10)
        if resp.status_code != 200 or resp.json().get("code") != 0:
            return jsonify({"status": "error", "message": "Authorization无效或网络异常"})
        user_id = resp.json()["data"]["user_info"]["user_id"]
        nick = resp.json()["data"]["user_info"]["nick_name"]
        key = f"{nick}(临时)"
        ACCOUNT_MAP[key] = {"bearer": auth, "usid": user_id}
        current_auth = auth
        current_user_id = user_id
        return jsonify({
            "status": "success", 
            "account": key, 
            "accounts": list(ACCOUNT_MAP.keys())
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/get_farm_info')
def get_farm_info():
    result = refresh_farm()
    if result["status"] != "success":
        return jsonify(result)
    farm_info = result["response"]
    now = int(time.time())
    lands = []
    for land in farmland_data:
        crop_id = land.get("crop_id")
        if not crop_id:
            crop_name = "空地"
            mature = "空地"
        else:
            crop_name = CROP_MAP.get(str(crop_id), f"未知({crop_id})")
            mature = "可收" if land.get("finish_ts", 0) <= now else "未熟"
        level_map = {0: "普通", 1: "丰收", 2: "大丰收"}
        level = level_map.get(land.get("harvest_state", 0), "未知")
        water_ts = land.get("last_watering_ts")
        water = datetime.fromtimestamp(water_ts).strftime('%m-%d %H:%M') if water_ts else "无"
        wet_ts = land.get("finish_wet_ts")
        wet = datetime.fromtimestamp(wet_ts).strftime('%m-%d %H:%M') if wet_ts else "无"
        finish_ts = land.get("finish_ts")
        finish_str = datetime.fromtimestamp(finish_ts).strftime('%m-%d %H:%M') if finish_ts else "无"
        stolen_users = land.get("taken_away_users") or []
        pray_users = land.get("pray_users") or []
        fert_list = land.get("fertilizer_list") or []
        fert_names = [fertilizer_client.get_name(f) for f in fert_list]
        fert_str = ', '.join(fert_names) if fert_names else "无"
        lands.append({
            "index": land.get("farmland_index", 0) + 1,
            "crop_name": crop_name,
            "level": level,
            "mature": mature,
            "finish_time": finish_str,
            "water_time": water,
            "wet_time": wet,
            "stolen_count": len(stolen_users),
            "pray_count": len(pray_users),
            "fertilizers": fert_str,
            "stolen_users": [nickname_of(uid) for uid in stolen_users],
            "pray_users": [nickname_of(uid) for uid in pray_users]
        })
    return jsonify({
        "status": "success",
        "data": {
            "nick_name": farm_info.get("nick_name", "—"),
            "farm_level": farm_info.get("farm_level", "—"),
            "farm_exp": farm_info.get("farm_exp", "—"),
            "veg_stall_level": farm_info.get("veg_stall_level", "—"),
            "lands": lands
        }
    })

@app.route('/get_friends')
def get_friends():
    keyword = request.args.get('keyword', '').lower()  # ✅ 新增
    result = load_friends()
    if result["status"] != "success":
        return jsonify(result)
    friends = []
    for friend in result["response"]:
        uid = friend["user_id"]
        nick = friend["nick_name"]
        farm = friend_cache.get(uid, {})
        lands = farm.get("farmland_info", [])
        now = int(time.time())
        states = []
        for land in lands:
            if not land.get("crop_id"):
                states.append("空地")
            else:
                states.append("已熟" if land.get("finish_ts", 0) <= now else "未熟")
        state_str = ";".join(states)
        friends.append({
            "user_id": uid,
            "nick_name": friend["nick_name"],
            "farm_level": farm.get("farm_level", "—"),
            "farm_exp": farm.get("farm_exp", "—"),
            "veg_stall_level": farm.get("veg_stall_level", "—"),
            "status": state_str,
            "loaded": uid in friend_cache,
            "search_highlight": keyword and keyword in friend["nick_name"].lower()  # ✅ 新增
        })
    return jsonify({
        "status": "success",
        "friends": friends
    })

@app.route('/get_friend_farm', methods=['POST'])
def get_friend_farm():
    uid = request.form.get('uid')
    if not uid:
        return jsonify({"status": "error", "response": "缺少用户ID"})
    if uid in friend_cache:
        farm = friend_cache[uid]
    else:
        result = load_friend_farm(uid)
        if result["status"] != "success":
            return jsonify(result)
        farm = result["response"]
    now = int(time.time())
    lands = []
    for land in farm.get("farmland_info", []):
        crop_id = land.get("crop_id")
        if not crop_id:
            crop_name = "空地"
            mature = "空地"
        else:
            crop_name = CROP_MAP.get(str(crop_id), f"未知({crop_id})")
            mature = "已熟" if land.get("finish_ts", 0) <= now else "未熟"
        water_ts = land.get("last_watering_ts")
        water = datetime.fromtimestamp(water_ts).strftime('%m-%d %H:%M') if water_ts else "无"
        wet_ts = land.get("finish_wet_ts")
        wet = datetime.fromtimestamp(wet_ts).strftime('%m-%d %H:%M') if wet_ts else "无"
        taken_away_users = land.get("taken_away_users", []) or []
        pray_users = land.get("pray_users", []) or []
        fert_list = land.get("fertilizer_list") or []
        fert_names = [fertilizer_client.get_name(f) for f in fert_list]
        fert_str = ', '.join(fert_names) if fert_names else "无"
        lands.append({
            "index": land["farmland_index"] + 1,
            "crop_name": crop_name,
            "mature": mature,
            "water_time": water,
            "wet_time": wet,
            "stolen_count": len(taken_away_users),
            "pray_status": "成功" if land.get("pray_success") else "失败",
            "fertilizers": fert_str
        })
    return jsonify({
        "status": "success",
        "data": {
            "nick_name": farm.get("nick_name", "好友"),
            "farm_level": farm.get("farm_level", 0),
            "farm_exp": farm.get("farm_exp", 0),
            "veg_stall_level": farm.get("veg_stall_level", 0),
            "lands": lands
        }
    })

@app.route('/harvest', methods=['POST'])
def harvest():
    land_indexes = request.form.getlist('land_indexes[]')
    if land_indexes:
        land_indexes = [int(i) - 1 for i in land_indexes]
    return jsonify(auto_harvest(land_indexes))

@app.route('/water', methods=['POST'])
def water():
    land_indexes = request.form.getlist('land_indexes[]')
    if land_indexes:
        land_indexes = [int(i) - 1 for i in land_indexes]
    return jsonify(auto_watering(land_indexes))

@app.route('/fertilize', methods=['POST'])
def fertilize():
    fertilizer_id = request.form.get('fertilizer_id')
    if not fertilizer_id:
        return jsonify({"status": "error", "response": "请选择肥料"})
    land_indexes = request.form.getlist('land_indexes[]')
    if land_indexes:
        land_indexes = [int(i) - 1 for i in land_indexes]
    return jsonify(auto_fertilize(int(fertilizer_id), land_indexes))

@app.route('/clear', methods=['POST'])
def clear():
    land_indexes = request.form.getlist('land_indexes[]')
    if land_indexes:
        land_indexes = [int(i) - 1 for i in land_indexes]
    return jsonify(clear_farm(land_indexes))

@app.route('/steal', methods=['POST'])
def steal():
    friend_uids = request.form.getlist('friend_uids[]')
    return jsonify(auto_steal(friend_uids))

@app.route('/get_fertilizers')
def get_fertilizers():
    if fertilizer_client.load_or_refresh():
        fertilizers = [{
            "item_id": p["item_id"],
            "name": p["name"],
            "price": p["original_price"] * 10
        } for p in fertilizer_client.products]
        return jsonify({"status": "success", "fertilizers": fertilizers})
    return jsonify({"status": "error", "response": "无法加载肥料列表"})

@app.route('/buy_fertilizer', methods=['POST'])
def buy_fertilizer():
    product_id = request.form.get('product_id')
    if not product_id:
        return jsonify({"status": "error", "response": "请选择肥料"})
    product = next((p for p in fertilizer_client.products if str(p["item_id"]) == str(product_id)), None)
    if not product:
        return jsonify({"status": "error", "response": "无效的肥料ID"})
    payload = {
        "product_id": product["product_id"],
        "product_price": product["original_price"],
        "activity_shop_id": "inside_unity",
        "number": 1
    }
    result = api_post(
        "（不公开，提示：）buy_product_v2",
        payload)
    add_result(f"购买肥料 {product['name']}", result)
    return jsonify(result)

@app.route('/search_friends', methods=['POST'])
def search_friends():
    keyword = request.form.get('keyword', '').lower()
    if not keyword:
        return jsonify({"status": "error", "response": "请输入搜索关键词"})
    result = load_friends()
    if result["status"] != "success":
        return result
    matched = [f for f in result["response"] if keyword in f["nick_name"].lower()]
    return jsonify({
        "status": "success",
        "friends": [{
            "user_id": f["user_id"],
            "nick_name": f["nick_name"],
            "loaded": f["user_id"] in friend_cache
        } for f in matched]
    })

@app.route('/get_results')
def get_results():
    with result_lock:
        return jsonify({"results": results})

@app.route('/clear_results', methods=['POST'])
def clear_results():
    with result_lock:
        results.clear()
    return jsonify({"status": "success"})

# ---------- HTML 模板 ----------
INDEX_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>农场自动化工具</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body { background: #f8f9fa; padding: 20px; }
        .card { margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,.1); }
        .farm-land { border: 1px solid #dee2e6; border-radius: 5px; padding: 10px; margin-bottom: 10px; }
        .land-mature { color: #28a745; font-weight: bold; }
        .land-not-mature { color: #dc3545; }
        .land-empty { color: #6c757d; }
        

        #logFloat {
            position: fixed;
            top: 0;
            right: 0;
            width: 500px;
            height: 350px;
            background: #343a40;
            color: #e9ecef;
            font-family: Consolas, monospace;
            font-size: 13px;
            border-radius: 0 0 0 8px;
            padding: 10px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
        }
        #logContent {
            flex: 1;
            overflow-y: auto;
            white-space: pre-wrap;
        }
        .toast-container { z-index: 99999; }

        .container { max-width: 98vw !important; padding-left: 1rem; padding-right: 1rem; }
        .table { width: 100% !important; }

        /* 防止 Bootstrap 的 table-hover 或 table-striped 覆盖 */
        .table tbody tr.search-highlight,
        .table tbody tr.search-selected {
            background-color: #ffeb3b !important;
        }

        .search-highlight td {
          background-color: #FF8000 !important;
          color: #000000 !important;
          font-weight: bold !important;
        }
        .search-selected {
            background-color: #FF8000 !important; /* 深红色 */
            color: #000000 !important;
            font-weight: bold !important;
        }

        .search-highlight td,
        .search-selected td {
          background-color: #FF8000 !important;
          color: #000000 !important;
          font-weight: bold !important;
        }
    </style>
</head>
<body>
<div class="container">
    <h1 class="text-center mb-4">农场自动化工具</h1>

    <div class="card">
        <div class="card-body">
            <div class="d-flex align-items-center mb-3 flex-wrap gap-2">
                <select id="accountSelect" class="form-select" style="width:200px">
                    {% for a in accounts %}
                    <option value="{{ a }}" {% if a==current_user %}selected{% endif %}>{{ a }}</option>
                    {% endfor %}
                </select>

                <button class="btn btn-primary" id="refreshBtn"><i class="bi bi-arrow-clockwise"></i> 刷新</button>
                <button class="btn btn-success" id="harvestBtn"><i class="bi bi-basket"></i> 一键收获</button>
                <button class="btn btn-info"    id="waterBtn"><i class="bi bi-droplet"></i> 自动浇水</button>
                <button class="btn btn-warning" id="fertilizeBtn"><i class="bi bi-flower1"></i> 自动施肥</button>
                <button class="btn btn-warning" id="buyFertilizerBtn"><i class="bi bi-cart-plus"></i> 购买肥料</button>
                <button class="btn btn-danger"  id="clearBtn"><i class="bi bi-trash"></i> 清空农场</button>
                <button class="btn btn-secondary" data-bs-toggle="modal" data-bs-target="#addAccountModal"><i class="bi bi-plus-lg"></i> 添加账号</button>
            </div>

            <div id="farmInfo" class="mb-3">
                <div class="d-flex justify-content-center"><div class="spinner-border text-primary"></div></div>
            </div>

            <div class="table-responsive">
                <table class="table table-bordered table-hover">
                    <thead>
                        <tr>
                            <th width="60px"><input type="checkbox" id="selectAllLands"></th>
                            <th>地块</th><th>作物</th><th>等级</th><th>状态</th><th>成熟时间</th>
                            <th>最后浇水</th><th>水分维持</th><th>被偷人数</th><th>祈福人数</th><th>肥料</th>
                        </tr>
                    </thead>
                    <tbody id="farmLandsList"></tbody>
                </table>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card-body">
            <h5 class="card-title">好友菜园</h5>
            <div class="mb-3">
                <div class="input-group">
                    <input type="text" class="form-control" id="searchFriendInput" placeholder="搜索好友昵称">
                    <button class="btn btn-primary" id="searchFriendBtn"><i class="bi bi-search"></i> 搜索</button>
                    <button class="btn btn-secondary" id="clearSearchBtn"><i class="bi bi-x-circle"></i> 清除</button>
                </div>
            </div>
            <div class="mb-3">
                <button class="btn btn-success btn-sm me-2" id="stealBtn"><i class="bi bi-hand-thief"></i> 开始偷菜</button>
                <button class="btn btn-secondary btn-sm me-2" id="selectAllBtn"><i class="bi bi-check-all"></i> 全选/取消</button>
                <button class="btn btn-primary btn-sm"   id="refreshFriendsBtn"><i class="bi bi-arrow-clockwise"></i> 刷新好友</button>
            </div>
            <div class="table-responsive">
                <table class="table table-bordered table-hover">
                    <thead>
                        <tr>
                            <th width="60px"><input type="checkbox" id="selectAllFriends"></th>
                            <th>昵称</th><th>农场等级</th><th>经验值</th><th>蔬菜摊等级</th><th>状态</th><th>操作</th>
                        </tr>
                    </thead>
                    <tbody id="friendsList"></tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<!-- =====  模态框  ===== -->
<!-- 添加账号 -->
<div class="modal fade" id="addAccountModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header"><h5 class="modal-title">添加临时账号</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
            <div class="modal-body">
                <label class="form-label">Authorization</label>
                <input type="text" class="form-control" id="authInput" placeholder="请输入Authorization">
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                <button class="btn btn-primary" id="confirmAddBtn">确认添加</button>
            </div>
        </div>
    </div>
</div>

<!-- 选择肥料 -->
<div class="modal fade" id="fertilizerModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header"><h5 class="modal-title">选择肥料</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
            <div class="modal-body" id="fertilizerList"></div>
            <div class="modal-footer">
                <button class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                <button class="btn btn-primary" id="confirmFertilizeBtn">确认施肥</button>
            </div>
        </div>
    </div>
</div>

<!-- 购买肥料 -->
<div class="modal fade" id="buyFertilizerModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header"><h5 class="modal-title">购买肥料</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
            <div class="modal-body" id="buyFertilizerList"></div>
            <div class="modal-footer">
                <button class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                <button class="btn btn-primary" id="confirmBuyFertilizerBtn">确认购买</button>
            </div>
        </div>
    </div>
</div>

<!-- =====  日志悬浮窗  ===== -->
<div id="logFloat" style="display:none;">
    <div class="d-flex justify-content-between align-items-center mb-1">
        <strong>执行日志</strong>
        <div>
            <button class="btn btn-sm btn-outline-light" id="scrollToLatestBtn" title="划到最新">⬇</button>
            <button class="btn btn-sm btn-outline-danger"  id="toggleLogBtn"    title="关闭">✕</button>
        </div>
    </div>
    <div id="logContent"></div>
</div>
<button id="openLogBtn" class="btn btn-dark" style="position: fixed; top: 0; right: 0; z-index: 10000;">📄</button>

<!-- =====  JS  ===== -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jquery@3.6.0/dist/jquery.min.js"></script>
<script>
/* =========  通用工具  ========= */
function showToast(msg, type = 'success') {
    const cls = type === 'success' ? 'bg-success' : 'bg-danger';
    const html = `
        <div class="toast align-items-center text-white ${cls} border-0" role="alert" data-bs-delay="3000">
            <div class="d-flex">
                <div class="toast-body">${msg}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>`;
    $('body').append(`<div class="toast-container position-fixed top-0 end-0 p-3">${html}</div>`);
    $('.toast').last().toast('show');
}

function loadFarmInfo() {
    $.get('/get_farm_info')
        .done(data => {
            if (data.status === 'success') {
                updateFarmInfo(data.data);
                updateFarmLands(data.data.lands);
                showToast('农场信息已刷新');
            } else {
                showToast('农场刷新失败：' + (data.response || '未知错误'), 'error');
            }
        })
        .fail(() => showToast('网络错误或服务器未响应', 'error'));
}

function updateFarmInfo(data) {
    $('#farmInfo').html(`
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h4>${data.nick_name}</h4>
            <div>
                <span class="badge bg-primary me-2">农场等级: ${data.farm_level}</span>
                <span class="badge bg-success me-2">经验值: ${data.farm_exp}</span>
                <span class="badge bg-warning">蔬菜摊等级: ${data.veg_stall_level}</span>
            </div>
        </div>
    `);
}

function updateFarmLands(lands) {
    let html = '';
    lands.forEach(l => {
        const cls = l.mature === '可收' ? 'text-success' : l.mature === '未熟' ? 'text-warning' : 'text-muted';
        html += `
        <tr>
            <td><input class="form-check-input land-checkbox" type="checkbox" value="${l.index}" ${l.mature === '空地' ? 'disabled' : ''}></td>
            <td>${l.index}</td><td>${l.crop_name}</td><td>${l.level}</td>
            <td class="${cls}">${l.mature}</td>
            <td>${l.finish_time}</td><td>${l.water_time}</td><td>${l.wet_time}</td>
            <td>${l.stolen_count}${l.stolen_count ? `<i class="bi bi-info-circle" title="${l.stolen_users.join(', ')}"></i>` : ''}</td>
            <td>${l.pray_count}${l.pray_count ? `<i class="bi bi-info-circle" title="${l.pray_users.join(', ')}"></i>` : ''}</td>
            <td>${l.fertilizers}</td>
        </tr>`;
    });
    $('#farmLandsList').html(html);
    $('#selectAllLands').off().on('change', function () {
        $('.land-checkbox:not(:disabled)').prop('checked', this.checked);
    });
    $('[title]').tooltip({ boundary: 'window' });
}

function buildFriendRow(f) {
    const kw = $('#searchFriendInput').val().trim().toLowerCase();
    const isMatch = kw && f.nick_name.toLowerCase().includes(kw);
    const isChecked = $('.friend-checkbox[value="' + f.user_id + '"]').prop('checked');
    let rowClass = '';
    if (isMatch && isChecked) rowClass = 'search-selected';
    else if (isMatch) rowClass = 'search-highlight';

    const states = (f.status || '').split(';').map((s, i) => {
        const cls = s === '已熟' ? 'text-success' : s === '未熟' ? 'text-warning' : 'text-muted';
        return `<span class="${cls}">${i + 1}:${s}</span>`;
    }).join(' ') || '<span class="text-muted">未加载</span>';

    return `
    <tr class="friend-row ${rowClass} ${f.loaded ? '' : 'table-secondary'}" data-uid="${f.user_id}">
        <td><input class="form-check-input friend-checkbox" type="checkbox" value="${f.user_id}"></td>
        <td>${f.nick_name}</td>
        <td>${f.farm_level}</td>
        <td>${f.farm_exp}</td>
        <td>${f.veg_stall_level}</td>
        <td>${states}</td>
        <td>
            <button class="btn btn-sm btn-outline-info view-friend-btn" data-uid="${f.user_id}" data-nick="${f.nick_name}">
                <i class="bi bi-eye"></i> 查看
            </button>
        </td>
    </tr>`;
}

function updateFriendsList(friends) {
    let html = '';
    friends.forEach(f => {
        const isChecked = $('.friend-checkbox[value="' + f.user_id + '"]').prop('checked');
        let rowClass = '';
        if (f.search_highlight && isChecked) {
            rowClass = 'search-selected';
        } else if (f.search_highlight) {
            rowClass = 'search-highlight';
        }

        const states = (f.status || '').split(';').map((s, i) => {
            const cls = s === '已熟' ? 'text-success' : s === '未熟' ? 'text-warning' : 'text-muted';
            return `<span class="${cls}">${i + 1}:${s}</span>`;
        }).join(' ') || '<span class="text-muted">未加载</span>';

        html += `
        <tr class="friend-row ${rowClass}" data-uid="${f.user_id}">
            <td><input class="form-check-input friend-checkbox" type="checkbox" value="${f.user_id}"></td>
            <td>${f.nick_name}</td>
            <td>${f.farm_level ?? '—'}</td>
            <td>${f.farm_exp ?? '—'}</td>
            <td>${f.veg_stall_level ?? '—'}</td>
            <td>${states}</td>
            <td>
                <button class="btn btn-sm btn-outline-info view-friend-btn" data-uid="${f.user_id}" data-nick="${f.nick_name}">
                    <i class="bi bi-eye"></i> 查看
                </button>
            </td>
        </tr>`;
    });
    $('#friendsList').html(html);
}

function loadFriends() {
    const kw = $('#searchFriendInput').val().trim().toLowerCase();
    $.get('/get_friends', { keyword: kw }, data => {
        if (data.status === 'success') updateFriendsList(data.friends);
    });
}

/* =========  页面初始化  ========= */
$(function () {
    loadFarmInfo();
    loadFriends();

    $('#accountSelect').change(() => {
        $.post('/change_account', { account: $('#accountSelect').val() }, () => {
            loadFarmInfo();
            loadFriends();
        });
    });

    $('#refreshBtn').click(() => {
        loadFarmInfo();
    });

    $('#refreshFriendsBtn').click(() => loadFriends());

    $('#harvestBtn').click(() => {
        const lands = $('.land-checkbox:checked').map((_, c) => parseInt(c.value) - 1).get();
        $.post('/harvest', { land_indexes: lands }, r => {
            showToast(r.response);
            loadFarmInfo();
        });
    });

    $('#waterBtn').click(() => {
        const lands = $('.land-checkbox:checked').map((_, c) => parseInt(c.value) - 1).get();
        $.post('/water', { land_indexes: lands }, r => {
            showToast(r.response);
            loadFarmInfo();
        });
    });

    $('#fertilizeBtn').click(() => {
        $.get('/get_fertilizers', d => {
            if (d.status !== 'success') return showToast('无法加载肥料', 'error');
            let html = '<div class="list-group">';
            d.fertilizers.forEach((f, i) => {
                html += `<label class="list-group-item">
                            <input type="radio" name="fertilizer" value="${f.item_id}" ${!i ? 'checked' : ''}>
                            ${f.name} (${f.price}跳跳点数)
                         </label>`;
            });
            html += '</div>';
            $('#fertilizerList').html(html);
            new bootstrap.Modal(document.getElementById('fertilizerModal')).show();
        });
    });

    $('#confirmFertilizeBtn').click(() => {
        const id = $('input[name="fertilizer"]:checked').val();
        const lands = $('.land-checkbox:checked').map((_, c) => parseInt(c.value) - 1).get();
        $.post('/fertilize', { fertilizer_id: id, land_indexes: lands }, r => {
            showToast(r.response);
            loadFarmInfo();
            $('#fertilizerModal').modal('hide');
        });
    });

    $('#clearBtn').click(() => {
        if (!confirm('确定要清空选中的地块吗？此操作不可撤销！')) return;
        const lands = $('.land-checkbox:checked').map((_, c) => parseInt(c.value) - 1).get();
        $.post('/clear', { land_indexes: lands }, r => {
            showToast(r.response);
            loadFarmInfo();
        });
    });

    $('#buyFertilizerBtn').click(() => {
        $.get('/get_fertilizers', d => {
            if (d.status !== 'success') return showToast('无法加载肥料', 'error');
            let html = '<div class="list-group">';
            d.fertilizers.forEach((f, i) => {
                html += `<label class="list-group-item">
                            <input type="radio" name="buy_fertilizer" value="${f.item_id}" ${!i ? 'checked' : ''}>
                            ${f.name} (${f.price}跳跳点数)
                         </label>`;
            });
            html += '</div>';
            $('#buyFertilizerList').html(html);
            new bootstrap.Modal(document.getElementById('buyFertilizerModal')).show();
        });
    });

    $('#confirmBuyFertilizerBtn').click(() => {
        const id = $('input[name="buy_fertilizer"]:checked').val();
        $.post('/buy_fertilizer', { product_id: id }, r => {
            showToast(r.response);
            $('#buyFertilizerModal').modal('hide');
        });
    });

    $('#stealBtn').click(() => {
        const friends = $('.friend-checkbox:checked').map((_, c) => c.value).get();
        $.post('/steal', { friend_uids: friends }, r => {
            showToast(r.response);
            loadFarmInfo();
            friends.forEach(uid => {
                $.post('/get_friend_farm', { uid }, res => {
                    if (res.status === 'success') {
                        $(`#friendsList tr[data-uid="${uid}"]`).replaceWith(buildFriendRow(res.data));
                    }
                });
            });
        });
    });

    $('#selectAllBtn').click(() => {
        const all = $('.friend-checkbox').length === $('.friend-checkbox:checked').length;
        $('.friend-checkbox').prop('checked', !all);
    });

    $('#selectAllFriends').on('change', function () {
        $('.friend-checkbox').prop('checked', this.checked);
    });

    $('#searchFriendBtn').click(loadFriends);
    $('#clearSearchBtn').click(() => {
        $('#searchFriendInput').val('');
        loadFriends();
    });
    $('#searchFriendInput').keypress(e => e.which === 13 && loadFriends());

    $('#confirmAddBtn').click(() => {
        const auth = $('#authInput').val().trim();
        if (!auth) return showToast('请输入 Authorization', 'error');
        $.post('/add_account', { auth }, r => {
            if (r.status === 'success') {
                $('#accountSelect').empty();
                r.accounts.forEach(a => $('#accountSelect').append(new Option(a, a)));
                $('#accountSelect').val(r.account).trigger('change');
                $('#addAccountModal').modal('hide');
                $('#authInput').val('');
                showToast('账号添加成功');
            } else {
                showToast(r.message, 'error');
            }
        });
    });

    $(document).on('click', '.view-friend-btn', function () {
        const uid = $(this).data('uid');
        const nick = $(this).data('nick');
        $.post('/get_friend_farm', { uid }, res => {
            if (res.status === 'success') {
                const html = `
                <div class="modal fade" id="friendFarmModal" tabindex="-1">
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content">
                            <div class="modal-header"><h5 class="modal-title">${nick} 的农场</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
                            <div class="modal-body">
                                <div class="mb-3">
                                    <span class="badge bg-primary me-2">农场等级: ${res.data.farm_level}</span>
                                    <span class="badge bg-success me-2">经验值: ${res.data.farm_exp}</span>
                                    <span class="badge bg-warning">蔬菜摊等级: ${res.data.veg_stall_level}</span>
                                </div>
                                <div class="table-responsive">
                                    <table class="table table-bordered table-hover">
                                        <thead><tr><th>地块</th><th>作物</th><th>状态</th><th>最后浇水</th><th>水分维持</th><th>被偷次数</th><th>祈福状态</th><th>肥料</th></tr></thead>
                                        <tbody>
                                        ${res.data.lands.map(l => `
                                            <tr>
                                                <td>${l.index}</td><td>${l.crop_name}</td>
                                                <td class="${l.mature==='已熟'?'text-success':'text-warning'}">${l.mature}</td>
                                                <td>${l.water_time}</td><td>${l.wet_time}</td>
                                                <td>${l.stolen_count}</td><td>${l.pray_status}</td><td>${l.fertilizers}</td>
                                            </tr>`).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`;
                $('body').append(html);
                new bootstrap.Modal(document.getElementById('friendFarmModal')).show();
                $('#friendFarmModal').on('hidden.bs.modal', () => $('#friendFarmModal').remove());
            }
        });
    });

    /* 日志窗口控制 */
    $('#openLogBtn').click(() => { $('#logFloat').show(); $('#openLogBtn').hide(); });
    $('#toggleLogBtn').click(() => { $('#logFloat').hide(); $('#openLogBtn').show(); });
    $('#scrollToLatestBtn').click(() => {
        const $c = $('#logContent');
        $c.scrollTop($c[0].scrollHeight);
    });

    /* 每 1 秒拉日志（不清空） */
    setInterval(() => {
        $.get('/get_results', data => {
            data.results.forEach(r => {
                const $line = $('<div>').addClass(r.status === 'error' ? 'text-danger' : 'text-success').text(r.text);
                $('#logContent').append($line);
            });
        });
    }, 1000);

    /* 手动清空日志 */
    $('#clearResultsBtn').click(() => {
        $('#logContent').empty();
        $.post('/clear_results');
    });
});
</script>
</body>
</html>
'''
# ---------- 启动 ----------
if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    with open(os.path.join('templates', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(INDEX_HTML)
    fertilizer_client.load_product_names()
    Thread(target=preload_all_friends_once, daemon=True).start()

    app.run(host='0.0.0.0', port=5001, debug=True)
