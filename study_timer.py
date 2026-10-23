#!/usr/bin/env python3
"""Zoom Auto: в нужное время сам открывает Zoom-ссылку пары."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

CONFIG_DIR = os.path.expanduser("~/.config/study-timer")
CONFIG = os.path.join(CONFIG_DIR, "classes.json")
BACKUP = CONFIG + ".bak"          # автоматическая копия перед каждым сохранением
LINKS_TXT = os.path.join(CONFIG_DIR, "links.txt")  # все пары и ссылки обычным текстом
GRACE_MIN = 30  # если ноутбук включили позже начала, но не позже 30 мин, всё равно зайдёт

BG, CARD, FG, DIM, ACC, RED = "#0f0f10", "#1a1a1c", "#f2f2f2", "#7d7d85", "#4f8cff", "#e5575b"
FONT = ("Ubuntu", 11)
FONT_BIG = ("Ubuntu", 20, "bold")
DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DAYS_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DEFAULT_DAYS = [0, 1, 2, 3, 4]


def days_text(days):
    days = sorted(days)
    if days == DEFAULT_DAYS:
        return "Пн-Пт"
    if len(days) == 7:
        return "Каждый день"
    return " ".join(DAYS[i] for i in days)


def _read(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("bad format")
    return data


def load():
    """Читает пары. Если файл повреждён, берёт копию и не теряет ссылки."""
    if not os.path.exists(CONFIG):
        try:
            return _read(BACKUP)
        except (OSError, ValueError):
            return []
    try:
        return _read(CONFIG)
    except (OSError, ValueError):
        try:
            shutil.copy(CONFIG, CONFIG + ".corrupt")
        except OSError:
            pass
        try:
            return _read(BACKUP)
        except (OSError, ValueError):
            return []


def save(classes):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:  # копия предыдущей версии, только если она целая
        _read(CONFIG)
        shutil.copy(CONFIG, BACKUP)
    except (OSError, ValueError):
        pass
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(classes, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG)
    try:  # текстовый список для себя
        with open(LINKS_TXT, "w", encoding="utf-8") as f:
            for c in sorted(classes, key=lambda x: x["time"]):
                f.write(f"{c['time']}  {c['name']}  ({days_text(c.get('days', DEFAULT_DAYS))})\n{c['link']}\n\n")
    except OSError:
        pass


def open_link(link):
    if not link.startswith(("http://", "https://", "zoommtg://")):
        link = "https://" + link
    subprocess.Popen(["xdg-open", link], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def short(text, n=44):
    return text if len(text) <= n else text[: n - 1] + "…"


def same(a, b):
    return (a["name"], a["time"], a["link"]) == (b["name"], b["time"], b["link"])


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zoom Auto")
        self.configure(bg=BG)
        self.geometry("480x760")
        self.minsize(480, 640)
        self.protocol("WM_DELETE_WINDOW", self.iconify)  # крестик сворачивает, а не закрывает

        self.classes = load()
        self.shown_day = datetime.date.today()
        self.day_on = [i in DEFAULT_DAYS for i in range(7)]
        self.build()
        self.refresh()
        self.check()
        if "--hidden" in sys.argv:
            self.after(300, self.iconify)

    # ---------- UI ----------
    def build(self):
        self.status = tk.Label(self, text="", bg=BG, fg=FG, font=FONT_BIG, anchor="w", justify="left")
        self.status.pack(fill="x", padx=22, pady=(22, 0))
        self.sub = tk.Label(self, text="", bg=BG, fg=DIM, font=FONT, anchor="w")
        self.sub.pack(fill="x", padx=22, pady=(2, 8))

        # форма снизу (создаём раньше списка, чтобы её всегда было видно)
        form = tk.Frame(self, bg=BG)
        form.pack(side="bottom", fill="x", padx=22, pady=(8, 22))
        self.name_e = self.entry(form, "Предмет")
        self.time_e = self.entry(form, "Время  ЧЧ:ММ")
        self.link_e = self.entry(form, "Zoom ссылка")

        days_row = tk.Frame(form, bg=BG)
        days_row.pack(fill="x", pady=(8, 2))
        self.day_btns = []
        for i, d in enumerate(DAYS):
            b = tk.Label(days_row, text=d, font=("Ubuntu", 10, "bold"), cursor="hand2", pady=7)
            b.pack(side="left", expand=True, fill="x", padx=2)
            b.bind("<Button-1>", lambda e, i=i: self.toggle_day(i))
            self.day_btns.append(b)
        self.paint_days()

        tk.Button(form, text="Добавить", command=self.add, bg=ACC, fg="white", relief="flat",
                  activebackground=ACC, activeforeground="white", font=FONT, cursor="hand2", pady=6
                  ).pack(fill="x", pady=(8, 0))

        # прокручиваемый список по дням
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=22)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, height=200)
        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.pack(fill="both", expand=True)
        self.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

    def entry(self, parent, placeholder):
        e = tk.Entry(parent, bg=CARD, fg=DIM, insertbackground=FG, relief="flat", font=FONT,
                     highlightthickness=1, highlightbackground=CARD, highlightcolor=ACC)
        e.insert(0, placeholder)
        e.placeholder = placeholder
        e.bind("<FocusIn>", self._focus_in)
        e.bind("<FocusOut>", self._focus_out)
        e.pack(fill="x", pady=3, ipady=6)
        return e

    @staticmethod
    def _focus_in(ev):
        e = ev.widget
        if e.get() == e.placeholder and e.cget("fg") == DIM:
            e.delete(0, "end")
            e.config(fg=FG)

    @staticmethod
    def _focus_out(ev):
        e = ev.widget
        if not e.get():
            e.insert(0, e.placeholder)
            e.config(fg=DIM)

    def value(self, e):
        return "" if e.cget("fg") == DIM else e.get().strip()

    def clear(self, e):
        e.delete(0, "end")
        e.insert(0, e.placeholder)
        e.config(fg=DIM)

    def toggle_day(self, i):
        self.day_on[i] = not self.day_on[i]
        self.paint_days()

    def paint_days(self):
        for b, on in zip(self.day_btns, self.day_on):
            b.config(bg=ACC if on else CARD, fg="white" if on else DIM)

    def refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        today = datetime.date.today().weekday()
        shown = False
        for d in range(7):
            items = sorted((c for c in self.classes if d in c.get("days", DEFAULT_DAYS)), key=lambda x: x["time"])
            if not items:
                continue
            shown = True
            title = DAYS_FULL[d] + ("  ·  сегодня" if d == today else "")
            tk.Label(self.list_frame, text=title, bg=BG, fg=ACC if d == today else DIM,
                     font=("Ubuntu", 10, "bold"), anchor="w").pack(fill="x", pady=(12, 3))
            for c in items:
                self.row(c, d)
        if not shown:
            tk.Label(self.list_frame, text="Пар пока нет", bg=BG, fg=DIM, font=FONT).pack(pady=20)
        self.update_status()

    def row(self, c, d):
        row = tk.Frame(self.list_frame, bg=CARD)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=c["time"], bg=CARD, fg=ACC, font=("Ubuntu", 13, "bold"), width=6).pack(side="left", padx=(8, 0), pady=8)
        tk.Button(row, text="✕", command=lambda: self.remove(c, d), bg=CARD, fg=DIM, relief="flat",
                  activebackground=CARD, activeforeground=RED, bd=0, cursor="hand2").pack(side="right", padx=8)
        tk.Button(row, text="▶", command=lambda: open_link(c["link"]), bg=CARD, fg=DIM, relief="flat",
                  activebackground=CARD, activeforeground=ACC, bd=0, cursor="hand2").pack(side="right")
        info = tk.Frame(row, bg=CARD)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=c["name"], bg=CARD, fg=FG, font=FONT, anchor="w").pack(fill="x")
        tk.Label(info, text=short(c["link"]), bg=CARD, fg=DIM, font=("Ubuntu", 8), anchor="w").pack(fill="x")

    def update_status(self):
        now = datetime.datetime.now()
        today = [c for c in self.classes if now.weekday() in c.get("days", DEFAULT_DAYS)]
        upcoming = sorted((c for c in today if c["time"] > now.strftime("%H:%M")), key=lambda x: x["time"])
        if upcoming:
            n = upcoming[0]
            self.status.config(text=f"{n['time']}  {n['name']}")
            self.sub.config(text="Следующая пара. Зайду сам")
        elif not self.classes:
            self.status.config(text="Пока пусто")
            self.sub.config(text="Добавь первую пару ниже")
        elif not today:
            self.status.config(text="Сегодня пар нет")
            self.sub.config(text="Отдыхай")
        else:
            self.status.config(text="На сегодня всё")
            self.sub.config(text="Пар больше нет")

    # ---------- Действия ----------
    def add(self):
        name, t, link = self.value(self.name_e), self.value(self.time_e), self.value(self.link_e)
        if not (name and t and link):
            messagebox.showinfo("Zoom Auto", "Заполни предмет, время и ссылку")
            return
        try:
            t = datetime.datetime.strptime(t, "%H:%M").strftime("%H:%M")
        except ValueError:
            messagebox.showerror("Zoom Auto", "Время нужно в формате ЧЧ:ММ, например 09:00")
            return
        days = [i for i, on in enumerate(self.day_on) if on]
        if not days:
            messagebox.showinfo("Zoom Auto", "Выбери хотя бы один день")
            return
        self.classes.append({"name": name, "time": t, "link": link, "days": days, "last": ""})
        save(self.classes)
        for e in (self.name_e, self.time_e, self.link_e):
            self.clear(e)
        self.focus()
        self.refresh()

    def remove(self, c, d):
        if not messagebox.askyesno("Zoom Auto", f"Убрать «{c['name']}» из дня: {DAYS_FULL[d]}?"):
            return
        for x in self.classes:
            if same(x, c):
                days = [i for i in x.get("days", DEFAULT_DAYS) if i != d]
                if days:
                    x["days"] = days
                else:
                    self.classes.remove(x)
                break
        save(self.classes)
        self.refresh()

    # ---------- Автозаход ----------
    def check(self):
        now = datetime.datetime.now()
        if now.date() != self.shown_day:
            self.shown_day = now.date()
            self.refresh()
        fresh = load()  # свежие данные (защита от двойного запуска)
        if fresh:
            self.classes = fresh
        today = now.date().isoformat()
        changed = False
        for c in self.classes:
            if now.weekday() not in c.get("days", DEFAULT_DAYS):
                continue
            h, m = map(int, c["time"].split(":"))
            start = now.replace(hour=h, minute=m, second=0, microsecond=0)
            delta = (now - start).total_seconds()
            if 0 <= delta <= GRACE_MIN * 60 and c.get("last") != today:
                c["last"] = today
                changed = True
                open_link(c["link"])
                if shutil.which("notify-send"):
                    subprocess.Popen(["notify-send", "Zoom Auto", f"Захожу на пару: {c['name']}"])
        if changed:
            save(self.classes)
        self.update_status()
        self.after(5000, self.check)


if __name__ == "__main__":
    App().mainloop()
