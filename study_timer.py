#!/usr/bin/env python3
"""Zoom Auto: в нужное время сам открывает Zoom-ссылку пары (Пн-Пт)."""
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
GRACE_MIN = 30  # если ноутбук включили позже начала, но не позже 30 мин, всё равно зайдёт

BG, CARD, FG, DIM, ACC, RED = "#0f0f10", "#1a1a1c", "#f2f2f2", "#7d7d85", "#4f8cff", "#e5575b"
FONT = ("Ubuntu", 11)
FONT_BIG = ("Ubuntu", 20, "bold")
DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DEFAULT_DAYS = [0, 1, 2, 3, 4]


def days_text(days):
    days = sorted(days)
    if days == DEFAULT_DAYS:
        return "Пн-Пт"
    if len(days) == 7:
        return "Каждый день"
    return " ".join(DAYS[i] for i in days)


def load():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(classes):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(classes, f, ensure_ascii=False, indent=2)


def open_link(link):
    if not link.startswith(("http://", "https://", "zoommtg://")):
        link = "https://" + link
    subprocess.Popen(["xdg-open", link], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zoom Auto")
        self.configure(bg=BG)
        self.geometry("460x640")
        self.minsize(460, 640)
        self.protocol("WM_DELETE_WINDOW", self.iconify)  # крестик сворачивает, а не закрывает

        self.classes = load()
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
        self.sub.pack(fill="x", padx=22, pady=(2, 14))

        self.list_frame = tk.Frame(self, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=22)

        form = tk.Frame(self, bg=BG)
        form.pack(fill="x", padx=22, pady=(8, 22))
        self.name_e = self.entry(form, "Предмет")
        self.time_e = self.entry(form, "Время  ЧЧ:ММ")
        self.link_e = self.entry(form, "Zoom ссылка")

        days_row = tk.Frame(form, bg=BG)
        days_row.pack(fill="x", pady=(8, 2))
        self.day_vars = []
        for i, d in enumerate(DAYS):
            v = tk.BooleanVar(value=i in DEFAULT_DAYS)
            self.day_vars.append(v)
            tk.Checkbutton(days_row, text=d, variable=v, indicatoron=False, bg=CARD, fg=DIM,
                           selectcolor=ACC, activebackground=CARD, activeforeground=FG, relief="flat",
                           bd=0, font=("Ubuntu", 10), cursor="hand2", width=4, pady=5
                           ).pack(side="left", expand=True, fill="x", padx=2)
        btn = tk.Button(form, text="Добавить", command=self.add, bg=ACC, fg="white", relief="flat",
                        activebackground=ACC, activeforeground="white", font=FONT, cursor="hand2", pady=6)
        btn.pack(fill="x", pady=(6, 0))

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

    def refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for i, c in enumerate(sorted(self.classes, key=lambda x: x["time"])):
            row = tk.Frame(self.list_frame, bg=CARD)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=c["time"], bg=CARD, fg=ACC, font=("Ubuntu", 13, "bold"), width=6).pack(side="left", padx=(8, 0), pady=10)
            tk.Label(row, text=c["name"], bg=CARD, fg=FG, font=FONT, anchor="w").pack(side="left", fill="x", expand=True)
            tk.Button(row, text="✕", command=lambda c=c: self.delete(c), bg=CARD, fg=DIM, relief="flat",
                      activebackground=CARD, activeforeground=RED, bd=0, cursor="hand2").pack(side="right", padx=8)
            tk.Button(row, text="▶", command=lambda c=c: open_link(c["link"]), bg=CARD, fg=DIM, relief="flat",
                      activebackground=CARD, activeforeground=ACC, bd=0, cursor="hand2").pack(side="right")
            tk.Label(row, text=days_text(c.get("days", DEFAULT_DAYS)), bg=CARD, fg=DIM,
                     font=("Ubuntu", 9)).pack(side="right", padx=6)
        self.update_status()

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
        days = [i for i, v in enumerate(self.day_vars) if v.get()]
        if not days:
            messagebox.showinfo("Zoom Auto", "Выбери хотя бы один день")
            return
        self.classes.append({"name": name, "time": t, "link": link, "days": days, "last": ""})
        save(self.classes)
        for e in (self.name_e, self.time_e, self.link_e):
            self.clear(e)
        self.focus()
        self.refresh()

    def delete(self, c):
        self.classes = [x for x in self.classes if x is not c]
        save(self.classes)
        self.refresh()

    # ---------- Автозаход ----------
    def check(self):
        now = datetime.datetime.now()
        if self.classes:
            self.classes = load()  # свежие данные (защита от двойного запуска)
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
