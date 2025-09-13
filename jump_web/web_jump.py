from flask import Flask, render_template, request, jsonify, send_file
import requests
import json
import time
import datetime
import os
from threading import Lock
import io

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# ---------- 统一配置 ----------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; 21091116AC Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Mobile Safari/537.36",
    "Connection": "close",
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "Cookie": "",
    "Proxy-Connection": "close",
    "X-Gkid-appType": "iOS",
    "X-Gkid-RequestId": "72F7ED05-E9BB-4A71-A64A-34280F8FCF0D",
    "X-Gkid-deviceIP": "192.168.1.23",
    "X-Gkid-deviceReal": "1",
    "X-Gkid-appVersion": "4.0.66",
    "X-Gkid-appName": "",
    "X-Gkid-idfa": "",
    "X-Gkid-systemVersion": "16.7.10",
    "X-Littlelights-Source": "gkid",
    "X-Gkid-uuid": "BCDD6E7B-6CF3-4A7D-A84C-A120AB4F8900",
    "X-Gkid-deviceName": "iPad 5 (WiFi)",
    "X-Gkid-Flavor": "App Store"
}

# ---------- 账号映射 ----------
ACCOUNT_MAP = {
    "名字": {
        "bearer": "Bearer 。。。。。。",
        "usid": "1e。。。。。。"
    }
}

current_date = datetime.datetime.now().strftime('%Y-%m')
BODIES_FILE = os.path.join(os.path.dirname(__file__), 'bodies.json')
result_lock = Lock()
results = []
current_user = "菲新"
bearer = ACCOUNT_MAP[current_user]["bearer"]
usid = ACCOUNT_MAP[current_user]["usid"]
user_info = None
exp_info = None
stat_info = None

# ---------- 工具 ----------
class RecordIdManager:
    FILE = "record_id.txt"
    def __init__(self):
        if os.path.exists(self.FILE):
            with open(self.FILE) as f:
                self.counter = int(f.read())
        else:
            self.counter = 0
            self.save()
    def next(self) -> str:
        prefix = f"{self.counter:08x}"
        self.counter += 1
        self.save()
        ts = str(int(time.time() * 1000))
        return f"{prefix}-{ts}-0066015086-V2"
    def save(self):
        with open(self.FILE, "w") as f:
            f.write(str(self.counter))

record_mgr = RecordIdManager()

def update_time_and_record(obj, mgr):
    now = int(time.time() * 1000)
    def _update(o):
        if isinstance(o, dict):
            if "take_time" in o:
                o["end_time"] = now
                o["begin_time"] = now - o["take_time"]
            if "record_id" in o:
                o["record_id"] = mgr.next()
            for v in o.values():
                _update(v)
        elif isinstance(o, list):
            for i in o:
                _update(i)
    _update(obj)

