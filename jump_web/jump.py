import tkinter as tk
from tkinter import simpledialog, ttk, messagebox
import requests
import json
import time,datetime
import re
import os

# ---------------- 统一配置 ----------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; 21091116AC Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Mobile Safari/537.36",
    "Connection": "close",
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "Cookie": "acw_tc=ac11000117538680237588324e647b17355604a102996c494b42b9cc3d488a; Hm_lvt_906658e7563d9820b4b1dc05e757c682=1753576990,1753837345,1753850232,1753859036",
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

# 预设账号
ACCOUNT_MAP = {
    "菲原": {
        "bearer": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiMWU1ODFlMzItM2YwOS00NmNiLTkxN2QtMmJhOGJiMmI2N2YwIiwiZXhwIjoxNzU2MzkyODg0MDAwLCJjb2RlIjo4NDEzMzF9.UE9WxK5fHrSq7L2p4tTYagCXdUaQf8c2pof7uZXApXY",
        "usid": "1e581e32-3f09-46cb-917d-2ba8bb2b67f0"
    },
    "菲新": {
        "bearer": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiN2IyODgwNmMtMDJhNy00MWYyLTg1M2QtY2M1MTI0NzA1ZTBlIiwiZXhwIjoxNzU2ODIxMzIyMDAwLCJjb2RlIjozMTkyMzF9.1BhxUj6HIHlAqws8VZMnnLtCqX95uHsQ66l4z67buIQ",
        "usid": "7b28806c-02a7-41f2-853d-cc5124705e0e"
    },
    "测试": {
        "bearer": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiNjYxYWE0NTUtYzRjZS00YzE3LThkMzEtYTk3ZjZkNGViNmZiIiwiZXhwIjoxNzU2OTc3NTIwMDAwLCJjb2RlIjowfQ.i1EU_m9UH5ROHsYdGlv6xLMUjWptYSMrGVURvdj6ABs",
        "usid": "661aa455-c4ce-4c17-8d31-a97f6d4eb6fb"
    }
}
current_date=datetime.datetime.now().strftime('%Y-%m')

