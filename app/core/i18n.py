"""Interface text in English and Russian.

Each key holds both languages side by side, so a missing translation is
obvious. Anything absent falls back to English rather than showing the key.
"""
from __future__ import annotations

LANGS = ("en", "ru")
DEFAULT = "en"

LANG_NAMES = {"en": "🇬🇧 English", "ru": "🇷🇺 Русский"}

DAYS_SHORT = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
}
DAYS_MINI = {
    "en": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
    "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
}
MONTHS_SHORT = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "ru": ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
}
MONTHS_FULL = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "ru": ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
           "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"],
}


def days_short(lang: str | None) -> list[str]:
    return DAYS_SHORT.get(lang or DEFAULT, DAYS_SHORT[DEFAULT])


def days_mini(lang: str | None) -> list[str]:
    return DAYS_MINI.get(lang or DEFAULT, DAYS_MINI[DEFAULT])


def month_short(lang: str | None, month: int) -> str:
    return MONTHS_SHORT.get(lang or DEFAULT, MONTHS_SHORT[DEFAULT])[month - 1]


def month_full(lang: str | None, month: int) -> str:
    return MONTHS_FULL.get(lang or DEFAULT, MONTHS_FULL[DEFAULT])[month - 1]


def pick_lang(telegram_code: str | None) -> str:
    """Telegram tells us the client's language; start there, let them change it."""
    if telegram_code and telegram_code.split("-")[0].lower() in LANGS:
        return telegram_code.split("-")[0].lower()
    return DEFAULT


STRINGS: dict[str, dict[str, str]] = {
    # ---------- bottom keyboard ----------
    "btn.today": {"en": "☀️ Today", "ru": "☀️ Сегодня"},
    "btn.new_task": {"en": "➕ New task", "ru": "➕ Новая задача"},
    "btn.tasks": {"en": "📝 Tasks", "ru": "📝 Задачи"},
    "btn.habits": {"en": "🔁 Habits", "ru": "🔁 Привычки"},
    "btn.more": {"en": "⚙️ More", "ru": "⚙️ Ещё"},
    "placeholder": {"en": "Type a task to add it…", "ru": "Напишите задачу, чтобы добавить…"},
    # ---------- shared ----------
    "back": {"en": "◀️ Back", "ru": "◀️ Назад"},
    "cancel": {"en": "✖️ Cancel", "ru": "✖️ Отмена"},
    "save": {"en": "💾 Save", "ru": "💾 Сохранить"},
    "saved": {"en": "Saved", "ru": "Сохранено"},
    "deleted": {"en": "Deleted", "ru": "Удалено"},
    "keep": {"en": "✖️ Keep it", "ru": "✖️ Оставить"},
    "yes_delete": {"en": "🗑 Yes, delete", "ru": "🗑 Да, удалить"},
    "cant_undo": {"en": "This can't be undone.", "ru": "Это нельзя отменить."},
    "gone.task": {"en": "This task no longer exists.", "ru": "Этой задачи больше нет."},
    "gone.habit": {"en": "This habit no longer exists.", "ru": "Этой привычки больше нет."},
    "need_text": {"en": "🤔 It needs some text.", "ru": "🤔 Нужен текст."},
    "expired": {"en": "That setup expired. Let's start again.",
                "ru": "Настройка устарела. Начнём заново."},
    "admins_only": {"en": "Admins only.", "ru": "Только для админа."},
    # ---------- welcome / language / zone ----------
    "welcome": {
        "en": ("👋 <b>Hi! I'm your personal assistant.</b>\n\n"
               "📝 <b>Tasks</b>: just type anything and I'll add it. Give it a due time "
               "and I'll remind you.\n"
               "🔁 <b>Habits</b>: daily check-ins with reminders and streaks.\n"
               "☀️ <b>Today</b>: everything for today on one screen.\n\n"
               "Use the buttons below 👇"),
        "ru": ("👋 <b>Привет! Я ваш личный помощник.</b>\n\n"
               "📝 <b>Задачи</b>: просто напишите что угодно — я добавлю. Поставьте срок, "
               "и я напомню.\n"
               "🔁 <b>Привычки</b>: ежедневные отметки с напоминаниями и сериями.\n"
               "☀️ <b>Сегодня</b>: все дела на сегодня на одном экране.\n\n"
               "Пользуйтесь кнопками ниже 👇"),
    },
    "lang.prompt": {"en": "🌐 <b>Choose your language</b>", "ru": "🌐 <b>Выберите язык</b>"},
    "lang.set": {"en": "🌐 Language set to <b>{name}</b>.", "ru": "🌐 Язык: <b>{name}</b>."},
    "lang.button": {"en": "🌐 Language", "ru": "🌐 Язык"},
    "zone.prompt": {
        "en": "🌍 <b>Which timezone are you in?</b>\n<i>Reminders and deadlines follow it.</i>",
        "ru": "🌍 <b>В каком вы часовом поясе?</b>\n<i>По нему считаются напоминания и сроки.</i>",
    },
    "zone.type": {"en": "⌨️ Type my timezone", "ru": "⌨️ Ввести вручную"},
    "zone.type_prompt": {
        "en": "⌨️ <b>Type your timezone</b>\n<i>Like</i> <code>Europe/Kyiv</code> <i>or</i> <code>Asia/Tokyo</code>",
        "ru": "⌨️ <b>Напишите часовой пояс</b>\n<i>Например</i> <code>Europe/Kyiv</code> <i>или</i> <code>Asia/Tokyo</code>",
    },
    "zone.unknown": {
        "en": "🤔 I don't know that one. Try <code>Europe/Kyiv</code>, or pick from the list.",
        "ru": "🤔 Не знаю такой. Попробуйте <code>Europe/Kyiv</code> или выберите из списка.",
    },
    "zone.set": {
        "en": "🌍 Timezone set to <b>{tz}</b>.\nEverything follows your local clock now.",
        "ru": "🌍 Часовой пояс: <b>{tz}</b>.\nТеперь всё считается по вашему времени.",
    },
    "full": {
        "en": "Sorry, this bot is private and currently full. Ask the owner to add you (id <code>{id}</code>).",
        "ru": "Извините, бот приватный и мест больше нет. Попросите владельца добавить вас (id <code>{id}</code>).",
    },
    "full.short": {"en": "This bot is full.", "ru": "В боте нет свободных мест."},
    # ---------- today ----------
    "today.title": {"en": "☀️ <b>Today</b> · {date}", "ru": "☀️ <b>Сегодня</b> · {date}"},
    "today.empty": {"en": "Nothing planned. Enjoy the day 🌿", "ru": "Планов нет. Хорошего дня 🌿"},
    "today.refresh": {"en": "🔄 Refresh", "ru": "🔄 Обновить"},
    "today.updated": {"en": "Updated", "ru": "Обновлено"},
    "not_text": {
        "en": "I can only read text 🙂 Type a task, or use the buttons below.",
        "ru": "Я понимаю только текст 🙂 Напишите задачу или воспользуйтесь кнопками.",
    },
    "no_commands": {
        "en": "I don't need commands 🙂 Use the buttons below, or just type a task.",
        "ru": "Команды не нужны 🙂 Пользуйтесь кнопками или просто напишите задачу.",
    },
    "stale_button": {
        "en": "This button is from an older version. Use the buttons below 👇",
        "ru": "Эта кнопка от старой версии. Пользуйтесь кнопками ниже 👇",
    },
    "broke": {"en": "Something broke. It's in the logs.", "ru": "Что-то сломалось. Подробности в логах."},
}


