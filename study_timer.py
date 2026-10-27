#!/usr/bin/env python3
"""Study Timer — само открывает ссылки на пары по расписанию.

Фичи: защита от дублей, любые ссылки (Zoom/Meet/Teams/...), импорт/экспорт
JSON и CSV, тёмная/светлая тема, обновление из GitHub одной кнопкой.
Зависимости: только python3 и python3-tk (sudo apt install python3-tk).
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
import uuid
import webbrowser
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox
from urllib.parse import urlparse

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.expanduser("~"), ".config", "study-timer")
DATA_FILE = os.path.join(DATA_DIR, "schedule.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
os.makedirs(DATA_DIR, exist_ok=True)

FONT = "Ubuntu"
DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DEFAULT_DAYS = [0, 1, 2, 3, 4]
DEDUPE_MINUTES = 180      # одну и ту же ссылку не открываем чаще, чем раз в 3 часа
LATE_WINDOW_SEC = 300     # если приложение запустили с опозданием до 5 минут — всё равно откроем

THEMES = {
    "dark": dict(bg="#0e0f12", card="#16181d", line="#262a32", fg="#e8e9ec",
                 muted="#7c818c", accent="#7c9cff", accent_fg="#0e0f12",
                 ok="#5ad19a", danger="#ff6b6b", hover="#1d2027"),
    "light": dict(bg="#f5f6f8", card="#ffffff", line="#e3e5ea", fg="#14161a",
                  muted="#7a808c", accent="#3b5bdb", accent_fg="#ffffff",
                  ok="#1f9d6b", danger="#e03131", hover="#eceef2"),
}


# ───────────── утилиты ─────────────
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def normalize_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlparse(u)
    return u if p.netloc and "." in p.netloc else ""


def service_of(url):
    host = (urlparse(url).hostname or "").lower()
    if "zoom." in host:
        return "Zoom"
    if "meet.google" in host:
        return "Meet"
    if "teams." in host or "microsoft" in host:
        return "Teams"
    return host.replace("www.", "") or "Link"


def parse_time(s):
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*$", s or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def parse_days(s):
    out = []
    for tok in re.split(r"[\s,;]+", s or ""):
        for i, d in enumerate(DAYS):
            if tok.lower() == d.lower():
                out.append(i)
    return sorted(set(out)) or list(DEFAULT_DAYS)


def human_delta(sec):
    sec = int(sec)
    if sec < 60:
        return "меньше минуты"
    if sec < 3600:
        return f"{sec // 60} мин"
    if sec < 86400:
        return f"{sec // 3600} ч {sec % 3600 // 60} мин"
    return f"{sec // 86400} д {sec % 86400 // 3600} ч"


# ───────────── приложение ─────────────
class App:
    def __init__(self, root):
        self.root = root
        root.title("Study Timer")
        root.geometry("470x760")
        root.minsize(420, 640)
        self.items = load_json(DATA_FILE, {"items": []}).get("items", [])
        self.settings = load_json(DATA_FILE, {}).get("settings", {"theme": "dark"})
        self.state = load_json(STATE_FILE, {"opened": {}, "fired": {}})
        self.sel_days = set(DEFAULT_DAYS)
        self.status = tk.StringVar(value="Готово")
        self.build()
        self.tick()

    # ── хранение ──
    def save(self):
        save_json(DATA_FILE, {"settings": self.settings, "items": self.items})

    def save_state(self):
        save_json(STATE_FILE, self.state)

    # ── мелкие виджеты ──
    def btn(self, parent, text, cmd, kind="ghost", **kw):
        t = self.t
        if kind == "primary":
            bg, fg, hov = t["accent"], t["accent_fg"], t["accent"]
        else:
            bg, fg, hov = parent["bg"], t["muted"], t["hover"]
        b = tk.Label(parent, text=text, bg=bg, fg=fg, cursor="hand2",
                     font=(FONT, 10, "bold" if kind == "primary" else "normal"),
                     padx=12, pady=7 if kind == "primary" else 4, **kw)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=hov, fg=t["fg"] if kind != "primary" else fg))
        b.bind("<Leave>", lambda e: b.configure(bg=bg, fg=fg))
        return b

    def entry(self, parent, width=None):
        t = self.t
        e = tk.Entry(parent, relief="flat", bg=t["card"], fg=t["fg"],
                     insertbackground=t["fg"], font=(FONT, 11),
                     highlightthickness=1, highlightbackground=t["line"],
                     highlightcolor=t["accent"])
        if width:
            e.configure(width=width)
        return e

    def caption(self, parent, text):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=self.t["muted"],
                        font=(FONT, 8, "bold"))

    # ── интерфейс ──
    def build(self):
        t = self.t = THEMES[self.settings.get("theme", "dark")]
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=t["bg"])
        wrap = tk.Frame(self.root, bg=t["bg"])
        wrap.pack(fill="both", expand=True, padx=22, pady=18)

        head = tk.Frame(wrap, bg=t["bg"])
        head.pack(fill="x")
        tk.Label(head, text="Study Timer", font=(FONT, 18, "bold"),
                 bg=t["bg"], fg=t["fg"]).pack(side="left")
        self.btn(head, "☾" if self.settings.get("theme") == "dark" else "☀",
                 self.toggle_theme).pack(side="right")

        # ближайшая пара
        card = tk.Frame(wrap, bg=t["card"], highlightthickness=1, highlightbackground=t["line"])
        card.pack(fill="x", pady=(14, 14))
        tk.Label(card, text="БЛИЖАЙШАЯ ПАРА", font=(FONT, 8, "bold"),
                 bg=t["card"], fg=t["muted"]).pack(anchor="w", padx=16, pady=(12, 0))
        self.next_title = tk.Label(card, text="—", font=(FONT, 15, "bold"),
                                   bg=t["card"], fg=t["fg"], anchor="w")
        self.next_title.pack(fill="x", padx=16)
        self.next_sub = tk.Label(card, text="", font=(FONT, 10),
                                 bg=t["card"], fg=t["accent"], anchor="w")
        self.next_sub.pack(fill="x", padx=16, pady=(0, 12))

        # форма
        self.caption(wrap, "ПРЕДМЕТ").pack(anchor="w")
        self.e_subj = self.entry(wrap)
        self.e_subj.pack(fill="x", ipady=6, pady=(3, 10))

        row = tk.Frame(wrap, bg=t["bg"])
        row.pack(fill="x")
        c1 = tk.Frame(row, bg=t["bg"])
        c1.pack(side="left")
        self.caption(c1, "ВРЕМЯ").pack(anchor="w")
        self.e_time = self.entry(c1, width=7)
        self.e_time.pack(ipady=6, pady=(3, 0))
        c2 = tk.Frame(row, bg=t["bg"])
        c2.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.caption(c2, "ССЫЛКА (ZOOM, MEET, TEAMS, ЛЮБАЯ)").pack(anchor="w")
        self.e_link = self.entry(c2)
        self.e_link.pack(fill="x", ipady=6, pady=(3, 0))

        # дни недели
        dr = tk.Frame(wrap, bg=t["bg"])
        dr.pack(fill="x", pady=(12, 12))
        self.chips = []
        for i, d in enumerate(DAYS):
            c = tk.Label(dr, text=d, font=(FONT, 9, "bold"), cursor="hand2", width=4, pady=5)
            c.pack(side="left", expand=True, padx=2)
            c.bind("<Button-1>", lambda e, i=i: self.toggle_day(i))
            self.chips.append(c)
        self.paint_chips()

        self.btn(wrap, "Добавить пару", self.add, "primary").pack(fill="x")

        # список
        tk.Frame(wrap, bg=t["line"], height=1).pack(fill="x", pady=(18, 10))
        self.caption(wrap, "РАСПИСАНИЕ").pack(anchor="w", pady=(0, 6))
        box = tk.Frame(wrap, bg=t["bg"])
        box.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(box, bg=t["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.list_frame = tk.Frame(self.canvas, bg=t["bg"])
        win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        for ev, d in (("<Button-4>", -1), ("<Button-5>", 1)):
            self.canvas.bind_all(ev, lambda e, d=d: self.canvas.yview_scroll(d, "units"))
        self.render_list()

        # низ
        foot = tk.Frame(wrap, bg=t["bg"])
        foot.pack(fill="x", pady=(10, 0))
        self.btn(foot, "Импорт", self.do_import).pack(side="left")
        self.btn(foot, "Экспорт", self.do_export).pack(side="left")
        self.btn(foot, "Обновить", self.do_update).pack(side="left")
        tk.Label(wrap, textvariable=self.status, font=(FONT, 9), bg=t["bg"],
                 fg=t["muted"], anchor="w").pack(fill="x", pady=(6, 0))

    def paint_chips(self):
        t = self.t
        for i, c in enumerate(self.chips):
            on = i in self.sel_days
            c.configure(bg=t["accent"] if on else t["card"],
                        fg=t["accent_fg"] if on else t["muted"],
                        highlightthickness=1,
                        highlightbackground=t["accent"] if on else t["line"])

    def toggle_day(self, i):
        self.sel_days ^= {i}
        self.paint_chips()

    def render_list(self):
        t = self.t
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not self.items:
            tk.Label(self.list_frame, text="Пока пусто. Добавь первую пару выше.",
                     bg=t["bg"], fg=t["muted"], font=(FONT, 10)).pack(pady=16)
            return
        for it in sorted(self.items, key=lambda x: x["time"]):
            on = it.get("enabled", True)
            r = tk.Frame(self.list_frame, bg=t["card"], highlightthickness=1,
                         highlightbackground=t["line"])
            r.pack(fill="x", pady=3)
            dot = tk.Label(r, text="●", cursor="hand2", font=(FONT, 12),
                           bg=t["card"], fg=t["ok"] if on else t["line"])
            dot.pack(side="left", padx=(12, 4))
            dot.bind("<Button-1>", lambda e, i=it["id"]: self.toggle_item(i))
            mid = tk.Frame(r, bg=t["card"])
            mid.pack(side="left", fill="x", expand=True, pady=8)
            tk.Label(mid, text=it["subject"], font=(FONT, 11, "bold"), anchor="w",
                     bg=t["card"], fg=t["fg"] if on else t["muted"]).pack(fill="x")
            days = " ".join(DAYS[d] for d in it["days"])
            tk.Label(mid, text=f'{it["time"]}  ·  {days}  ·  {service_of(it["link"])}',
                     font=(FONT, 9), anchor="w", bg=t["card"], fg=t["muted"]).pack(fill="x")
            x = tk.Label(r, text="✕", cursor="hand2", font=(FONT, 10),
                         bg=t["card"], fg=t["muted"])
            x.pack(side="right", padx=12)
            x.bind("<Button-1>", lambda e, i=it["id"]: self.delete_item(i))
            x.bind("<Enter>", lambda e, w=x: w.configure(fg=t["danger"]))
            x.bind("<Leave>", lambda e, w=x: w.configure(fg=t["muted"]))

    # ── действия ──
    def toggle_theme(self):
        self.settings["theme"] = "light" if self.settings.get("theme") == "dark" else "dark"
        self.save()
        self.build()

    def add(self):
        subj = self.e_subj.get().strip()
        tm = parse_time(self.e_time.get())
        link = normalize_url(self.e_link.get())
        if not subj:
            return self.status.set("Укажи предмет")
        if not tm:
            return self.status.set("Время в формате ЧЧ:ММ, например 09:30")
        if not link:
            return self.status.set("Нужна корректная ссылка")
        self.items.append({"id": uuid.uuid4().hex[:8], "subject": subj, "time": tm,
                           "link": link, "days": sorted(self.sel_days) or list(DEFAULT_DAYS),
                           "enabled": True})
        self.save()
        for e in (self.e_subj, self.e_time, self.e_link):
            e.delete(0, "end")
        self.render_list()
        self.status.set(f"Добавлено: {subj}")

    def toggle_item(self, iid):
        for it in self.items:
            if it["id"] == iid:
                it["enabled"] = not it.get("enabled", True)
        self.save()
        self.render_list()

    def delete_item(self, iid):
        self.items = [i for i in self.items if i["id"] != iid]
        self.save()
        self.render_list()

    # ── таймер и защита от дублей ──
    def launch(self, it, now):
        url = it["link"]
        last = self.state["opened"].get(url)
        if last and now - datetime.fromisoformat(last) < timedelta(minutes=DEDUPE_MINUTES):
            self.status.set(f'{it["subject"]}: ссылка уже открывалась, пропускаю')
            return
        webbrowser.open(url)
        self.state["opened"][url] = now.isoformat()
        self.status.set(f'{now:%H:%M} открыл: {it["subject"]}')

    def tick(self):
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        for it in self.items:
            if not it.get("enabled", True) or now.weekday() not in it["days"]:
                continue
            h, m = map(int, it["time"].split(":"))
            start = now.replace(hour=h, minute=m, second=0, microsecond=0)
            late = (now - start).total_seconds()
            if 0 <= late < LATE_WINDOW_SEC and self.state["fired"].get(it["id"]) != today:
                self.state["fired"][it["id"]] = today
                self.launch(it, now)
                self.prune_state(now)
                self.save_state()
        self.refresh_next(now)
        self.root.after(1000, self.tick)

    def prune_state(self, now):
        self.state["opened"] = {u: ts for u, ts in self.state["opened"].items()
                                if now - datetime.fromisoformat(ts) < timedelta(days=2)}
        ids = {i["id"] for i in self.items}
        self.state["fired"] = {k: v for k, v in self.state["fired"].items() if k in ids}

    def next_lesson(self, now):
        best = None
        for it in self.items:
            if not it.get("enabled", True):
                continue
            h, m = map(int, it["time"].split(":"))
            for add in range(8):
                d = now + timedelta(days=add)
                if d.weekday() in it["days"]:
                    dt = d.replace(hour=h, minute=m, second=0, microsecond=0)
                    if dt >= now:
                        if best is None or dt < best[0]:
                            best = (dt, it)
                        break
        return best

    def refresh_next(self, now):
        nxt = self.next_lesson(now)
        if nxt:
            dt, it = nxt
            self.next_title.configure(text=it["subject"])
            self.next_sub.configure(text=f'через {human_delta((dt - now).total_seconds())}  ·  '
                                         f'{DAYS[dt.weekday()]} {it["time"]}')
        else:
            self.next_title.configure(text="Пар нет")
            self.next_sub.configure(text="Добавь расписание")

    # ── импорт / экспорт ──
    def do_export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile="schedule",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")])
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["subject", "time", "link", "days"])
                    for it in self.items:
                        w.writerow([it["subject"], it["time"], it["link"],
                                    " ".join(DAYS[d] for d in it["days"])])
            else:
                save_json(path, {"items": self.items})
            self.status.set(f"Экспортировано: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Экспорт", str(e))

    def do_import(self):
        path = filedialog.askopenfilename(filetypes=[("JSON / CSV", "*.json *.csv")])
        if not path:
            return
        try:
            rows = []
            if path.lower().endswith(".csv"):
                with open(path, newline="", encoding="utf-8-sig") as f:
                    for r in csv.DictReader(f):
                        rows.append({"subject": r.get("subject"), "time": r.get("time"),
                                     "link": r.get("link"), "days": parse_days(r.get("days"))})
            else:
                data = load_json(path, None)
                data = data.get("items", []) if isinstance(data, dict) else data
                for r in data or []:
                    rows.append({"subject": r.get("subject"), "time": r.get("time"),
                                 "link": r.get("link"), "days": r.get("days") or DEFAULT_DAYS,
                                 "enabled": r.get("enabled", True)})
            have = {(i["subject"], i["time"], i["link"]) for i in self.items}
            added = skipped = 0
            for r in rows:
                subj = (r["subject"] or "").strip()
                tm, link = parse_time(r["time"]), normalize_url(r["link"])
                if not (subj and tm and link) or (subj, tm, link) in have:
                    skipped += 1
                    continue
                have.add((subj, tm, link))
                self.items.append({"id": uuid.uuid4().hex[:8], "subject": subj, "time": tm,
                                   "link": link, "days": sorted(set(r["days"])),
                                   "enabled": r.get("enabled", True)})
                added += 1
            self.save()
            self.render_list()
            self.status.set(f"Импорт: добавлено {added}, пропущено {skipped}")
        except Exception as e:
            messagebox.showerror("Импорт", str(e))

    # ── обновление из GitHub ──
    def do_update(self):
        self.status.set("Проверяю обновления…")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        def run(*args):
            return subprocess.run(["git", "-C", APP_DIR, *args], capture_output=True,
                                  text=True, timeout=60)
        try:
            top = run("rev-parse", "--show-toplevel")
            if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(APP_DIR):
                return self.root.after(0, lambda: messagebox.showwarning(
                    "Обновление", "Папка приложения не является отдельным git-репозиторием. "
                                  "Пропускаю, чтобы не затронуть другие проекты."))
            r = run("pull", "--ff-only")
            out = (r.stdout + r.stderr).strip()
            if r.returncode != 0:
                return self.root.after(0, lambda: (self.status.set("Ошибка обновления"),
                                                   messagebox.showerror("Обновление", out)))
            if "up to date" in out.lower() or "уже актуально" in out.lower():
                return self.root.after(0, lambda: self.status.set("Уже последняя версия"))
            self.root.after(0, self._ask_restart)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Обновление", str(e)))

    def _ask_restart(self):
        if messagebox.askyesno("Обновление", "Новая версия загружена. Перезапустить приложение?"):
            os.execv(sys.executable, [sys.executable] + sys.argv)
        self.status.set("Обновлено, перезапусти приложение")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