# ---------------- 主程序 ----------------
class SportDataBot:
    BODIES_FILE = os.path.join(os.path.dirname(__file__), 'bodies.json')
    def __init__(self, root):
        self.root = root
        self.root.title("运动数据刷取工具")
        self.root.geometry("950x750")
        self.root.configure(bg="#f0f0f0")

        self.bearer = None
        self.usid = None
        self.user_info = None

        self.set_default_account()  # 新增

        # 全局 record_id 管理器
        self.record_mgr = RecordIdManager()

        # 创建样式
        self.setup_styles()

        # 选择账号
        
        self.fetch_user_info()      # 原来就有
        self.create_widgets()

    # ---------- 账号选择 ----------
    def set_account(self):
        key = self.account_var.get()
        self.bearer = ACCOUNT_MAP[key]["bearer"]
        self.usid = ACCOUNT_MAP[key]["usid"]

    def confirm_account(self):
        self.set_account()
        self.select_frame.destroy()
        self.fetch_user_info()
        self.create_widgets()

    def fetch_user_info(self):
        try:
            url = "https://api.tiantiantiaosheng.com/api/user/user_info"
            headers = {"Authorization": self.bearer}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    self.user_info = data["data"]
                    self.exp_info = self.fetch_exp_info()
                    self.stat_info = self.fetch_statistics()
                else:
                    self.user_info = None
            else:
                self.user_info = None
        except Exception as e:
            self.user_info = None
            print("获取用户信息失败:", e)

    def set_default_account(self):
        key = "菲新"  # 你想默认启动的账号
        self.bearer = ACCOUNT_MAP[key]["bearer"]
        self.usid = ACCOUNT_MAP[key]["usid"]

    def fetch_exp_info(self):
        try:
            url = "https://api.tiantiantiaosheng.com/api/user/exp/current_detail"
            resp = requests.get(url, headers={"Authorization": self.bearer}, timeout=10)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                return resp.json()["data"]
        except Exception:
            pass
        return None

    def fetch_statistics(self):
        try:
            url = "https://api.tiantiantiaosheng.com/api/user/drill_record/statistics_v2"
            resp = requests.get(url, headers={"Authorization": self.bearer}, timeout=10)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                return resp.json()["data"]
        except Exception:
            pass
        return None

    def confirm_account(self):
        self.set_account()
        self.select_frame.destroy()
        self.fetch_user_info()  # 新增
        self.create_widgets()

    def populate_user_combo(self):
        self.user_combo["values"] = list(ACCOUNT_MAP.keys())
        if hasattr(self, 'temp_users'):
            self.user_combo["values"] += tuple(self.temp_users.keys())
        # 选中当前
        current = next((k for k, v in ACCOUNT_MAP.items() if v["bearer"] == self.bearer), None)
        if not current and hasattr(self, 'temp_users'):
            current = next((k for k, v in self.temp_users.items() if v["bearer"] == self.bearer), None)
        self.user_combo.set(current or "")

        self.user_combo.bind("<<ComboboxSelected>>", self.on_user_change)

    def on_user_change(self, event):
        key = self.user_combo.get()
        if key in ACCOUNT_MAP:
            self.bearer = ACCOUNT_MAP[key]["bearer"]
            self.usid = ACCOUNT_MAP[key]["usid"]
        elif hasattr(self, 'temp_users') and key in self.temp_users:
            self.bearer = self.temp_users[key]["bearer"]
            self.usid = self.temp_users[key]["usid"]
        self.refresh_user_info()

    def add_user_dialog(self):
        auth = simpledialog.askstring("添加用户", "请输入 Authorization：", parent=self.root)
        if not auth:
            return
        try:
            url = "https://api.tiantiantiaosheng.com/api/user/user_info"
            resp = requests.get(url, headers={"Authorization": auth}, timeout=10)
            if resp.status_code != 200 or resp.json().get("code") != 0:
                messagebox.showerror("错误", "Authorization 无效或网络异常")
                return
            user_id = resp.json()["data"]["user_info"]["user_id"]
            nick = resp.json()["data"]["user_info"]["nick_name"]
            key = f"{nick}(临时)"
            if not hasattr(self, 'temp_users'):
                self.temp_users = {}
            self.temp_users[key] = {"bearer": auth, "usid": user_id}
            self.populate_user_combo()
            self.user_combo.set(key)
            self.on_user_change(None)
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def refresh_user_info(self):
        self.fetch_user_info()
        self.display_user_info_card()

    # ---------- 样式 ----------
    def create_user_toolbar(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, pady=(0, 10))

        self.user_combo = ttk.Combobox(bar, state="readonly", width=20)
        self.user_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.populate_user_combo()

        ttk.Button(bar, text="➕ 添加用户", command=self.add_user_dialog).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(bar, text="🔄 刷新", command=self.refresh_user_info).pack(side=tk.LEFT)

        self.user_info_frame = ttk.LabelFrame(parent, text="用户信息", padding=10)
        self.user_info_frame.pack(fill=tk.X, pady=(0, 10))
    def display_user_info_card(self):
        for w in self.user_info_frame.winfo_children():
            w.destroy()
        if not self.user_info:
            ttk.Label(self.user_info_frame, text="无法获取用户信息").pack()
            return

        # 拉取钱包信息
        wallet = {}
        try:
            for api in [
                ("wallet", "https://api.tiantiantiaosheng.com/api2/wallet/info"),
                ("store",  "https://api.tiantiantiaosheng.com/api2/sport_card/store_info"),
                ("virtual","https://api.tiantiantiaosheng.com/api2/virtual_wallet/info"),
            ]:
                resp = requests.get(api[1], headers={"Authorization": self.bearer}, timeout=5)
                if resp.status_code == 200:
                    wallet[api[0]] = resp.json().get("data", {})
        except Exception:
            pass

        # 统一容器
        container = ttk.Frame(self.user_info_frame)
        container.pack(fill=tk.X)

        # 1️⃣ 头像
        left = ttk.Frame(container)
        left.pack(side=tk.LEFT, padx=5)
        try:
            from PIL import Image, ImageTk
            from io import BytesIO
            img_url = self.user_info["user_info"]["head_img_url"]
            img_data = requests.get(img_url, timeout=5).content
            img = Image.open(BytesIO(img_data)).resize((60, 60))
            self.avatar_img = ImageTk.PhotoImage(img)
            tk.Label(left, image=self.avatar_img).pack()
        except Exception:
            pass

        # 2️⃣ 基本信息
        mid = ttk.Frame(container)
        mid.pack(side=tk.LEFT, padx=10, fill=tk.Y)
        user = self.user_info["user_info"]
        coin = self.user_info["gold_coin"]["total_coin"]
        dianshu = wallet.get('virtual', {}).get('ttpoint', 0)
        ttk.Label(mid, text=f"昵称：{user['nick_name']}", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(mid, text=f"学校：{user['school']}", font=("Segoe UI", 10)).pack(anchor="w")
        ttk.Label(mid, text=f"能量豆：{coin} 跳跳点数：{dianshu}", font=("Segoe UI", 10, "bold"), foreground="#f39c12").pack(anchor="w")

        # 3️⃣ 经验 & 统计
        right = ttk.Frame(container)
        right.pack(side=tk.LEFT, padx=10, fill=tk.Y)
        if self.exp_info:
            lvl  = self.exp_info["level_no"]
            exp  = self.exp_info["exp_total"]
            need = self.exp_info["current_level_delta_exp"]
            ttk.Label(right, text=f"等级：Lv{lvl}  ({exp}/{need})", font=("Segoe UI", 10)).pack(anchor="w")
        if self.stat_info:
            burn = self.stat_info["burned_calories"]
            days = self.stat_info["training_days"]
            ttk.Label(right, text=f"已燃脂：{burn} kcal", font=("Segoe UI", 10)).pack(anchor="w")
            ttk.Label(right, text=f"训练天数：{days}", font=("Segoe UI", 10)).pack(anchor="w")

        # 4️⃣ 钱包信息（横向）
        wallet_bar = ttk.Frame(container)
        wallet_bar.pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Label(wallet_bar, text="💰 钱包", font=("Segoe UI", 10, "bold")).pack(side=tk.TOP, anchor="w")
        w = ttk.Frame(wallet_bar)               # 横向容器
        w.pack(side=tk.TOP, anchor="w")
        labels = [
            ("跳跳币", wallet.get('wallet', {}).get('ttb_amount', 0)),
            ("钻石", wallet.get('store', {}).get('diamond_amount', 0)),
            ("扭蛋瓶", wallet.get('wallet', {}).get('bottle_amount', 0)),
            ("星贝壳", wallet.get('virtual', {}).get('starshell', 0)),
            ("许愿币", wallet.get('virtual', {}).get('island_lottery_coin', 0)),
        ]
        for txt, val in labels:
            ttk.Label(w, text=f"{txt}:{val}", foreground="#3498db").pack(side=tk.LEFT, padx=4)
        # 新增提示行
        ttk.Label(wallet_bar, text="vip购买-不稳定别用", foreground="#e74c3c", font=("Segoe UI", 9)).pack(side=tk.TOP, anchor="w", pady=(2,0))

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Modern.TButton",
            font=("Segoe UI", 10, "bold"),
            foreground="#2c3e50",
            background="#3498db",
            borderwidth=0,
            focusthickness=3,
            focuscolor="none",
            padding=6
        )
        style.map(
            "Modern.TButton",
            background=[("active", "#2980b9"), ("disabled", "#bdc3c7")]
        )
        style.configure(
            "Title.TLabel",
            font=("Segoe UI", 18, "bold"),
            foreground="#2c3e50",
            background="#f0f0f0"
        )
        style.configure(
            "Header.TLabel",
            font=("Segoe UI", 14, "bold"),
            foreground="#34495e",
            background="#f0f0f0"
        )

    # ---------- 主界面 ----------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.create_user_toolbar(main_frame)
        self.display_user_info_card()

        # 标题
        title = ttk.Label(main_frame, text="运动数据刷取工具", style="Title.TLabel")
        title.pack(pady=10)

        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, pady=(0, 10))

        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 10))

        self.create_buttons(button_frame)

        # 结果展示
        result_frame = ttk.LabelFrame(main_frame, text="执行结果")
        result_frame.pack(fill=tk.BOTH, expand=True)

        text_frame = ttk.Frame(result_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.result_text = tk.Text(
            text_frame,
            height=15,
            font=("Consolas", 9),
            bg="#2c3e50",
            fg="#ecf0f1",
            insertbackground="#ecf0f1",
            relief=tk.FLAT,
            padx=10,
            pady=10
        )
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scroll.set)

        self.result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        clear_btn = ttk.Button(self.result_text, text="🗑️ 清空结果", command=self.clear_results, style="Modern.TButton")
        clear_btn.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)

    # ---------- 按钮 ----------
        # ---------- 修改后的按钮 ----------
    def create_buttons(self, parent):
        buttons = [
            ("🎗 跳绳10分钟", self.brush_jump_rope),
            ("🍒 水果总记录", self.brush_fruit_total),
            ("🍒 水果活动记录", self.brush_fruit_event),
            ("👻 吃豆人", self.brush_pacman),
            ("🎮 极限跑酷", self.brush_parkour),
            ("🐉 灵动飞龙", self.brush_dragon),
            ("🔫 敏捷火枪手", self.brush_soldier),
            ("🥊 动感拳击", self.brush_boxing),
            ("💰 500跳跳点数", self.brush_coins),
            ("📖 洞洞书", self.brush_hole_book),
            ("🛢️ 滚动刺桶", self.brush_rolling_assassin),
            ("🥟 回旋镖", self.brush_boomerang),
            ("🚀 太空弹跳", self.brush_squat_jump),
            ("〰 大跳绳", self.brush_big_jump),
            ("🧱 顶顶砖块", self.brush_jumping_brick),
            ("🌀 呼啦圈", self.Hula_hoops),
            ("🤸 俯卧撑", self.push_up),
            ("🙏 前合掌", self.Front_palms_together),
            ("🛡️ 反向支撑", self.Reverse_support),
            ("🏃‍ 1000米跑步", self.one_km_run),
            ("🏃 户外跑", self.Run_outdoors),
            ("🎟️ vip购买", self.VIP_purchase),
            ("🐚 10000贝壳", self.Ten_thousand_shells),
            ("💎 10000钻石", self.Ten_thousand_diamond),
            ("🥚 10000扭蛋瓶", self.Ten_thousand_twisted_egg_bottles),
        ]

        row, col = 0, 0
        max_cols = 6        # 原来 4 → 改成 6，可再调
        for text, cmd in buttons:
            # 自适应宽度：字符数 + 2 留白
            btn = ttk.Button(parent, text=text, command=cmd, style="Modern.TButton",
                             width=len(text)+2)
            btn.grid(row=row, column=col, padx=2, pady=3, sticky="ew")
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        for i in range(max_cols):
            parent.grid_columnconfigure(i, weight=1)

    # ---------- 通用请求 ----------
    def make_request(self, url: str, body: dict):
        try:
            update_time_and_record(body, self.record_mgr)
            headers = {**HEADERS, "Authorization": self.bearer}
            resp = requests.post(url, headers=headers, json=body, timeout=10)
            return {
                "status": resp.status_code,
                "response": resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
            }
        except Exception as e:
            return {"status": "error", "response": str(e)}

    # ---------- 各项目 ----------
    def brush_jump_rope(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("跳绳")
        result = self.make_request(url, body)
        self.display_result("跳绳", result)#跳绳    
    def brush_fruit_total(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("水果总记录")
        result = self.make_request(url, body)
        self.display_result("水果总记录", result)#水果总记录    
    def brush_fruit_event(self):
        url = "https://api.tiantiantiaosheng.com/api2/sfruit_ninja/update_score"
        body = self._load_json_body("水果活动记录")
        result = self.make_request(url, body)
        self.display_result("水果活动记录", result)#水果活动记录    
    def brush_pacman(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("吃豆人")
        result = self.make_request(url, body)
        self.display_result("吃豆人", result)#吃豆人    
    def brush_parkour(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("极限跑酷")
        result = self.make_request(url, body)
        self.display_result("极限跑酷", result)#极限跑酷    
    def brush_dragon(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("灵动飞龙")
        result = self.make_request(url, body)
        self.display_result("灵动飞龙", result)# 灵动飞龙    
    def brush_soldier(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("敏捷火枪手")
        result = self.make_request(url, body)
        self.display_result("敏捷火枪手", result)# 敏捷火枪手    
    def brush_boxing(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("动感拳击")
        result = self.make_request(url, body)
        self.display_result("动感拳击", result)# 动感拳击    
    def brush_coins(self):
        url = "https://api.tiantiantiaosheng.com/api2/invite_2412/receive"
        body = {"stage_id": "stage_2"}
        result = self.make_request(url, body)
        self.display_result("跳跳币", result) # 跳跳币
    def brush_hole_book(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("洞洞书")
        result = self.make_request(url, body)
        self.display_result("洞洞书", result)#洞洞书    
    def brush_rolling_assassin(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("滚动刺桶")
        result = self.make_request(url, body)
        self.display_result("滚动刺桶", result)# 滚动刺桶    
    def brush_boomerang(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("回旋镖")
        result = self.make_request(url, body)
        self.display_result("回旋镖", result)# 回旋镖    
    def brush_squat_jump(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("太空弹跳")
        result = self.make_request(url, body)
        self.display_result("太空弹跳", result)#太空弹跳    
    def brush_big_jump(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("大跳绳")
        result = self.make_request(url, body)
        self.display_result("大跳绳", result)#大跳绳    
    def brush_jumping_brick(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("顶顶砖块")
        result = self.make_request(url, body)
        self.display_result("顶顶砖块", result)# 顶顶砖块    
    def Hula_hoops(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("呼啦圈")
        result = self.make_request(url, body)
        self.display_result("呼啦圈", result)# 呼啦圈    
    def push_up(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("俯卧撑")
        result = self.make_request(url, body)
        self.display_result("俯卧撑", result)# 俯卧撑    
    def Front_palms_together(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("前合掌")
        result = self.make_request(url, body)
        self.display_result("前合掌", result)# 前合掌    
    def Reverse_support(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("反向支撑")
        result = self.make_request(url, body)
        self.display_result("反向支撑", result)# 反向支撑   
    def Run_outdoors(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("户外跑")
        result = self.make_request(url, body)
        self.display_result("户外跑", result)# 户外跑    
    def one_km_run(self):
        url = "https://api.tiantiantiaosheng.com/api/user/drill_record_upload"
        body = self._load_json_body("1千米跑步")
        result = self.make_request(url, body)
        self.display_result("1千米跑步", result)# 1千米跑步    
    def VIP_purchase(self):
        url = "https://api.tiantiantiaosheng.com/api2/sfruit_ninja/add_month_vip"
        body = {"month":current_date}
        result = self.make_request(url, body)
        self.display_result("vip购买", result)#vip购买    
    def Ten_thousand_shells(self):
        url = "https://api.tiantiantiaosheng.com/api2/virtual_mall/activity_shop/buy_product_v2"
        body = {"product_id": "515527804314456100","product_price": 1000,"activity_shop_id": "starshells_shop","number": 1000}
        result = self.make_request(url, body)
        self.display_result("一万贝壳", result)# 一万贝壳   
    def Ten_thousand_diamond(self):
        url = "https://api.tiantiantiaosheng.com/api2/sport_card/diamond_exchange"
        body = {"diamond_delta":10000,"ttb_delta":0,"ttp_delta":10000}
        result = self.make_request(url, body)
        self.display_result("一万钻石", result) # 一万钻石 
    def Ten_thousand_twisted_egg_bottles(self):
        url = "https://api.tiantiantiaosheng.com/api2/common_lottery/exchange_db_v2"
        body = {"db_number": 10000,"ttpoint_number": 10000,"currencies": [{"currency_type": "wish","amount": 0}],"scene_name": "basketball_2023"}
        result = self.make_request(url, body)
        self.display_result("一万扭蛋瓶", result)# 一万扭蛋瓶


    # ---------- 辅助 ----------
    def _replace_id(self, obj):
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if k == "user_id" and v == "__USER_ID__":
                    obj[k] = self.usid
                elif isinstance(v, (dict, list)):
                    self._replace_id(v)
        elif isinstance(obj, list):
            for item in obj:
                self._replace_id(item)
    def _load_json_body(self, key):
        with open(self.BODIES_FILE, 'r', encoding='utf-8') as f:
            body = json.load(f)[key]
        # 3. 递归替换 __USER_ID__ -> self.usid
        self._replace_id(body)
        return body

    def display_result(self, game_name, result):
        t = time.strftime("%H:%M:%S")
        self.result_text.tag_config("success", foreground="#2ecc71")
        self.result_text.tag_config("error", foreground="#e74c3c")
        self.result_text.tag_config("info", foreground="#3498db")
        self.result_text.tag_config("timestamp", foreground="#95a5a6")

        self.result_text.insert(tk.END, f"[{t}] ", "timestamp")
        if str(result["status"]).startswith("2"):
            self.result_text.insert(tk.END, f"✅ {game_name} 执行成功\n", "success")
        else:
            self.result_text.insert(tk.END, f"❌ {game_name} 执行失败\n", "error")
        self.result_text.insert(tk.END, f"状态码: {result['status']}\n", "info")
        if isinstance(result["response"], dict):
            self.result_text.insert(tk.END, f"响应:\n{json.dumps(result['response'], ensure_ascii=False, indent=2)}\n")
        else:
            self.result_text.insert(tk.END, f"响应: {result['response']}\n")
        self.result_text.insert(tk.END, "─" * 50 + "\n")
        self.result_text.see(tk.END)

        print(f"\n[{t}] 【{game_name}】")
        print(f"状态码: {result['status']}")
        print(f"响应: {json.dumps(result['response'], ensure_ascii=False, indent=2)}")

        self.refresh_user_info()

    def clear_results(self):
        self.result_text.delete(1.0, tk.END)


# ---------- Record 管理 ----------
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


# ---------- 通用工具 ----------
def update_time_and_record(obj, mgr):
    now = int(time.time() * 1000)

    if isinstance(obj, dict):
        if "take_time" in obj:
            obj["end_time"] = now
            obj["begin_time"] = now - obj["take_time"]
        if "record_id" in obj:
            obj["record_id"] = mgr.next()
        for v in obj.values():
            update_time_and_record(v, mgr)
    elif isinstance(obj, list):
        for item in obj:
            update_time_and_record(item, mgr)


# ---------- 启动 ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = SportDataBot(root)
    root.mainloop()