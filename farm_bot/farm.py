import json
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, simpledialog, scrolledtext
import requests
import time
import threading
from datetime import datetime

# ===== 1. 全局配置 =====
with open("headers.json", encoding="utf-8") as f:
    HEADERS = json.load(f)
with open("accounts.json", encoding="utf-8") as f:
    ACCOUNT_MAP = json.load(f)
try:
    with open("crop_map.json", encoding="utf-8") as f:
        CROP_MAP = json.load(f)
except FileNotFoundError:
    CROP_MAP = {}

# ===== 2. 日志 =====
def log(widget, text):
    widget.configure(state='normal')
    widget.insert(tk.END, f"[{datetime.now():%H:%M:%S}] {text}\n")
    widget.see(tk.END)
    widget.configure(state='disabled')

class Tooltip:
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None

    def showtip_at(self, text, x, y):
        if self.tipwindow or not text:
            return
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=text, background="#ffffe0", relief="solid", borderwidth=1, font=("Arial", 10))
        label.pack(ipadx=2, ipady=2)

    def hidetip(self):
        if self.tipwindow:
            self.tipwindow.destroy()
        self.tipwindow = None

# ===== 3. 肥料 =====
class FertilizerClient:
    def __init__(self):
        self.products = []
        self.auth = None

    def load_product_names(self):
        try:
            with open("fertilizer_list.json", encoding="utf-8") as f:
                self.products = json.load(f)
        except FileNotFoundError:
            self.products = []

    def load_or_refresh(self):
        if not self.auth:
            return
        try:
            headers = {**HEADERS, "Authorization": self.auth}
            resp = requests.get(
                "https://api.tiantiantiaosheng.com/api2/sports_island/farm/hot_sale_products?activity_id=ac_farm_fertilizer",
                headers=headers, timeout=10)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                self.products = resp.json()["data"]["product_list"]
                with open("fertilizer_list.json", "w", encoding="utf-8") as f:
                    json.dump(self.products, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(self.log_box, f"肥料列表失败：{e}")

    def get_name(self, item_id):
        for p in self.products:
            if str(p.get("item_id")) == str(item_id):
                return p["name"]
        return str(item_id)

    def buy_dialog(self, parent, log_widget):
        self.load_or_refresh()
        if not self.products:
            messagebox.showinfo("提示", "暂无肥料可购买")
            return
        names = [f"{p['name']} ({p['original_price'] * 10}跳跳点数)" for p in self.products]
        idx = simpledialog.askinteger(
            "购买肥料",
            "请选择肥料编号（从1开始）：\n" + "\n".join([f"{i+1}. {n}" for i, n in enumerate(names)]),
            parent=parent, minvalue=1, maxvalue=len(names))
        if not idx:
            return
        p = self.products[idx - 1]

        # 子线程里循环买 30 次
        def _buy_loop():
            for i in range(30):
                payload = {
                    "product_id": p["product_id"],
                    "product_price": p["original_price"],
                    "activity_shop_id": "inside_unity",
                    "number": 1
                }
                try:
                    headers = {**HEADERS, "Authorization": self.auth}
                    resp = requests.post(
                        "https://api.tiantiantiaosheng.com/api2/virtual_mall/activity_shop/buy_product_v2",
                        json=payload, headers=headers, timeout=10)
                    msg = resp.json().get("msg", "")
                    # 回主线程写日志
                    parent.after(0, lambda m=f"第 {i+1}/30 次：{msg}": log(log_widget, m))
                except Exception as e:
                    parent.after(0, lambda e=e: log(log_widget, str(e)))
                time.sleep(0.25)
            parent.after(0, lambda: messagebox.showinfo("完成", "已尝试购买 30 份肥料"))
        threading.Thread(target=_buy_loop, daemon=True).start()

# ===== 4. 偷菜窗口 =====
class StealDialog(tk.Toplevel):
    def __init__(self, parent, api_get, api_post, log_box, crop_map, fertilizer_client, friend_cache):
        super().__init__(parent)
        self.title("好友菜园")
        self.geometry("1000x800")
        self.api_get = api_get
        self.api_post = api_post
        self.log_box = log_box
        self.crop_map = crop_map
        self.fertilizer_client = fertilizer_client
        self.loaded = friend_cache
        self.batch_size = 5
        self.running = False
        self.current_batch = 0

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        frame = ttk.Frame(self)
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # ================= Treeview 创建与表头绑定 =================
        self.tree = ttk.Treeview(
            frame,
            columns=("nick", "lvl", "exp", "stall", "status"),
            show="headings")
        heads = ("昵称", "农场等级", "农场经验值", "蔬菜摊等级", "状态")
        for col, h in zip(self.tree["columns"], heads):
            self.tree.heading(col, text=h, anchor="center",
                              command=lambda c=col: self._sort_column(c))
            self.tree.column(col, width=100, stretch=True)

        # 记录每列当前升/降序状态
        self.sort_reverse = {c: False for c in self.tree["columns"]}

        # ================= 其余原有控件保持不变 =================
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_search())
        self.search_var = tk.StringVar()
        search_frame = ttk.Frame(self)
        search_frame.grid(row=2, column=0, pady=5, sticky="ew")
        ttk.Label(search_frame, text="🔍 搜索好友：").pack(side="left", padx=5)
        ttk.Entry(search_frame, textvariable=self.search_var, width=20).pack(side="left", padx=5)
        ttk.Label(search_frame, text=" 蓝色=搜索结果 黄色=已选中+搜索匹配", foreground="blue").pack(side="left", padx=10)
        self.search_var.trace_add("write", self._on_search)

        self.tree.tag_configure("blue", background="lightblue")
        self.tree.tag_configure("yellow", background="yellow")

        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        btn = ttk.Frame(self)
        btn.grid(row=1, column=0, pady=5)
        ttk.Button(btn, text="开始偷菜", command=self.start_steal).pack(side="left", padx=5)
        ttk.Button(btn, text="暂停/继续", command=self.toggle_pause).pack(side="left", padx=5)
        ttk.Button(btn, text="关闭", command=self.destroy).pack(side="left", padx=5)

        self.friends = []
        self.load_friends()
        self._start_live_loader()
        self.tree.bind("<Double-1>", self.show_friend_detail)

    # ================ 新增排序函数（类成员方法） ================
    def _sort_column(self, col):
        """点击表头排序：数字列按数值，昵称按拼音，状态按已熟数量"""
        rows = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        reverse = self.sort_reverse[col] = not self.sort_reverse[col]

        if col == "nick":
            # 中文昵称 → 按拼音首字母排序（需 pip install pypinyin）
            try:
                import pypinyin
                def key_fn(t):
                    return ''.join([p[0] for p in pypinyin.lazy_pinyin(t[0])])
                rows.sort(key=key_fn, reverse=reverse)
            except ImportError:
                # 没有 pypinyin 就按 Unicode
                rows.sort(key=lambda t: t[0], reverse=reverse)
        elif col in ("lvl", "exp", "stall"):
            # 数值列
            rows.sort(key=lambda t: int(t[0]) if str(t[0]).isdigit() else 0, reverse=reverse)
        elif col == "status":
            # 统计“已熟”出现次数
            def ripe_cnt(txt):
                return txt.count("已熟")
            rows.sort(key=lambda t: ripe_cnt(t[0]), reverse=reverse)
        else:
            rows.sort(key=lambda t: t[0], reverse=reverse)

        # 重新插入以应用排序
        for idx, (val, k) in enumerate(rows):
            self.tree.move(k, "", idx)

    def _start_live_loader(self):
        """实时逐条刷新好友农场"""
        self.after(100, self._load_one_friend, 0)

    def load_friends(self):
        try:
            r = self.api_get("https://api.tiantiantiaosheng.com/api2/sports_island/friends/simple?contains_farm=1")
            if r.status_code == 200 and r.json().get("code") == 0:
                self.friends = r.json()["data"]["friend_list"]
                # 一次性插入昵称行（不删除）
                for f in self.friends:
                    self.tree.insert("", "end", iid=f["user_id"],
                                     values=(f["nick_name"], "—", "—", "—", "加载中…"))
            else:
                log(self.log_box, f"好友列表：{r.status_code} - {r.json().get('msg','')}")
        except Exception as e:
            log(self.log_box, str(e))

    def _load_one_friend(self, idx):
        if idx >= len(self.friends):
            return
        friend = self.friends[idx]
        uid = friend["user_id"]
        nick = friend["nick_name"]
        try:
            resp = self.api_get(f"https://api.tiantiantiaosheng.com/api2/sports_island/farm/farm_info?host_user_id={uid}")
            if resp.status_code == 200 and resp.json().get("code") == 0:
                farm = resp.json()["data"]
                self.loaded[uid] = farm
                self._update_row(nick, farm)
        except Exception:
            pass
        self.after(250, self._load_one_friend, idx + 1)

    def _on_search(self, *_):
        keyword = self.search_var.get().strip().lower()
        for item in self.tree.get_children():
            self.tree.item(item, tags=())
        if not keyword:
            return
        for item in self.tree.get_children():
            nick = str(self.tree.item(item, "values")[0]).lower()
            if keyword in nick:
                if item in self.tree.selection():
                    self.tree.item(item, tags=("yellow",))
                else:
                    self.tree.item(item, tags=("blue",))

    def _refresh_friend(self, uid, nick):
        try:
            resp = self.api_get(
                f"https://api.tiantiantiaosheng.com/api2/sports_island/farm/farm_info?host_user_id={uid}")
            if resp.status_code == 200 and resp.json().get("code") == 0:
                self.loaded[uid] = resp.json()["data"]
                self._update_row(nick, self.loaded[uid])
        except Exception:
            pass

    def show_friend_detail(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择一个好友")
            return
        item = selected_items[0]
        nick = self.tree.item(item, "values")[0]
        uid = next(f["user_id"] for f in self.friends if f["nick_name"] == nick)
        farm = self.loaded.get(uid)
        if not farm:
            messagebox.showinfo("提示", "农场信息尚未加载完成，请稍候")
            return
        detail = tk.Toplevel(self)
        detail.title(f"{nick} 的农场")
        detail.geometry("720x300")
        tree = ttk.Treeview(
            detail,
            columns=("plot", "crop", "mature", "water", "wet", "stolen", "pray", "fert"),
            show="headings")
        heads = ("地块", "作物", "成熟状态", "最后浇水", "水分维持", "被偷次数", "祈福状态", "肥料")
        for c, h in zip(tree["columns"], heads):
            tree.heading(c, text=h)
            tree.column(c, width=90, anchor="center")
        tree.pack(fill="both", expand=True)
        now = int(time.time())
        for l in farm.get("farmland_info") or []:
            crop_id = l.get("crop_id")
            crop_name = "空地" if not crop_id else self.crop_map.get(str(crop_id), f"未知({crop_id})")
            mature = "空地" if not crop_id else ("已熟" if l.get("finish_ts", 0) <= now else "未熟")
            water = datetime.fromtimestamp(l.get("last_watering_ts", 0)).strftime('%m-%d %H:%M') if l.get("last_watering_ts") else "无"
            wet = datetime.fromtimestamp(l.get("finish_wet_ts", 0)).strftime('%m-%d %H:%M') if l.get("finish_wet_ts") else "无"
            fert = ", ".join([self.fertilizer_client.get_name(f) for f in (l.get("fertilizer_list") or [])]) or "无"
            tree.insert("", "end", values=(
                l["farmland_index"] + 1, crop_name, mature, water, wet,
                len(l.get("taken_away_users") or []),
                "成功" if l.get("pray_success") else "失败",
                fert))


    def _update_row(self, nick, farm):
        lands = farm.get("farmland_info") or []
        now = int(time.time())
        states = []
        for l in lands:
            states.append("空地" if not l.get("crop_id") else ("已熟" if l.get("finish_ts", 0) <= now else "未熟"))
        state_str = ";".join(states)
        for item in self.tree.get_children():
            if self.tree.item(item)["values"][0] == nick:
                self.tree.item(item, values=(nick,
                                             farm.get("farm_level", 0),
                                             farm.get("farm_exp", 0),
                                             farm.get("veg_stall_level", 0),
                                             state_str))
                break

    def _bg_loader(self):
        for friend in self.friends:
            uid = friend["user_id"]
            nick = friend["nick_name"]
            try:
                resp = self.api_get(
                    f"https://api.tiantiantiaosheng.com/api2/sports_island/farm/farm_info?host_user_id={uid}")
                if resp.status_code == 200 and resp.json().get("code") == 0:
                    farm = resp.json()["data"]
                    lands = farm.get("farmland_info", [])
                    now = int(time.time())
                    crops, matures, waters, wets, stolens, prays, ferts = [], [], [], [], [], [], []
                    for land in lands:
                        crop_name = self.crop_map.get(str(land["crop_id"]), f"未知({land['crop_id']})")
                        matures.append("已熟" if land.get("finish_ts", 0) <= now else "未熟")
                        crops.append(crop_name)
                        waters.append(datetime.fromtimestamp(land.get("last_watering_ts", 0)).strftime('%m-%d %H:%M'))
                        wets.append(datetime.fromtimestamp(land.get("finish_wet_ts", 0)).strftime('%m-%d %H:%M'))
                        stolens.append(str(land.get("taken_away_count", 0)))
                        prays.append("成功" if land.get("pray_success") else "失败")
                        ferts.append(",".join([self.fertilizer_client.get_name(f) for f in land.get("fertilizer_list", [])]) or "无")
                    for item in self.tree.get_children():
                        if self.tree.item(item)["values"][0] == nick:
                            self.tree.item(item, values=(
                                nick, farm.get("farm_level", 0), farm.get("farm_exp", 0),
                                farm.get("veg_stall_level", 0), ";".join(matures),
                                ";".join(crops), ";".join(waters), ";".join(wets),
                                ";".join(stolens), ";".join(prays), ";".join(ferts)))
                            self.loaded[uid] = farm
                            break
            except Exception:
                pass
            time.sleep(0.20)

    def start_steal(self):
        if self.running:
            return
        sel_items = self.tree.selection()
        if not sel_items:
            self.targets = self.friends[:]
        else:
            sel_uids = {self.tree.item(iid)["values"][0] for iid in sel_items}
            self.targets = [f for f in self.friends if f["nick_name"] in sel_uids]
        if not self.targets:
            messagebox.showinfo("提示", "没有可偷的好友")
            return
        self.running = True
        self.current_batch = 0
        threading.Thread(target=self._do_steal, daemon=True).start()

    def toggle_pause(self):
        self.running = not self.running

    def _do_steal(self):
        total = 0
        while self.current_batch * self.batch_size < len(self.targets) and self.running:
            batch = self.targets[self.current_batch * self.batch_size:(self.current_batch + 1) * self.batch_size]
            for friend in batch:
                if not self.running:
                    return
                uid = friend["user_id"]
                nick = friend["nick_name"]
                if uid not in self.loaded:
                    continue
                farm = self.loaded[uid]
                lands = farm.get("farmland_info", [])
                now = int(time.time())
                for land in lands:
                    if land.get("crop_id") == 0:
                        continue
                    if land.get("finish_ts", 0) <= now:
                        payload = {
                            "farmland_index": land["farmland_index"],
                            "host_user_id": uid,
                            "crop_id": land["crop_id"],
                            "version": land["version"]
                        }
                        try:
                            resp = self.api_post("https://api.tiantiantiaosheng.com/api2/sports_island/farm/steal_veg", payload)
                            code = resp.json().get("code")
                            msg = resp.json().get("msg", "")
                            if code == 0:
                                total += 1
                                log(self.log_box, f"偷 {nick} 地块 {land['farmland_index'] + 1}: 成功")
                            elif "抢菜失败，请稍后再试" in msg:
                                time.sleep(0.5)
                                resp = self.api_post("https://api.tiantiantiaosheng.com/api2/sports_island/farm/steal_veg", payload)
                                code = resp.json().get("code")
                                if code == 0:
                                    total += 1
                                    log(self.log_box, f"偷 {nick} 地块 {land['farmland_index'] + 1}: 重试成功")
                                else:
                                    log(self.log_box, f"偷 {nick} 地块 {land['farmland_index'] + 1}: 重试失败 - {msg}")
                            elif "该地块没有可拿取的菜了" in msg:
                                log(self.log_box, f"跳过 {nick} 地块 {land['farmland_index'] + 1}: {msg}")
                            else:
                                log(self.log_box, f"偷 {nick} 地块 {land['farmland_index'] + 1}: {msg}")
                        except Exception as e:
                            log(self.log_box, str(e))
                        time.sleep(0.25)
                        if not self.running:
                            return
                threading.Thread(target=self._refresh_friend, args=(uid, nick), daemon=True).start()
            self.current_batch += 1
        self.running = False
        self.run_on_main(messagebox.showinfo, "完成", f"共偷菜 {total} 次")

    def run_on_main(self, func, *args, **kw):
        """把函数放到主线程执行，防止弹窗报错"""
        self.root.after(0, lambda: func(*args, **kw))

# ===== 5. 主界面 =====
class FarmBotUI:
    def __init__(self, root):
        self.root = root
        self.root.title("农场自动化工具")
        self.root.geometry("1200x700")

        self.accounts = ACCOUNT_MAP.copy()
        self.temp_users = {}
        self.current_auth = None
        self.current_user_id = None
        self.farmland_data = []
        self.nick_cache = {}
        self.crop_map = CROP_MAP

        self.fertilizer_client = FertilizerClient()
        self.build_ui()
        self.populate_user_combo()

        threading.Thread(target=self.preload_nicknames, daemon=True).start()
        threading.Thread(target=self._preload_all_friends, daemon=True).start()

        self.friend_cache = {}

    # 预加载好友线程
    def _preload_all_friends(self):
        try:
            resp = self.api_get("https://api.tiantiantiaosheng.com/api2/sports_island/friends/simple?contains_farm=1")
            if resp.status_code == 200 and resp.json().get("code") == 0:
                friends = resp.json()["data"]["friend_list"]
                log(self.log_box, f"共 {len(friends)} 位好友，开始后台刷新...")
                for f in friends:
                    uid = f["user_id"]
                    nick = f["nick_name"]
                    try:
                        r = self.api_get(f"https://api.tiantiantiaosheng.com/api2/sports_island/farm/farm_info?host_user_id={uid}")
                        if r.status_code == 200 and r.json().get("code") == 0:
                            self.friend_cache[uid] = r.json()["data"]
                    except Exception as e:
                        log(self.log_box, f"[后台] 刷新 {nick} 失败：{e}")
                    time.sleep(0.25)
                log(self.log_box, "后台好友菜园刷新完成")
        except Exception as e:
            log(self.log_box, f"获取好友列表失败：{e}")

    def build_ui(self):
        self.info_frame = ttk.Frame(self.root)
        self.info_frame.pack(fill='x', padx=10, pady=(10, 0))
        self.info_lbl = ttk.Label(self.info_frame, font=('', 10))
        self.info_lbl.pack(side='left')

        top = ttk.Frame(self.root)
        top.pack(fill='x', padx=10, pady=(5, 10))

        ttk.Label(top, text="选择账号：").grid(row=0, column=0)
        self.user_combo = ttk.Combobox(top, width=20, state="readonly")
        self.user_combo.grid(row=0, column=1, padx=5)
        self.user_combo.bind("<<ComboboxSelected>>", self.on_user_change)

        ttk.Button(top, text="添加临时账号", command=self.add_temp_user).grid(row=0, column=2, padx=5)
        ttk.Button(top, text="刷新农场", command=self.refresh_farm).grid(row=0, column=3, padx=5)
        ttk.Button(top, text="一键收获", command=self.auto_harvest).grid(row=0, column=4, padx=5)
        ttk.Button(top, text="购买肥料",command=lambda: self.fertilizer_client.buy_dialog(self.root, self.log_box)).grid(row=0, column=5, padx=5)
        ttk.Button(top, text="自动浇水", command=self.auto_watering).grid(row=0, column=6, padx=5)
        ttk.Button(top, text="偷菜", command=lambda: StealDialog(
            self.root, self.api_get, self.api_post, self.log_box,
            self.crop_map, self.fertilizer_client, self.friend_cache
        )).grid(row=0, column=7, padx=5)
        ttk.Button(top, text="自动施肥", command=self.auto_fertilize).grid(row=0, column=8, padx=5)
        ttk.Button(top, text="清空农场", command=self.clear_farm_warning).grid(row=0, column=9, padx=5)

        tree_frame = ttk.Frame(self.root)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=5)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("地块", "作物", "等级", "状态", "成熟时间", "最后浇水时间", "水分维持时间", "被偷人数", "祈福人数", "肥料"),
            show="headings")
        heads = ("地块", "作物", "等级", "状态", "成熟时间", "最后浇水时间", "水分维持时间", "被偷人数", "祈福人数", "肥料")
        for col, h in zip(self.tree["columns"], heads):
            self.tree.heading(col, text=h)
            self.tree.column(col, anchor="center", width=100, stretch=True)

        scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<Motion>", self.on_tree_hover)
        self.tree.bind("<Leave>", self.on_tree_leave)

        log_frame = ttk.LabelFrame(self.root, text="日志")
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)
        self.log_box = scrolledtext.ScrolledText(log_frame, height=8, state='disabled')
        self.log_box.pack(fill='both', expand=True, padx=5, pady=5)

    def populate_user_combo(self):
        users = list(self.accounts) + list(self.temp_users)
        self.user_combo["values"] = users
        if users:
            self.user_combo.current(0)
            self.on_user_change()

    def preload_nicknames(self):
        if not self.current_user_id:
            return
        try:
            resp = self.api_get("https://api.tiantiantiaosheng.com/api2/sports_island/friends/simple?contains_farm=1")
            if resp.status_code == 200 and resp.json().get("code") == 0:
                for f in resp.json()["data"]["friend_list"]:
                    uid = f["user_id"]
                    nick = f["nick_name"]
                    self.nick_cache[uid] = nick
            log(self.log_box, "好友昵称缓存完成")
        except Exception as e:
            log(self.log_box, f"预加载昵称失败：{e}")

    def add_temp_user(self):
        auth = simpledialog.askstring("添加临时用户", "请输入 Authorization：", parent=self.root)
        if not auth:
            return
        try:
            resp = requests.get(
                "https://api.tiantiantiaosheng.com/api/user/user_info",
                headers={**HEADERS, "Authorization": auth},
                timeout=10)
            if resp.status_code != 200 or resp.json().get("code") != 0:
                messagebox.showerror("错误", "Authorization 无效或网络异常")
                return
            info = resp.json()["data"]["user_info"]
            nick = info["nick_name"]
            uid = info["user_id"]
            key = f"{nick}(临时)"
            self.temp_users[key] = {"bearer": auth, "usid": uid}
            self.populate_user_combo()
            self.user_combo.set(key)
            self.on_user_change()
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def on_user_change(self, _=None):
        key = self.user_combo.get()
        if key in self.accounts:
            self.current_auth = self.accounts[key]["bearer"]
            self.current_user_id = self.accounts[key]["usid"]
        elif key in self.temp_users:
            self.current_auth = self.temp_users[key]["bearer"]
            self.current_user_id = self.temp_users[key]["usid"]
        else:
            return

        log(self.log_box, f"切换到用户：{key}")
        self.nick_cache.clear()
        self.fertilizer_client.auth = self.current_auth

        def load_and_refresh():
            self.fertilizer_client.load_or_refresh()
            self.root.after(0, self.refresh_farm)

        threading.Thread(target=load_and_refresh, daemon=True).start()

    # ===== 统一网络出口 =====
    def api_get(self, url):
        return requests.get(url, headers={**HEADERS, "Authorization": self.current_auth}, timeout=10)

    def api_post(self, url, payload):
        return requests.post(url, json=payload, headers={**HEADERS, "Authorization": self.current_auth}, timeout=10)

    def nickname_of(self, uid):
        return self.nick_cache.get(uid, uid[:8])

    # ===== 主线程与后台刷新工具 =====
    def run_on_main(self, func, *args, **kw):
        self.root.after(0, lambda: func(*args, **kw))

    def _refresh_farm_thread(self, callback=None):
        try:
            resp = self.api_get(
                f"https://api.tiantiantiaosheng.com/api2/sports_island/farm/farm_info?host_user_id={self.current_user_id}")
            log_msg = f"刷新农场：{resp.status_code} - {resp.json().get('msg','')}"
            if resp.status_code == 200 and resp.json().get("code") == 0:
                self.farmland_data = resp.json()["data"]["farmland_info"]
                info = resp.json()["data"]
                farm_lvl = info.get("farm_level", "—")
                farm_exp = info.get("farm_exp", "—")
                stall_lvl = info.get("veg_stall_level", "—")
                nick = info.get("nick_name", "—")
                self.root.after(0, lambda: self.info_lbl.config(
                    text=f"昵称：{nick}  |  农场等级：{farm_lvl}  |  农场经验值：{farm_exp}  |  蔬菜摊等级：{stall_lvl}"))
                self.root.after(0, self.fill_tree)
            else:
                self.root.after(0, lambda: messagebox.showerror("错误", resp.text))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        self.root.after(0, lambda: log(self.log_box, log_msg))
        if callback:
            self.root.after(0, callback)

    def _refresh_and_run(self, worker_thread_func):
        self._refresh_farm_thread(callback=lambda: threading.Thread(target=worker_thread_func, daemon=True).start())

    def refresh_farm(self):
        threading.Thread(target=self._refresh_farm_thread, daemon=True).start()

    def fill_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        now = int(time.time())
        lands = [l for l in (self.farmland_data or []) if l]
        for land in lands:
            crop_id = land.get("crop_id")
            if not crop_id:
                crop_name = "空地"
                mature = "空地"
            else:
                crop_name = self.crop_map.get(str(crop_id), f"未知({crop_id})")
                mature = "可收" if land.get("finish_ts", 0) <= now else "未熟"
            level_map = {0: "普通", 1: "丰收", 2: "大丰收"}
            level = level_map.get(land.get("harvest_state", 0), "未知")
            water = datetime.fromtimestamp(land.get("last_watering_ts", 0)).strftime('%m-%d %H:%M') if land.get("last_watering_ts") else "无"
            wet = datetime.fromtimestamp(land.get("finish_wet_ts", 0)).strftime('%m-%d %H:%M') if land.get("finish_wet_ts") else "无"
            finish_str = datetime.fromtimestamp(land.get("finish_ts", 0)).strftime('%m-%d %H:%M') if land.get("finish_ts") else "无"
            stolen_users = land.get("taken_away_users") or []
            pray_users = land.get("pray_users") or []
            stolen_nicks = [self.nickname_of(uid) for uid in stolen_users]
            pray_nicks = [self.nickname_of(uid) for uid in pray_users]
            fert_list = land.get("fertilizer_list") or []
            fert_names = [self.fertilizer_client.get_name(f) for f in fert_list]
            fert_str = ', '.join(fert_names) if fert_names else "无"
            item_id = self.tree.insert("", "end", values=(
                land.get("farmland_index", 0) + 1,
                crop_name,
                level,
                mature,
                finish_str,
                water,
                wet,
                len(stolen_nicks),
                len(pray_nicks),
                fert_str))
            self.tree.item(item_id, tags=(item_id,))
            # 计算状态并缓存
            if not crop_id:
                mature = "空地"
            else:
                mature = "可收" if land.get("finish_ts", 0) <= now else "未熟"
            land["_display_status"] = mature   # 缓存给收获线程使用

    def on_tree_hover(self, event):
        row_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row_id or col not in ("#8", "#9"):
            self.on_tree_leave()
            return
        index = int(self.tree.set(row_id, "地块")) - 1
        if index < 0 or index >= len(self.farmland_data):
            return
        land = self.farmland_data[index]
        if col == "#8":
            users = land.get("taken_away_users") or []
            title = "偷菜名单"
        else:
            users = land.get("pray_users") or []
            title = "祈福名单"
        nicks = [self.nickname_of(uid) for uid in users]
        text = f"{title}：{', '.join(nicks)}" if nicks else f"{title}：无"
        if not hasattr(self, "tooltip"):
            self.tooltip = None
        if self.tooltip:
            self.tooltip.hidetip()
        self.tooltip = Tooltip(self.tree)
        x = event.x_root + 10
        y = event.y_root + 10
        self.tooltip.showtip_at(text, x, y)

    def on_tree_leave(self, event=None):
        if hasattr(self, "tooltip") and self.tooltip:
            self.tooltip.hidetip()
            self.tooltip = None

    def _selected_or_all(self):
        if not self.farmland_data:
            messagebox.showwarning("提示", "请先刷新农场")
            return []
        selected = self.tree.selection()
        if not selected:
            return self.farmland_data
        indexes = [int(self.tree.set(item, "地块")) - 1 for item in selected]
        return [land for land in self.farmland_data if land["farmland_index"] in indexes]

    # ===== 功能入口（统一先刷新再执行） =====
    def auto_harvest(self):
        self._refresh_and_run(self._auto_harvest_thread)

    def _auto_harvest_thread(self):
        lands = self._selected_or_all()
        count = 0
        for land in lands:
            # 直接复用主窗口表格里的“状态”字段
            if land.get("_display_status") != "可收":
                continue
            payload = {
                "crop_id": land["crop_id"],
                "farmland_index": land["farmland_index"],
                "version": land["version"],
                "finish_guide": False
            }
            try:
                resp = self.api_post("https://api.tiantiantiaosheng.com/api2/sports_island/farm/harvest", payload)
                log(self.log_box, f"收获地块 {land['farmland_index']}：{resp.status_code} - {resp.json().get('msg','')}")
                if resp.json().get("code") == 0:
                    count += 1
            except Exception as e:
                log(self.log_box, str(e))
            time.sleep(0.25)
        self.run_on_main(messagebox.showinfo, "完成", f"共收获 {count} 块地")
        self.root.after(0, self.refresh_farm)

    def auto_watering(self):
        self._refresh_and_run(self._auto_watering_thread)

    def _auto_watering_thread(self):
        lands = self._selected_or_all()
        for land in lands:
            if land.get("crop_id") == 0:
                continue
            payload = {
                "farmland_index": land["farmland_index"],
                "crop_id": land["crop_id"],
                "version": land["version"],
                "finish_guide": False
            }
            try:
                resp = self.api_post("https://api.tiantiantiaosheng.com/api2/sports_island/farm/watering", payload)
                log(self.log_box, f"浇水地块 {land['farmland_index']}：{resp.status_code} - {resp.json().get('msg','')}")
            except Exception as e:
                log(self.log_box, str(e))
            time.sleep(0.25)
        self.run_on_main(messagebox.showinfo, "完成", "浇水完毕")
        self.root.after(0, self.refresh_farm)

    def auto_fertilize(self):
        self._refresh_and_run(self._auto_fertilize_thread)

    def _auto_fertilize_thread(self):
        lands = self._selected_or_all()
        self.fertilizer_client.load_or_refresh()
        if not self.fertilizer_client.products:
            self.run_on_main(messagebox.showinfo, "提示", "暂无可用肥料")
            return

        names = [f"{p['name']} ({p['original_price'] * 10}币)" for p in self.fertilizer_client.products]

        def ask_and_fert():
            selected = simpledialog.askinteger(
                "选择肥料",
                "请选择肥料编号（从1开始）：\n" + "\n".join([f"{i+1}. {n}" for i, n in enumerate(names)]),
                parent=self.root,
                minvalue=1,
                maxvalue=len(names))
            if not selected:
                return
            product = self.fertilizer_client.products[selected - 1]
            product_id = product["item_id"]
            count = 0
            for land in lands:
                if land.get("crop_id") == 0:
                    continue
                payload = {
                    "farmland_index": land["farmland_index"],
                    "crop_id": land["crop_id"],
                    "fertilizer_id": product_id,
                    "version": land["version"]
                }
                try:
                    resp = self.api_post(
                        "https://api.tiantiantiaosheng.com/api2/sports_island/farm/fertilize", payload)
                    log(self.log_box, f"施肥地块 {land['farmland_index']}：{resp.status_code} - {resp.json().get('msg','')}")
                    if resp.json().get("code") == 0:
                        count += 1
                except Exception as e:
                    log(self.log_box, str(e))
                time.sleep(0.25)
            self.run_on_main(messagebox.showinfo, "完成", f"共施肥 {count} 块地")
            self.root.after(0, self.refresh_farm)

        self.run_on_main(ask_and_fert)

    def clear_farm_warning(self):
        self._refresh_and_run(self._clear_farm_after_refresh)

    def _clear_farm_after_refresh(self):
        lands = self._selected_or_all()
        if not lands:
            self.run_on_main(messagebox.showwarning, "提示", "农场无地块可操作")
            return

        def confirm_clear():
            msg = "确定要清空选中的地块吗？此操作不可撤销！"
            top = tk.Toplevel(self.root)
            top.title("危险操作警告")
            top.geometry("400x150")
            top.transient(self.root)
            top.grab_set()
            tk.Label(top, text=msg, fg="red", font=("Arial", 12, "bold")).pack(pady=20)
            btn_frame = tk.Frame(top)
            btn_frame.pack()
            tk.Button(btn_frame, text="确认清空", fg="white", bg="red",
                      command=lambda: [top.destroy(), self._do_clear(lands)]).pack(side="left", padx=10)
            tk.Button(btn_frame, text="取消", command=top.destroy).pack(side="left", padx=10)

        self.run_on_main(confirm_clear)

    def _do_clear(self, lands):
        for land in lands:
            if land.get("crop_id") == 0:
                continue
            payload = {
                "remove_list": [{
                    "farmland_index": land["farmland_index"],
                    "crop_id": land["crop_id"],
                    "version": land["version"]
                }]
            }
            try:
                resp = self.api_post("https://api.tiantiantiaosheng.com/api2/sports_island/farm/remove", payload)
                log(self.log_box,
                    f"清空地块 {land['farmland_index'] + 1}：{resp.status_code} - {resp.json().get('msg', '')}")
            except Exception as e:
                log(self.log_box, str(e))
            time.sleep(0.3)
        self.run_on_main(messagebox.showinfo, "完成", "已执行清空操作")
        self.root.after(0, self.refresh_farm)

# ===== 6. 入口 =====
if __name__ == "__main__":
    root = tk.Tk()
    FarmBotUI(root)
    root.mainloop()