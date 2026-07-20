# Study Coach Bot — Setup Guide

A personal Telegram bot that turns your study material (a textbook, a lecture
deck, a set of notes) into a daily target and reminds you a few times a day,
based on your deadline and how much you have left.

This guide assumes you've never used a terminal before. Follow the steps
in order — each one tells you exactly what to type. `bot.py` is the only
file you ever run yourself; everything else in the folder is used by it
automatically.

**What it actually does, once it's running:**
- You tell it about a project: what it is, how much there is (e.g. 40
  chapters), and your deadline.
- It works out how much you need to do per day to finish on time, and
  recalculates that every time you log progress.
- A few times a day — only between the wake/sleep hours you set — it sends
  a reminder with your current daily target.
- It tracks a daily streak, and sends a summary at the end of each day and
  a recap once a week.

---

## What you'll need

- A computer (Windows, Mac, or Linux)
- A Telegram account (the app, or telegram.org)
- About 20–30 minutes, the first time

---

## Step 1 — Install Python

1. Go to **https://www.python.org/downloads/** and download Python 3.12
   or newer.
2. Run the installer.
   - **Windows only:** on the very first screen, tick **"Add python.exe
     to PATH"** before clicking Install. This is the single most common
     thing people miss.
3. Confirm it worked. Open a terminal:
   - **Windows:** press the Start key, type `cmd`, press Enter.
   - **Mac:** press Cmd+Space, type `Terminal`, press Enter.
   Then run:
   ```
   python3 --version
   ```
   (On Windows, if that's not recognized, try `python --version` instead.)
   You should see `Python 3.12.x` or similar. If you get an error instead,
   the PATH step above was likely skipped — rerun the installer, choose
   "Modify", and tick that box.

---

## Step 2 — Create your bot with BotFather

1. In Telegram, search for **@BotFather** (it has a blue checkmark — it's
   Telegram's own official bot for creating bots).
2. Send `/newbot`.
3. Give your bot a display name (anything you like).
4. Give it a username — this must be unique and end in `bot`
   (e.g. `hamza_study_coach_bot`).
5. BotFather replies with a **token** that looks like
   `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`. Copy it somewhere safe — you'll
   paste it into a config file in Step 6. Keep it private; anyone who has
   this token can control your bot.

---

## Step 3 — (Optional) Get your Telegram ID for admin access

Skip this if you don't care about the `/admin` and `/broadcast` commands
— the bot works fully without it.

1. In Telegram, search for **@userinfobot** and send it any message.
2. It replies with your numeric **Id**. Save that number for Step 6.
   This is what makes `/admin` (usage stats) and `/broadcast` (message
   everyone) work for your account specifically.

---

## Step 4 — Unzip the project

Unzip the attached file somewhere easy to find, like your Desktop. You
should see a folder called `study_coach_bot` containing `bot.py`,
`requirements.txt`, and several other files and folders.

---

## Step 5 — Open a terminal inside that folder

- **Windows:** open the `study_coach_bot` folder in File Explorer, click
  the address bar at the top, type `cmd`, press Enter.
- **Mac:** open Terminal, type `cd ` (with a trailing space), then drag
  the `study_coach_bot` folder from Finder into the Terminal window, and
  press Enter.

Check you're in the right place by running:
```
python3 bot.py
```
You should get an error mentioning a missing module (that's expected —
we haven't installed anything yet) rather than "file not found." If you
get "file not found" or "No such file or directory," you're not inside
the right folder yet.

---

## Step 6 — Create a virtual environment

This keeps this project's packages separate from anything else on your
computer, and sidesteps a very common error on newer Mac and Linux
systems (see the Troubleshooting section below if you're curious what
that error looks like).

**Windows:**
```
python -m venv venv
venv\Scripts\activate
```

**Mac/Linux:**
```
python3 -m venv venv
source venv/bin/activate
```

If it worked, your terminal line now starts with `(venv)`. You'll need
to re-run the second line above (`venv\Scripts\activate` or
`source venv/bin/activate`) every time you close and reopen the terminal
before running the bot again.

---

## Step 7 — Install the required packages

With `(venv)` still showing in your terminal:
```
pip install -r requirements.txt
```

This downloads everything the bot depends on — it's normal for this to
take a minute or two. When it finishes, you'll be back at a normal prompt
with no red error text.

---

## Step 8 — Add your bot token

1. In the `study_coach_bot` folder, find the file `.env.example`.
2. Make a copy of it and rename the copy to exactly `.env`
   (just `.env` — nothing before the dot, and not `.env.txt`; some
   editors add `.txt` automatically, so double-check the name afterward).
3. Open `.env` in any plain text editor (Notepad, TextEdit) and fill in:
   ```
   TELEGRAM_BOT_TOKEN=paste_your_botfather_token_here
   DATABASE_URL=sqlite+aiosqlite:///study_coach.db
   ADMIN_USER_ID=paste_your_userinfobot_id_here
   ```
   If you skipped Step 3, leave `ADMIN_USER_ID` as the placeholder number
   that's already there — everything except `/admin` and `/broadcast`
   still works fine.
4. Save the file.

---

## Step 9 — Run the bot

Still in your terminal, with `(venv)` showing:
```
python3 bot.py
```

You should see log lines ending with `Study Coach Bot is starting
polling...`. **The terminal will just sit there after that — that's
correct**, it means the bot is running and listening. Leave this window
open; closing it stops the bot.

---

## Step 10 — Take it for a test drive

In Telegram, open a chat with the bot username you picked in Step 2.

1. Send `/start` — you should get a welcome message with buttons.
2. Tap **➕ New Project** and answer its questions (name, type, how much
   there is, deadline, and so on) to create your first study project.
3. Tap **📚 Projects → (your project)** to see your calculated daily
   target.
4. Tap **✅ Log Progress**, pick your project, and log a small amount —
   your daily target should recalculate immediately.
5. Tap **⚙️ Settings** and set your timezone and wake/sleep hours so
   reminders arrive at sensible times for you.

If all five of those worked, the bot is fully up and running.

---

## Everyday use, once it's set up

- `/start` — open the main menu
- `/done` — quickly log progress on a project
- `/stats` — see your streak and stats
- `/cancel` — bail out of anything you're in the middle of, any time
- Most things are done by tapping buttons, not typing commands.

---

## Keeping it running long-term

Running `python3 bot.py` only keeps the bot online while that terminal
window stays open. If you close it, or your computer sleeps, the bot
goes offline — reminders simply resume automatically once you start it
again, you won't lose any data. To keep it running permanently in the
background, you'd host it somewhere that stays on 24/7 (a small cloud
server, for example). That's a separate, more involved step — worth
doing only once you've confirmed everything works locally first.

---

## Troubleshooting

**"externally-managed-environment" error during `pip install`**
This happens on newer Mac (Homebrew Python) and some Linux systems when
you try to install packages outside a virtual environment. It's exactly
what Step 6 avoids — make sure you see `(venv)` at the start of your
terminal line before running `pip install`. If you skipped Step 6, go
back and do it now.

**"python3 is not recognized" / "python is not recognized" (Windows)**
Python wasn't added to PATH during install. Rerun the Python installer,
choose "Modify," and tick "Add python.exe to PATH."

**"ModuleNotFoundError: No module named 'telegram'" (or similar)**
Either the install step didn't complete, or `(venv)` isn't showing in
your terminal (meaning the virtual environment isn't active — rerun the
activate command from Step 6, then `pip install -r requirements.txt`
again).

**"TELEGRAM_BOT_TOKEN is not set" when you run `python3 bot.py`**
Your `.env` file is missing, misnamed (check it's not `.env.txt`), isn't
in the same folder as `bot.py`, or the token line inside it is empty.

**Bot doesn't respond at all in Telegram**
Check the terminal running `bot.py` for error text. Make sure you're
messaging the exact bot username from Step 2, and that the terminal
window is still open and running.

**You tapped a button and nothing happened, or got a generic error**
This can happen if the bot was restarted (or your computer slept) while
you were partway through something. Send `/cancel` and start that action
again.

**Reminders aren't arriving when you'd expect**
Check your timezone (⚙️ Settings → 🌐 Timezone) and that the current
time falls between your wake and sleep times. Reminders arrive within
about 10 minutes of their scheduled time, not to-the-minute.

**You want to start over with a completely clean bot**
Stop the bot (Ctrl+C in the terminal), delete the file `study_coach.db`
that appeared in the folder after your first run, and start the bot
again — it recreates an empty database automatically.

---

## A note on how this was built and checked

This project went through several rounds of review before reaching you:
fixing a startup bug that prevented the bot from launching at all, adding
restart-safe scheduling so reminders survive the bot going offline and
back online, wiring up buttons that used to do nothing, and switching
free-typed answers to tap-to-select buttons wherever a typo could
otherwise cause a silent mismatch later on.

On top of that prior work, this version was re-verified end to end:
every file was checked for syntax errors, every button's callback was
cross-referenced against its handler to confirm nothing is a dead end,
and every import between files was confirmed to resolve correctly. A
further review then caught and fixed three subtler issues: a reminder
scheduling edge case that could skew how many reminders arrived on two
consecutive days if the bot had been offline for part of the morning,
a settings flow that could have its in-progress answer wiped if a
project was created at the same time, and a safety net so the bot
can't crash if someone taps an old button after their data was reset.
The first of those was confirmed with an actual simulation, not just a
read-through, before and after the fix.

What that verification *can't* replicate is an actual live connection to
Telegram's servers — that first real test happens when you run Step 9
yourself. If anything errors out there, copy what the terminal shows and
ask for help fixing it.