def _replace_id(obj):
    def _do(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if k == "user_id" and v == "__USER_ID__":
                    o[k] = usid
                elif isinstance(v, (dict, list)):
                    _do(v)
        elif isinstance(o, list):
            for i in o:
                _do(i)
    _do(obj)

def _load_json_body(key):
    with open(BODIES_FILE, 'r', encoding='utf-8') as f:
        body = json.load(f)[key]
    _replace_id(body)
    return body

def make_request(url: str, body: dict):
    try:
        update_time_and_record(body, record_mgr)
        headers = {**HEADERS, "Authorization": bearer}
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        return {
            "status": resp.status_code,
            "response": resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
        }
    except Exception as e:
        return {"status": "error", "response": str(e)}

# ---------- 用户信息 ----------
def fetch_user_info():
    global user_info, bearer, usid
    try:
        # 调试输出 - 显示当前使用的认证信息
        print("\n" + "="*50)
        print(f"[DEBUG] 开始获取用户信息")
        print(f"[DEBUG] 当前用户: {current_user}")
        print(f"[DEBUG] 使用的 bearer token: {bearer[:30]}...{bearer[-30:]}")
        print(f"[DEBUG] 用户ID (usid): {usid}")

        url = "（不公开，提示：）user_info"
        headers = {"Authorization": bearer}
        
        # 调试输出 - 显示请求详情
        print(f"[DEBUG] 请求URL: {url}")
        print(f"[DEBUG] 请求头: {headers}")

        # 发送请求
        resp = requests.get(url, headers=headers, timeout=10)
        
        # 调试输出 - 显示响应详情
        print(f"[DEBUG] 响应状态码: {resp.status_code}")
        print(f"[DEBUG] 响应头: {dict(resp.headers)}")
        print(f"[DEBUG] 原始响应内容: {resp.text[:200]}...")  # 只打印前200字符避免太长

        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"[DEBUG] 解析后的JSON数据: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}...")
                
                if data.get("code") == 0:
                    print("[DEBUG] 获取用户信息成功")
                    user_info = data["data"]
                    print(f"[DEBUG] 用户信息: {json.dumps(user_info, indent=2, ensure_ascii=False)[:500]}...")
                    
                    # 获取额外信息
                    print("[DEBUG] 开始获取经验信息...")
                    fetch_exp_info()
                    print("[DEBUG] 开始获取统计信息...")
                    fetch_statistics()
                else:
                    print(f"[DEBUG] API返回错误代码: {data.get('code')}, 消息: {data.get('message')}")
                    user_info = None
            except json.JSONDecodeError as je:
                print(f"[DEBUG] JSON解析错误: {str(je)}")
                user_info = None
        else:
            print(f"[DEBUG] HTTP请求失败，状态码: {resp.status_code}")
            user_info = None

    except requests.exceptions.Timeout:
        print("[DEBUG] 请求超时")
        user_info = None
    except requests.exceptions.ConnectionError:
        print("[DEBUG] 连接错误")
        user_info = None
    except Exception as e:
        print(f"[DEBUG] 获取用户信息时发生异常: {str(e)}")
        user_info = None
    
    print(f"[DEBUG] 最终 user_info: {'已设置' if user_info else 'None'}")
    print("="*50 + "\n")

def fetch_exp_info():
    global exp_info
    try:
        url = "（不公开，提示：）current_detail"
        resp = requests.get(url, headers={"Authorization": bearer}, timeout=10)
        if resp.status_code == 200 and resp.json().get("code") == 0:
            exp_info = resp.json()["data"]
    except Exception:
        exp_info = None

def fetch_statistics():
    global stat_info
    try:
        url = "（不公开，提示：）statistics_v2"
        resp = requests.get(url, headers={"Authorization": bearer}, timeout=10)
        if resp.status_code == 200 and resp.json().get("code") == 0:
            stat_info = resp.json()["data"]
    except Exception:
        stat_info = None

# ---------- 结果 ----------
def add_result(game_name, result):
    t = time.strftime("%H:%M:%S")
    status_class = "success" if str(result["status"]).startswith("2") else "error"
    result_text = f"[{t}] "
    if status_class == "success":
        result_text += f"✅ {game_name} 执行成功\n"
    else:
        result_text += f"❌ {game_name} 执行失败\n"
    result_text += f"状态码: {result['status']}\n"
    if isinstance(result["response"], dict):
        result_text += f"响应:\n{json.dumps(result['response'], ensure_ascii=False, indent=2)}\n"
    else:
        result_text += f"响应: {result['response']}\n"
    result_text += "─" * 50 + "\n"
    with result_lock:
        results.append({"text": result_text, "status": status_class})
        if len(results) > 100:
            results.pop(0)