def t(lang: str | None, key: str, **kwargs) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang or DEFAULT) or entry[DEFAULT]
    return text.format(**kwargs) if kwargs else text


def all_variants(key: str) -> list[str]:
    """Every language's text for one key - used to match keyboard presses."""
    entry = STRINGS.get(key, {})
    return [entry[lang] for lang in LANGS if lang in entry]

STRINGS.update({
    "date.today": {"en": "today {time}", "ru": "сегодня {time}"},
    "date.tomorrow": {"en": "tomorrow {time}", "ru": "завтра {time}"},
    "date.min": {"en": "{n} min", "ru": "{n} мин"},
    "date.hour": {"en": "{n} h", "ru": "{n} ч"},
    "date.day": {"en": "{n} d", "ru": "{n} дн"},
    "date.in": {"en": "in {span}", "ru": "через {span}"},
    "date.ago": {"en": "{span} ago", "ru": "{span} назад"},
})

# ---------- tasks ----------
STRINGS.update({
    "t.new_prompt": {
        "en": "✍️ <b>What do you need to do?</b>\n\nJust type it and send. Several lines add several tasks.",
        "ru": "✍️ <b>Что нужно сделать?</b>\n\nПросто напишите и отправьте. Несколько строк — несколько задач.",
    },
    "t.title": {"en": "📝 <b>Tasks</b> · {n} open", "ru": "📝 <b>Задачи</b> · {n} открыто"},
    "t.empty": {"en": "📝 <b>Tasks</b>\n\nAll clear! 🎉\nType anything to add a task.",
                "ru": "📝 <b>Задачи</b>\n\nВсё чисто! 🎉\nНапишите что угодно — добавлю задачу."},
    "t.tap_hint": {"en": "<i>Tap a task to open it.</i>", "ru": "<i>Нажмите на задачу, чтобы открыть.</i>"},
    "t.sec.overdue": {"en": "⚠️ <b>Overdue</b>", "ru": "⚠️ <b>Просрочено</b>"},
    "t.sec.today": {"en": "☀️ <b>Today</b>", "ru": "☀️ <b>Сегодня</b>"},
    "t.sec.upcoming": {"en": "📅 <b>Upcoming</b>", "ru": "📅 <b>Предстоящее</b>"},
    "t.sec.anytime": {"en": "🗂 <b>Anytime</b>", "ru": "🗂 <b>Когда-нибудь</b>"},
    "t.new": {"en": "➕ New task", "ru": "➕ Новая задача"},
    "t.completed": {"en": "🗂 Completed", "ru": "🗂 Выполненные"},
    "t.undo": {"en": "↩️ Undo: {name}", "ru": "↩️ Вернуть: {name}"},
    "t.done": {"en": "✅ Done", "ru": "✅ Готово"},
    "t.due_btn": {"en": "⏰ Due time", "ru": "⏰ Срок"},
    "t.rename": {"en": "✏️ Rename", "ru": "✏️ Переименовать"},
    "t.delete": {"en": "🗑 Delete", "ru": "🗑 Удалить"},
    "t.all": {"en": "◀️ All tasks", "ru": "◀️ Все задачи"},
    "t.reopen": {"en": "↩️ Reopen", "ru": "↩️ Вернуть в работу"},
    "t.completed_at": {"en": "✅ Completed {when}", "ru": "✅ Выполнено {when}"},
    "t.due_line": {"en": "⏰ Due {when} · <i>{status}</i>", "ru": "⏰ Срок {when} · <i>{status}</i>"},
    "t.overdue": {"en": "⚠️ overdue", "ru": "⚠️ просрочено"},
    "t.no_due": {"en": "⏰ No due time", "ru": "⏰ Без срока"},
    "t.remind_line": {"en": "🔔 Reminder: {when}", "ru": "🔔 Напоминание: {when}"},
    "t.repeat_line": {"en": "🔁 Repeats: {how}", "ru": "🔁 Повтор: {how}"},
    "t.when_q": {"en": "⏰ When is <b>{name}</b> due?\n<i>I'll send you a reminder at that time.</i>",
                 "ru": "⏰ Когда нужно сделать <b>{name}</b>?\n<i>В это время придёт напоминание.</i>"},
    "t.pick_date": {"en": "📅 Pick a date", "ru": "📅 Выбрать дату"},
    "t.type_it": {"en": "⌨️ Type it", "ru": "⌨️ Ввести вручную"},
    "t.no_due_btn": {"en": "🚫 No due time", "ru": "🚫 Без срока"},
    "t.skip_due": {"en": "⏭ Skip, no due time", "ru": "⏭ Пропустить, без срока"},
    "t.added": {"en": "✅ <b>Task added</b>", "ru": "✅ <b>Задача добавлена</b>"},
    "t.added_many": {"en": "✅ <b>Added {n} tasks</b>", "ru": "✅ <b>Добавлено задач: {n}</b>"},
    "t.saved_note": {"en": "✅ <b>Saved</b>", "ru": "✅ <b>Сохранено</b>"},
    "t.due_removed": {"en": "🚫 <b>Due time removed</b>", "ru": "🚫 <b>Срок убран</b>"},
    "t.lead_q": {"en": "🔔 When should I remind you about <b>{name}</b>?\n<i>Deadline: {when}</i>",
                 "ru": "🔔 Когда напомнить про <b>{name}</b>?\n<i>Срок: {when}</i>"},
    "t.lead_set": {"en": "🔔 <b>Reminder set</b>", "ru": "🔔 <b>Напоминание настроено</b>"},
    "t.lead.0": {"en": "At the deadline", "ru": "В момент срока"},
    "t.lead.10": {"en": "10 min before", "ru": "За 10 минут"},
    "t.lead.60": {"en": "1 hour before", "ru": "За час"},
    "t.lead.180": {"en": "3 hours before", "ru": "За 3 часа"},
    "t.lead.1440": {"en": "1 day before", "ru": "За день"},
    "t.lead.2880": {"en": "2 days before", "ru": "За 2 дня"},
    "t.rep_q": {"en": "🔁 How often does <b>{name}</b> come back?\n<i>Completing it creates the next one automatically.</i>",
                "ru": "🔁 Как часто повторяется <b>{name}</b>?\n<i>После выполнения я создам следующую.</i>"},
    "t.rep_set": {"en": "🔁 <b>Repeat set</b>", "ru": "🔁 <b>Повтор настроен</b>"},
    "t.rep.": {"en": "Never", "ru": "Никогда"},
    "t.rep.daily": {"en": "Every day", "ru": "Каждый день"},
    "t.rep.weekly": {"en": "Every week", "ru": "Каждую неделю"},
    "t.rep.monthly": {"en": "Every month", "ru": "Каждый месяц"},
    "t.rep.yearly": {"en": "Every year", "ru": "Каждый год"},
    "t.hist.title": {"en": "🗂 <b>Completed</b> · last 10", "ru": "🗂 <b>Выполненные</b> · последние 10"},
    "t.hist.empty": {"en": "🗂 <b>Completed</b>\n\nNothing completed yet.",
                     "ru": "🗂 <b>Выполненные</b>\n\nПока ничего не выполнено."},
    "t.hist.hint": {"en": "<i>Tap one to bring it back.</i>", "ru": "<i>Нажмите, чтобы вернуть в список.</i>"},
    "t.hist.clear": {"en": "🧹 Clear all", "ru": "🧹 Очистить всё"},
    "t.hist.clear_q": {"en": "🧹 Clear all completed tasks?", "ru": "🧹 Удалить все выполненные задачи?"},
    "t.hist.cleared": {"en": "Cleared {n}", "ru": "Удалено: {n}"},
    "t.hist.back_on": {"en": "↩️ Back on your list", "ru": "↩️ Снова в списке"},
    "t.del_q": {"en": "🗑 Delete <b>{name}</b>?", "ru": "🗑 Удалить <b>{name}</b>?"},
    "t.done_toast": {"en": "✅ Done!", "ru": "✅ Готово!"},
    "t.already": {"en": "Already done", "ru": "Уже выполнено"},
    "t.restored": {"en": "Restored", "ru": "Восстановлено"},
    "t.reopened": {"en": "↩️ Reopened", "ru": "↩️ Вернули в работу"},
    "t.renamed": {"en": "✏️ Renamed", "ru": "✏️ Переименовано"},
    "t.next_one": {"en": "✅ Done! Next one: {when}", "ru": "✅ Готово! Следующая: {when}"},
    "t.type_due": {
        "en": "⌨️ <b>Type the due time</b>\n\nFor example:\n<code>in 2h</code> · <code>18:30</code> · <code>tomorrow 9:00</code>\n<code>fri 18:00</code> · <code>25/12 10:00</code>",
        "ru": "⌨️ <b>Напишите срок</b>\n\nНапример:\n<code>in 2h</code> · <code>18:30</code> · <code>tomorrow 9:00</code>\n<code>fri 18:00</code> · <code>25/12 10:00</code>",
    },
    "t.type_time": {"en": "⌨️ <b>Type the time</b>, e.g. <code>17:45</code>",
                    "ru": "⌨️ <b>Напишите время</b>, например <code>17:45</code>"},
    "t.type_text": {"en": "✏️ <b>Type the new text</b>", "ru": "✏️ <b>Напишите новый текст</b>"},
    "t.retry": {"en": "🤔 {err}\nTry again, or tap Cancel above.", "ru": "🤔 {err}\nПопробуйте снова или нажмите «Отмена»."},
    "t.passed": {"en": "That time has already passed.", "ru": "Это время уже прошло."},
    "t.passed_long": {"en": "🤔 That time has already passed. Try a later one.",
                      "ru": "🤔 Это время уже прошло. Выберите позже."},
    "t.pick_day": {"en": "📅 Pick a day for <b>{name}</b>", "ru": "📅 Выберите день для <b>{name}</b>"},
    "t.what_time": {"en": "🕐 What time on <b>{day}</b>?", "ru": "🕐 Во сколько <b>{day}</b>?"},
    "t.other_time": {"en": "⌨️ Other time", "ru": "⌨️ Другое время"},
    "t.set_due_first": {"en": "Set a due time first.", "ru": "Сначала поставьте срок."},
    "t.repeat_needs_date": {"en": "Set a due time first - a repeat needs a date to count from.",
                            "ru": "Сначала поставьте срок — от него считается повтор."},
    # pushes
    "t.push.reminder": {"en": "⏰ <b>Reminder</b>\n\n📌 {name}\n<i>Due {when}</i>",
                        "ru": "⏰ <b>Напоминание</b>\n\n📌 {name}\n<i>Срок {when}</i>"},
    "t.push.heads": {"en": "🔔 <b>Heads up</b>\n\n📌 {name}\n<i>Due {when} · {rel}</i>",
                     "ru": "🔔 <b>Скоро срок</b>\n\n📌 {name}\n<i>Срок {when} · {rel}</i>"},
    "t.push.open": {"en": "📌 Open task", "ru": "📌 Открыть задачу"},
    "t.push.open_list": {"en": "📝 Open tasks", "ru": "📝 Открыть задачи"},
    "t.push.h1": {"en": "⏰ +1 hour", "ru": "⏰ +1 час"},
    "t.push.tonight": {"en": "🌙 Tonight", "ru": "🌙 Вечером"},
    "t.push.tomorrow": {"en": "📅 Tomorrow", "ru": "📅 Завтра"},
    "t.push.nice": {"en": "✅ <s>{name}</s>\nNice work! 🎉", "ru": "✅ <s>{name}</s>\nОтлично! 🎉"},
    "t.push.next": {"en": "✅ <s>{name}</s>\n🔁 Next one: {when}", "ru": "✅ <s>{name}</s>\n🔁 Следующая: {when}"},
    "t.push.snoozed": {"en": "⏰ <b>{name}</b>\nSnoozed. I'll remind you {when}.",
                       "ru": "⏰ <b>{name}</b>\nОтложено. Напомню {when}."},
    "t.snoozed": {"en": "Snoozed", "ru": "Отложено"},
    # quick due options (labels shift with the current hour)
    "t.edit": {"en": "✏️ Edit", "ru": "✏️ Изменить"},
    "t.edit_title": {"en": "✏️ <b>{name}</b>\n<i>What would you like to change?</i>",
                     "ru": "✏️ <b>{name}</b>\n<i>Что изменить?</i>"},
    "t.due_with": {"en": "⏰ {when}", "ru": "⏰ {when}"},
    "t.set_due": {"en": "⏰ Set a due time", "ru": "⏰ Поставить срок"},
    "t.remind_btn": {"en": "🔔 Remind: {when}", "ru": "🔔 Напомнить: {when}"},
    "t.repeat_btn": {"en": "🔁 Repeat: {how}", "ru": "🔁 Повтор: {how}"},
    "t.lead_more": {"en": "⋯ Other", "ru": "⋯ Другое"},
    "t.q.1h": {"en": "In 1 hour", "ru": "Через час"},
    "t.q.3h": {"en": "In 3 hours", "ru": "Через 3 часа"},
    "t.q.eve": {"en": "Tonight 20:00", "ru": "Вечером 20:00"},
    "t.q.tm9": {"en": "Tomorrow 09:00", "ru": "Завтра 09:00"},
    "t.q.tm18": {"en": "Tomorrow 18:00", "ru": "Завтра 18:00"},
    "t.q.mon9": {"en": "Next Mon 09:00", "ru": "В пн 09:00"},
})