# ---------- 游戏刷分 ----------
def brush_jump_rope():          return make_request("（不公开，提示：）drill_record_upload", _load_json_body("跳绳"))
def brush_fruit_total():        return make_request("（不公开，提示：）drill_record_upload", _load_json_body("水果总记录"))
def brush_fruit_event():        return make_request("（不公开，提示：）update_score", _load_json_body("水果活动记录"))
def brush_pacman():             return make_request("（不公开，提示：）drill_record_upload", _load_json_body("吃豆人"))
def brush_parkour():            return make_request("（不公开，提示：）drill_record_upload", _load_json_body("极限跑酷"))
def brush_dragon():             return make_request("（不公开，提示：）drill_record_upload", _load_json_body("灵动飞龙"))
def brush_soldier():            return make_request("（不公开，提示：）drill_record_upload", _load_json_body("敏捷火枪手"))
def brush_boxing():             return make_request("（不公开，提示：）drill_record_upload", _load_json_body("动感拳击"))
def brush_coins():              return make_request("（不公开，提示：）receive", {"stage_id": "stage_2"})
def brush_hole_book():          return make_request("（不公开，提示：）drill_record_upload", _load_json_body("洞洞书"))
def brush_rolling_assassin():   return make_request("（不公开，提示：）drill_record_upload", _load_json_body("滚动刺桶"))
def brush_boomerang():          return make_request("（不公开，提示：）drill_record_upload", _load_json_body("回旋镖"))
def brush_squat_jump():         return make_request("（不公开，提示：）drill_record_upload", _load_json_body("太空弹跳"))
def brush_big_jump():           return make_request("（不公开，提示：）drill_record_upload", _load_json_body("大跳绳"))
def brush_jumping_brick():      return make_request("（不公开，提示：）drill_record_upload", _load_json_body("顶顶砖块"))
def Hula_hoops():               return make_request("（不公开，提示：）drill_record_upload", _load_json_body("呼啦圈"))
def push_up():                  return make_request("（不公开，提示：）drill_record_upload", _load_json_body("俯卧撑"))
def Front_palms_together():     return make_request("（不公开，提示：）drill_record_upload", _load_json_body("前合掌"))
def Reverse_support():          return make_request("（不公开，提示：）drill_record_upload", _load_json_body("反向支撑"))
def Run_outdoors():             return make_request("（不公开，提示：）drill_record_upload", _load_json_body("户外跑"))
def one_km_run():               return make_request("（不公开，提示：）drill_record_upload", _load_json_body("1千米跑步"))
def VIP_purchase():             return make_request("（不公开，提示：）add_month_vip", {"month": current_date})
def Ten_thousand_shells():      return make_request("（不公开，提示：）buy_product_v2", {"product_id": "515527804314456100", "product_price": 1000, "activity_shop_id": "starshells_shop", "number": 1000})
def Ten_thousand_diamond():     return make_request("（不公开，提示：）diamond_exchange", {"diamond_delta": 10000, "ttb_delta": 0, "ttp_delta": 10000})
def Ten_thousand_twisted_egg_bottles(): return make_request("（不公开，提示：）exchange_db_v2", {"db_number": 10000, "ttpoint_number": 10000, "currencies": [{"currency_type": "wish", "amount": 0}], "scene_name": "basketball_2023"})

# ---------- Flask 路由 ----------
@app.route('/')
def index():
    fetch_user_info()
    return render_template('index.html', accounts=list(ACCOUNT_MAP.keys()), current_user=current_user, bearer=bearer)

@app.route('/proxy_avatar')
def proxy_avatar():
    auth = request.headers.get("Authorization")
    if not auth:
        return "", 401
    global user_info
    if not user_info or not user_info.get("user_info", {}).get("head_img_url"):
        return "", 404
    avatar_url = user_info["user_info"]["head_img_url"]
    try:
        headers = {"User-Agent": HEADERS["User-Agent"], "Authorization": auth}
        resp = requests.get(avatar_url, headers=headers, stream=True, timeout=10)
        if resp.status_code == 200:
            return send_file(io.BytesIO(resp.content), mimetype=resp.headers.get("Content-Type", "image/jpeg"))
    except Exception:
        pass
    return "", 404

@app.route('/get_user_info')
def get_user_info():
    wallet = {}
    for key, url in [
        ("wallet", "（不公开，提示：）wallet/info"),
        ("store", "（不公开，提示：）sport_card/store_info"),
        ("virtual", "（不公开，提示：）virtual_wallet/info"),
    ]:
        try:
            resp = requests.get(url, headers={"Authorization": bearer}, timeout=5)
            if resp.status_code == 200:
                wallet[key] = resp.json().get("data", {})
        except Exception:
            pass
    return jsonify({
        "user_info": user_info["user_info"] if user_info else None,
        "coin": user_info["gold_coin"]["total_coin"] if user_info else 0,
        "exp_info": exp_info,
        "stat_info": stat_info,
        "wallet": wallet
    })

@app.route('/change_account', methods=['POST'])
def change_account():
    global current_user, bearer, usid, user_info, exp_info, stat_info
    account = request.form.get('account')
    if account in ACCOUNT_MAP:
        current_user = account
        bearer = ACCOUNT_MAP[account]["bearer"]
        usid = ACCOUNT_MAP[account]["usid"]
        fetch_user_info()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "无效的账号"})

@app.route('/add_account', methods=['POST'])
def add_account():
    global bearer, usid, user_info, exp_info, stat_info
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
        bearer = auth
        usid = user_id
        fetch_user_info()
        return jsonify({"status": "success", "account": key, "accounts": list(ACCOUNT_MAP.keys())})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/execute', methods=['POST'])
def execute():
    action = request.form.get('action')
    actions = {
        "跳绳": brush_jump_rope,
        "水果总记录": brush_fruit_total,
        "水果活动记录": brush_fruit_event,
        "吃豆人": brush_pacman,
        "极限跑酷": brush_parkour,
        "灵动飞龙": brush_dragon,
        "敏捷火枪手": brush_soldier,
        "动感拳击": brush_boxing,
        "跳跳币": brush_coins,
        "洞洞书": brush_hole_book,
        "滚动刺桶": brush_rolling_assassin,
        "回旋镖": brush_boomerang,
        "太空弹跳": brush_squat_jump,
        "大跳绳": brush_big_jump,
        "顶顶砖块": brush_jumping_brick,
        "呼啦圈": Hula_hoops,
        "俯卧撑": push_up,
        "前合掌": Front_palms_together,
        "反向支撑": Reverse_support,
        "户外跑": Run_outdoors,
        "1千米跑步": one_km_run,
        "vip购买": VIP_purchase,
        "一万贝壳": Ten_thousand_shells,
        "一万钻石": Ten_thousand_diamond,
        "一万扭蛋瓶": Ten_thousand_twisted_egg_bottles
    }
    if action in actions:
        result = actions[action]()
        add_result(action, result)
        fetch_user_info()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "无效的操作"})

@app.route('/get_results')
def get_results():
    with result_lock:
        return jsonify({"results": results})

@app.route('/clear_results', methods=['POST'])
def clear_results():
    with result_lock:
        results.clear()
    return jsonify({"status": "success"})