STRINGS.update({
    "td.more": {"en": "<i>…and {n} more</i>", "ru": "<i>…и ещё {n}</i>"},
    "td.nothing": {"en": "Nothing due today 🎉", "ru": "На сегодня сроков нет 🎉"},
    "td.done_today": {"en": "✨ {n} done today", "ru": "✨ {n} выполнено сегодня"},
    "td.more_open": {"en": "{n} more on your list", "ru": "ещё {n} в списке"},
})

# ---------- habits ----------
STRINGS.update({
    "h.title": {"en": "🔁 <b>Habits</b> · {date}", "ru": "🔁 <b>Привычки</b> · {date}"},
    "h.empty": {
        "en": "No habits yet.\nStart with one small thing. I'll remind you every day and keep track of your streak 🔥",
        "ru": "Пока нет привычек.\nНачните с одной небольшой. Буду напоминать каждый день и считать серию 🔥",
    },
    "h.progress": {"en": "{done}/{total} today", "ru": "{done}/{total} сегодня"},
    "h.progress_reps": {"en": "{done}/{total} habits · {reps}/{reps_total} check-ins",
                        "ru": "{done}/{total} привычек · {reps}/{reps_total} отметок"},
    "h.all_done": {"en": "🎉 <b>All done for today!</b>", "ru": "🎉 <b>На сегодня всё!</b>"},
    "h.rest": {"en": "\nNothing scheduled today. Rest day 🌿", "ru": "\nНа сегодня ничего. День отдыха 🌿"},
    "h.not_today": {"en": "\n<i>Not today: {list}</i>", "ru": "\n<i>Не сегодня: {list}</i>"},
    "h.paused_list": {"en": "<i>Paused: {list}</i>", "ru": "<i>На паузе: {list}</i>"},
    "h.tap_hint": {"en": "\n<i>Tap a habit to check it off.</i>", "ru": "\n<i>Нажмите, чтобы отметить.</i>"},
    "h.new": {"en": "➕ New habit", "ru": "➕ Новая привычка"},
    "h.manage": {"en": "⚙️ Manage", "ru": "⚙️ Настроить"},
    "h.week": {"en": "📊 This week", "ru": "📊 За неделю"},
    "h.manage.title": {"en": "⚙️ <b>Manage habits</b>\nTap one to edit its name, time or days.",
                       "ru": "⚙️ <b>Настройка привычек</b>\nНажмите, чтобы изменить название, время или дни."},
    "h.manage.empty": {"en": "⚙️ <b>Manage habits</b>\nNo habits yet.",
                       "ru": "⚙️ <b>Настройка привычек</b>\nПривычек пока нет."},
    "h.paused_tag": {"en": " · ⏸ paused", "ru": " · ⏸ на паузе"},
    "h.sched_line": {"en": "🕐 {when} · {days}", "ru": "🕐 {when} · {days}"},
    "h.today_line": {"en": "💪 Today: <b>{done}/{total}</b>", "ru": "💪 Сегодня: <b>{done}/{total}</b>"},
    "h.next": {"en": "🔔 Next reminder: {when}", "ru": "🔔 Следующее напоминание: {when}"},
    "h.streak": {"en": "🔥 Streak {now} · best {best}", "ru": "🔥 Серия {now} · лучшая {best}"},
    "h.no_streak": {"en": "🔥 No streak yet. Today's a good day to start",
                    "ru": "🔥 Серии пока нет. Сегодня хороший день, чтобы начать"},
    "h.rate": {"en": "📈 {pct}% of the last 30 days", "ru": "📈 {pct}% за последние 30 дней"},
    "h.legend": {"en": "<i>▓ done  ▒ partial  ░ skipped  ✗ missed  · rest day</i>",
                 "ru": "<i>▓ сделано  ▒ частично  ░ пропуск  ✗ не сделано  · день отдыха</i>"},
    "h.plus": {"en": "➕ +1", "ru": "➕ +1"},
    "h.minus": {"en": "➖ −1", "ru": "➖ −1"},
    "h.time": {"en": "🕐 Time", "ru": "🕐 Время"},
    "h.schedule": {"en": "🕐 Schedule", "ru": "🕐 Расписание"},
    "h.days": {"en": "📅 Days", "ru": "📅 Дни"},
    "h.pause": {"en": "⏸ Pause", "ru": "⏸ Пауза"},
    "h.resume": {"en": "▶️ Resume", "ru": "▶️ Продолжить"},
    "h.test": {"en": "🔔 Test reminder", "ru": "🔔 Проверить напоминание"},
    "h.test_sent": {"en": "Sent 🔔 Check your phone's notifications.",
                    "ru": "Отправил 🔔 Проверьте уведомления на телефоне."},
    "h.paused_note": {"en": "⏸ Paused. No reminders until you resume.",
                      "ru": "⏸ На паузе. Напоминаний не будет, пока не продолжите."},
    "h.resumed": {"en": "▶️ Resumed", "ru": "▶️ Продолжаем"},
    "h.del_q": {"en": "🗑 Delete <b>{name}</b>?\n<i>Its whole history goes too: streak {now}, best {best}.</i>",
                "ru": "🗑 Удалить <b>{name}</b>?\n<i>Вся история тоже исчезнет: серия {now}, лучшая {best}.</i>"},
    "h.name_q": {"en": "✨ <b>New habit</b>\n\nWhat do you want to do regularly?\n<i>Type it, or pick one below.</i>",
                 "ru": "✨ <b>Новая привычка</b>\n\nЧто хотите делать регулярно?\n<i>Напишите или выберите ниже.</i>"},
    "h.kind_q": {"en": "⏱ How often should <b>{name}</b> happen?",
                 "ru": "⏱ Как часто делать <b>{name}</b>?"},
    "h.once": {"en": "🕐 Once a day", "ru": "🕐 Раз в день"},
    "h.many": {"en": "🔁 Several times a day", "ru": "🔁 Несколько раз в день"},
    "h.time_q": {"en": "🕐 When should I remind you to <b>{name}</b>?",
                 "ru": "🕐 Когда напоминать про <b>{name}</b>?"},
    "h.interval_q": {"en": "⏱ <b>How often?</b>\nI'll remind you at each step.",
                     "ru": "⏱ <b>Как часто?</b>\nБуду напоминать каждый раз."},
    "h.window_q": {"en": "🕐 <b>Between which hours?</b>", "ru": "🕐 <b>В какие часы?</b>"},
    "h.custom_hours": {"en": "⌨️ Custom hours", "ru": "⌨️ Свои часы"},
    "h.type_hours": {"en": "⌨️ <b>Type the hours</b>, e.g. <code>09:00-18:00</code>",
                     "ru": "⌨️ <b>Напишите часы</b>, например <code>09:00-18:00</code>"},
    "h.bad_range": {"en": "Use a range like <code>09:00-18:00</code>.",
                    "ru": "Нужен диапазон, например <code>09:00-18:00</code>."},
    "h.end_after": {"en": "The end has to come after the start.", "ru": "Конец должен быть позже начала."},
    "h.days_q": {"en": "📅 <b>Which days?</b>\n\nSelected: <b>{sel}</b>",
                 "ru": "📅 <b>Какие дни?</b>\n\nВыбрано: <b>{sel}</b>"},
    "h.days_none": {"en": "none yet", "ru": "пока ничего"},
    "h.pick_day_min": {"en": "Pick at least one day.", "ru": "Выберите хотя бы один день."},
    "h.created": {"en": "✨ <b>Habit created!</b>", "ru": "✨ <b>Привычка создана!</b>"},
    "h.first_rem": {"en": "\nFirst reminder: {when}", "ru": "\nПервое напоминание: {when}"},
    "h.days_updated": {"en": "📅 Days updated", "ru": "📅 Дни обновлены"},
    "h.sched_updated": {"en": "🕐 <b>Schedule updated</b>", "ru": "🕐 <b>Расписание обновлено</b>"},
    "h.time_moved": {"en": "🕐 Reminder moved to {when}", "ru": "🕐 Напоминание перенесено на {when}"},
    "h.new_time_q": {"en": "🕐 New reminder time for <b>{name}</b>?\n<i>Now: {when}</i>",
                     "ru": "🕐 Новое время для <b>{name}</b>?\n<i>Сейчас: {when}</i>"},
    "h.type_name": {"en": "✏️ <b>Type the new name</b>", "ru": "✏️ <b>Напишите новое название</b>"},
    "h.need_name": {"en": "🤔 Give it a name.", "ru": "🤔 Нужно название."},
    "h.unchecked": {"en": "Unchecked", "ru": "Отметка снята"},
    "h.streak_toast": {"en": "🔥 {n}-day streak!", "ru": "🔥 Серия {n} дней!"},
    "h.done_toast": {"en": "✅ Done!", "ru": "✅ Готово!"},
    "h.target_hit": {"en": "🎉 {done}/{total} - done for today!", "ru": "🎉 {done}/{total} — на сегодня всё!"},
    "h.milestone": {"en": "🏆 {n} days in a row!", "ru": "🏆 {n} дней подряд!"},
    # weekly stats
    "h.week.title": {"en": "📊 <b>This week</b> · {start} – {end}", "ru": "📊 <b>Эта неделя</b> · {start} – {end}"},
    "h.week.none": {"en": "No active habits yet.", "ru": "Пока нет активных привычек."},
    "h.week.sum": {"en": "<b>{done}/{total} done · {pct}%</b>", "ru": "<b>{done}/{total} · {pct}%</b>"},
    "h.week.prev": {"en": "\nLast week: {pct}% {arrow}", "ru": "\nНа прошлой неделе: {pct}% {arrow}"},
    "h.week.longest": {"en": "🔥 Longest run right now: {n} days · {name}",
                       "ru": "🔥 Самая длинная серия сейчас: {n} дней · {name}"},
    "h.week.tail": {"en": "\n\n<i>That's your week. New one starts tomorrow.</i>",
                    "ru": "\n\n<i>Вот ваша неделя. Новая начинается завтра.</i>"},
    # nudges
    "h.push.time": {"en": "🔁 Time for <b>{name}</b>", "ru": "🔁 Пора: <b>{name}</b>"},
    "h.push.streak_tail": {"en": "\n🔥 {n}-day streak. Keep it going!", "ru": "\n🔥 Серия {n} дней. Не бросайте!"},
    "h.push.encourage": {"en": "\nYou've got this 💪", "ru": "\nУ вас получится 💪"},
    "h.push.interval": {"en": "💪 Time for <b>{name}</b>\n<i>{done}/{total} today</i>",
                        "ru": "💪 Пора: <b>{name}</b>\n<i>{done}/{total} сегодня</i>"},
    "h.push.done_n": {"en": "✅ Done ({n}/{total})", "ru": "✅ Готово ({n}/{total})"},
    "h.push.skip": {"en": "⏭ Skip today", "ru": "⏭ Пропустить сегодня"},
    "h.push.in1h": {"en": "⏰ In 1 hour", "ru": "⏰ Через час"},
    "h.push.open": {"en": "🔁 Open habits", "ru": "🔁 Открыть привычки"},
    "h.push.did": {"en": "✅ <b>{name}</b>: done!", "ru": "✅ <b>{name}</b>: сделано!"},
    "h.push.count": {"en": "✅ <b>{name}</b>: {done}/{total} today", "ru": "✅ <b>{name}</b>: {done}/{total} сегодня"},
    "h.push.finished": {"en": "🎉 <b>{name}</b>: {done}/{total} - done for today!",
                        "ru": "🎉 <b>{name}</b>: {done}/{total} — на сегодня всё!"},
    "h.push.skipped": {"en": "⏭ <b>{name}</b>: skipped today. No worries, see you next time.",
                       "ru": "⏭ <b>{name}</b>: сегодня пропуск. Ничего страшного, до следующего раза."},
    "h.push.snoozed": {"en": "⏰ <b>{name}</b>\nOK, I'll remind you again at {when}.",
                       "ru": "⏰ <b>{name}</b>\nХорошо, напомню ещё раз в {when}."},
    "h.push.too_late": {"en": "Too late to snooze. It would land on tomorrow. Tap Done or Skip.",
                        "ru": "Уже поздно откладывать — попадёт на завтра. Нажмите «Готово» или «Пропустить»."},
    "h.nice": {"en": "Nice! 💪", "ru": "Отлично! 💪"},
    "h.skipped": {"en": "Skipped", "ru": "Пропущено"},
    "h.every": {"en": "every {step}, {start}–{end}", "ru": "каждые {step}, {start}–{end}"},
    "h.daily_label": {"en": "every day", "ru": "каждый день"},
    "h.weekdays": {"en": "weekdays", "ru": "по будням"},
    "h.weekends": {"en": "weekends", "ru": "по выходным"},
    "h.preset.daily": {"en": "Every day", "ru": "Каждый день"},
    "h.preset.weekdays": {"en": "Weekdays", "ru": "Будни"},
    "h.preset.weekends": {"en": "Weekends", "ru": "Выходные"},
    "h.int.30": {"en": "Every 30 min", "ru": "Каждые 30 минут"},
    "h.int.60": {"en": "Every hour", "ru": "Каждый час"},
    "h.int.120": {"en": "Every 2 hours", "ru": "Каждые 2 часа"},
    "h.int.180": {"en": "Every 3 hours", "ru": "Каждые 3 часа"},
    "h.win.work": {"en": "Work day 09–18", "ru": "Рабочий день 09–18"},
    "h.win.waking": {"en": "Waking hours 08–22", "ru": "Весь день 08–22"},
})