# ---------- HTML ----------
INDEX_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>运动数据模拟器</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        body{background:#f8f9fa;padding:20px}
        .card{margin-bottom:20px;box-shadow:0 4px 6px rgba(0,0,0,.1)}
        .avatar{width:60px;height:60px;border-radius:50%;object-fit:cover}
        #resultContainer{background:#343a40;color:#e9ecef;font-family:Consolas,monospace;padding:15px;border-radius:5px;height:400px;overflow-y:auto;white-space:pre-wrap}
    </style>
</head>
<body>
<div class="container">
    <h1 class="text-center mb-4">运动数据模拟器</h1>

    <div class="card">
        <div class="card-body">
            <div class="d-flex align-items-center mb-3">
                <select id="accountSelect" class="form-select me-2" style="width:200px">
                    {% for a in accounts %}
                    <option value="{{ a }}" {% if a==current_user %}selected{% endif %}>{{ a }}</option>
                    {% endfor %}
                </select>
                <button class="btn btn-primary me-2" id="refreshBtn"><i class="bi bi-arrow-clockwise"></i> 刷新</button>
                <button class="btn btn-success" data-bs-toggle="modal" data-bs-target="#addAccountModal"><i class="bi bi-plus-lg"></i> 添加用户</button>
            </div>
            <div id="userInfoCard" class="user-info">
                <div class="d-flex justify-content-center"><div class="spinner-border text-primary"></div></div>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card-body">
            <h5 class="card-title">操作</h5>
            <div class="d-flex flex-wrap">
                <button class="btn btn-primary m-1 btn-action" data-action="跳绳">🎗 跳绳10分钟</button>
                <button class="btn btn-primary m-1 btn-action" data-action="水果总记录">🍒 水果总记录</button>
                <button class="btn btn-primary m-1 btn-action" data-action="水果活动记录">🍒 水果活动记录</button>
                <button class="btn btn-primary m-1 btn-action" data-action="吃豆人">👻 吃豆人</button>
                <button class="btn btn-primary m-1 btn-action" data-action="极限跑酷">🎮 极限跑酷</button>
                <button class="btn btn-primary m-1 btn-action" data-action="灵动飞龙">🐉 灵动飞龙</button>
                <button class="btn btn-primary m-1 btn-action" data-action="敏捷火枪手">🔫 敏捷火枪手</button>
                <button class="btn btn-primary m-1 btn-action" data-action="动感拳击">🥊 动感拳击</button>
                <button class="btn btn-primary m-1 btn-action" data-action="跳跳币">💰 500跳跳币</button>
                <button class="btn btn-primary m-1 btn-action" data-action="洞洞书">📖 洞洞书</button>
                <button class="btn btn-primary m-1 btn-action" data-action="滚动刺桶">🛢️ 滚动刺桶</button>
                <button class="btn btn-primary m-1 btn-action" data-action="回旋镖">🥟 回旋镖</button>
                <button class="btn btn-primary m-1 btn-action" data-action="太空弹跳">🚀 太空弹跳</button>
                <button class="btn btn-primary m-1 btn-action" data-action="大跳绳">〰 大跳绳</button>
                <button class="btn btn-primary m-1 btn-action" data-action="顶顶砖块">🧱 顶顶砖块</button>
                <button class="btn btn-primary m-1 btn-action" data-action="呼啦圈">🌀 呼啦圈</button>
                <button class="btn btn-primary m-1 btn-action" data-action="俯卧撑">🤸 俯卧撑</button>
                <button class="btn btn-primary m-1 btn-action" data-action="前合掌">🙏 前合掌</button>
                <button class="btn btn-primary m-1 btn-action" data-action="反向支撑">🛡️ 反向支撑</button>
                <button class="btn btn-primary m-1 btn-action" data-action="1千米跑步">🏃‍ 1000米跑步</button>
                <button class="btn btn-primary m-1 btn-action" data-action="户外跑">🏃 户外跑</button>
                <button class="btn btn-primary m-1 btn-action" data-action="vip购买">🎟️ vip购买</button>
                <button class="btn btn-primary m-1 btn-action" data-action="一万贝壳">🐚 10000贝壳</button>
                <button class="btn btn-primary m-1 btn-action" data-action="一万钻石">💎 10000钻石</button>
                <button class="btn btn-primary m-1 btn-action" data-action="一万扭蛋瓶">🥚 10000扭蛋瓶</button>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card-body">
            <div class="d-flex justify-content-between mb-3">
                <h5 class="card-title mb-0">执行结果</h5>
                <button class="btn btn-danger btn-sm" id="clearResultsBtn"><i class="bi bi-trash"></i> 清空结果</button>
            </div>
            <div id="resultContainer"></div>
        </div>
    </div>
</div>

<div class="modal fade" id="addAccountModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog"><div class="modal-content">
        <div class="modal-header"><h5 class="modal-title">添加用户</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
        <div class="modal-body">
            <label class="form-label">Authorization</label>
            <input type="text" class="form-control" id="authInput" placeholder="请输入Authorization">
        </div>
        <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
            <button type="button" class="btn btn-primary" id="confirmAddBtn">确认添加</button>
        </div>
    </div></div>
</div>
<div class="card mt-3">
    <div class="card-body text-center">
        <a href="http://192.168.1.202:5001" target="_blank" class="btn btn-success btn-lg">
            <i class="bi bi-flower1"></i> 农场助手
        </a>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jquery@3.6.0/dist/jquery.min.js"></script>
<script>
const bearer = `{{ bearer }}`;
// ---------- 滚动控制 ----------
let autoScroll = true;
let lastResultCount = 0; // 跟踪上次结果数量

// 监听滚动：用户离开底部就暂停自动滚动
$('#resultContainer').on('scroll', function () {
    const $this = $(this);
    const isNearBottom = $this.scrollTop() + $this.innerHeight() >= $this[0].scrollHeight - 10;
    autoScroll = isNearBottom;
});

$(function () {
    // 页面初始化
    loadUserInfo();
    loadResults();
    setInterval(loadResults, 1000);

    // 账号切换
    $('#accountSelect').change(function () {
        $.post('/change_account', { account: this.value }, r => {
            if (r.status === 'success') location.reload();
        });
    });

    // 刷新按钮
    $('#refreshBtn').click(loadUserInfo);

    // 功能按钮
    $(document).on('click', '.btn-action', function () {
        const action = $(this).data('action');
        $.post('/execute', { action: action }, () => loadResults());
    });

    // 清空结果
    $('#clearResultsBtn').click(() => {
        $.post('/clear_results', () => {
            lastResultCount = 0; // 重置计数器
            loadResults(true); // 强制刷新
        });
    });

    // 添加账号
    $('#confirmAddBtn').click(() => {
        const auth = $('#authInput').val().trim();
        if (!auth) return alert('请输入Authorization');
        $.post('/add_account', { auth }, r => {
            if (r.status === 'success') location.reload();
            else alert(r.message);
        });
    });

    // 加载用户信息
    function loadUserInfo() {
        $('#userInfoCard').html('<div class="d-flex justify-content-center"><div class="spinner-border text-primary"></div></div>');
        $.get('/get_user_info', d => {
            if (!d.user_info) {
                $('#userInfoCard').html('<div class="text-danger text-center">无法获取用户信息</div>');
                return;
            }
            const u = d.user_info, c = d.coin, e = d.exp_info, s = d.stat_info, w = d.wallet || {};
            const dianshu = d.wallet?.virtual?.ttpoint || 0;  // 新增跳跳点数
            const html = `
                <div class="d-flex flex-wrap align-items-center">
                    <img id="avatarImg" class="avatar me-3" src="https://placehold.co/60x60">
                    <div class="me-4"><h5>${u.nick_name}</h5><p>学校：${u.school || '未知'}</p><p class="text-warning"><strong>能量豆：${c} 跳跳点数：${dianshu}</strong></p></div>
                    <div class="me-4">
                        ${e ? `<p>等级：Lv${e.level_no} (${e.exp_total}/${e.current_level_delta_exp})</p>` : ''}
                        ${s ? `<p>已燃脂：${s.burned_calories} kcal</p><p>训练天数：${s.training_days}</p>` : ''}
                    </div>
                    <div>
                        <p><strong>💰 钱包</strong></p>
                        <div class="d-flex flex-wrap">
                            <span class="me-2">跳跳币: ${w.wallet?.ttb_amount || 0}</span>
                            <span class="me-2">钻石: ${w.store?.diamond_amount || 0}</span>
                            <span class="me-2">扭蛋瓶: ${w.wallet?.bottle_amount || 0}</span>
                            <span class="me-2">星贝壳: ${w.virtual?.starshell || 0}</span>
                            <span>许愿币: ${w.virtual?.island_lottery_coin || 0}</span>
                        </div>
                        <p class="text-danger"><small>切水果vip购买-被修复别用</small></p>
                    </div>
                </div>`;
            $('#userInfoCard').html(html);

            // 头像
            fetch('/proxy_avatar', { method: 'GET', headers: { Authorization: bearer } })
                .then(r => r.ok ? r.blob() : Promise.reject())
                .then(b => document.getElementById('avatarImg').src = URL.createObjectURL(b))
                .catch(() => {});
        }).fail(() => $('#userInfoCard').html('<div class="text-danger text-center">获取用户信息失败</div>'));
    }

    // 加载结果
    function loadResults(force = false) {
        $.get('/get_results', d => {
            // 只有当结果数量变化或强制刷新时才更新DOM
            if (!force && d.results.length === lastResultCount) return;
            lastResultCount = d.results.length;
        
            const c = $('#resultContainer');
            const wasScrolledToBottom = autoScroll;
            const oldScrollHeight = c[0].scrollHeight;
            const oldScrollTop = c[0].scrollTop;
        
            c.empty();
            d.results.forEach(r => {
                r.text.split('\n').forEach(l => {
                    if (!l.trim()) return;
                    const div = $('<div>');
                    if (l.includes('✅')) div.addClass('text-success');
                    else if (l.includes('❌')) div.addClass('text-danger');
                    div.text(l);
                    c.append(div);
                });
            });
        
            // 保持滚动位置
            if (!wasScrolledToBottom) {
                const newScrollHeight = c[0].scrollHeight;
                c.scrollTop(oldScrollTop + (newScrollHeight - oldScrollHeight));
            } else {
                c.scrollTop(c[0].scrollHeight);
            }
        });
    }
});
</script>
</body>
</html>'''

# ---------- 启动 ----------
if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    index_path = os.path.join('templates', 'index.html')
    # 直接写入文件，覆盖已存在的文件
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(INDEX_HTML)
    app.run(host='0.0.0.0', port=5000, debug=True)