STRINGS.update({
    "h.edit": {"en": "✏️ Edit", "ru": "✏️ Изменить"},
    "h.edit_title": {"en": "✏️ <b>{name}</b>\n<i>What would you like to change?</i>",
                     "ru": "✏️ <b>{name}</b>\n<i>Что изменить?</i>"},
    "h.mark_done": {"en": "✅ Mark today done", "ru": "✅ Отметить сегодня"},
    "h.mark_undo": {"en": "↩️ Undo today", "ru": "↩️ Снять отметку"},
    "h.tpl.0": {"en": "📖 Read 20 pages", "ru": "📖 Читать 20 страниц"},
    "h.tpl.1": {"en": "🎩 Practice a magic trick", "ru": "🎩 Отрепетировать фокус"},
    "h.tpl.2": {"en": "🏃 Exercise", "ru": "🏃 Зарядка"},
    "h.tpl.3": {"en": "🧘 Meditate 10 min", "ru": "🧘 Медитация 10 мин"},
    "h.tpl.4": {"en": "💧 Drink water", "ru": "💧 Выпить воды"},
    "h.tpl.5": {"en": "🚶 Walk 30 min", "ru": "🚶 Прогулка 30 мин"},
})

# ---------- more / settings ----------
STRINGS.update({
    "s.title": {"en": "⚙️ <b>More</b>\n\n🌍 Timezone: <b>{tz}</b>\n🕐 Your local time: <b>{time}</b>",
                "ru": "⚙️ <b>Ещё</b>\n\n🌍 Часовой пояс: <b>{tz}</b>\n🕐 Ваше время: <b>{time}</b>"},
    "s.tz": {"en": "🌍 My timezone", "ru": "🌍 Часовой пояс"},
    "s.export": {"en": "📤 Export my data", "ru": "📤 Выгрузить мои данные"},
    "s.export_caption": {"en": "📤 Your tasks and habits.", "ru": "📤 Ваши задачи и привычки."},
    "s.collecting": {"en": "Collecting…", "ru": "Собираю…"},
    "s.wipe": {"en": "🗑 Delete my account", "ru": "🗑 Удалить мой аккаунт"},
    "s.wipe_q": {
        "en": "🗑 <b>Delete your account?</b>\n\nEvery task, habit and day of history you have goes with it. This can't be undone.",
        "ru": "🗑 <b>Удалить аккаунт?</b>\n\nВсе задачи, привычки и вся история исчезнут. Это нельзя отменить.",
    },
    "s.wipe_ok": {"en": "🗑 Yes, delete everything", "ru": "🗑 Да, удалить всё"},
    "s.wiped": {"en": "Everything is gone. Send /start if you ever want to come back.",
                "ru": "Всё удалено. Напишите /start, если захотите вернуться."},
    "s.users": {"en": "👥 Users", "ru": "👥 Пользователи"},
    "s.jobs": {"en": "📊 Scheduled jobs", "ru": "📊 Задания"},
    "s.status": {"en": "ℹ️ Status", "ru": "ℹ️ Состояние"},
})
