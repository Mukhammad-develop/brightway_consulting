# Deploy Brightway Consulting on PythonAnywhere

This guide gets the **Django web app** (admin panel + public site) running on PythonAnywhere. The **Telegram bot** and **userbot** need to run separately (see bottom).

---

## 1. Create account and start a Web app

1. Sign up at [pythonanywhere.com](https://www.pythonanywhere.com).
2. **Dashboard → Web** → **Add a new web app** → **Next** → choose **Manual configuration** (not Flask) → **Next**.
3. Pick **Python 3.10** (or 3.11). Finish.

---

## 2. Clone the project and set up the virtualenv

In a **Bash** console on PythonAnywhere:

```bash
cd ~
git clone https://github.com/Mukhammad-develop/brightway_consulting.git
cd brightway_consulting
```

Create and use a virtualenv, install dependencies:

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Environment variables

Create a `.env` in the project root (`~/brightway_consulting/.env`):

```bash
# Required for production
DEBUG=False
SECRET_KEY=your-long-random-secret-key-here
ALLOWED_HOSTS=yourusername.pythonanywhere.com

# Admin panel login (.env master user)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password

# Optional: second master
# MASTER2_USERNAME=...
# MASTER2_PASSWORD=...
# MASTER2_DISPLAY=...

# Telegram bot (if you run the bot elsewhere, leave blank here)
# BOT_TOKEN=...
# OPENAI_API_KEY=...
# TG_API_ID=...
# TG_API_HASH=...
# TG_PHONE=...
```

Replace `yourusername` with your PythonAnywhere username.

---

## 4. Database and static files

In the same console (with `venv` active):

```bash
cd ~/brightway_consulting
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
mkdir -p uploads
```

---

## 5. Configure the Web app

1. Go to **Web** tab on PythonAnywhere.
2. **Code** section:
   - **Source code**: `/home/yourusername/brightway_consulting`
   - **Working directory**: `/home/yourusername/brightway_consulting`
   - **WSGI configuration file**: `/home/yourusername/brightway_consulting/bwc/wsgi.py` (use the project’s WSGI file from the repo; do not use the random file PythonAnywhere creates under `/var/www/`).

3. **Static files** (scroll down):  
   You need **two** mappings. Use your real username instead of `yourusername`.
   - **URL**: `/static/`  
     **Directory**: `/home/yourusername/brightway_consulting/staticfiles`  
     (Do **not** point `/static/` at `uploads` – that breaks CSS/JS and can show a big blue circle or broken layout.)
   - **URL**: `/uploads/`  
     **Directory**: `/home/yourusername/brightway_consulting/uploads`

   After changing, **Reload** the web app (green button).

---

## 6. Check the site

- Public site: `https://yourusername.pythonanywhere.com/`
- Admin panel: `https://yourusername.pythonanywhere.com/admin/`

Log in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `.env`.

---

## 7. (Optional) Telegram bot and userbot on PythonAnywhere

The Django site works without the bot. To run the **Telegram bot** and **userbot**:

- **Free account**: You cannot run long-running processes 24/7. You can run them manually in a console for testing, or use a different host (e.g. a VPS) for the bots.
- **Paid account**: Use **Tasks** or an **Always-on task** to run:
  - `python manage.py run_bot` (Telegram bot)
  - `python manage.py run_userbot` (userbot for sending/receiving as your Telegram account)

Add to `.env` on PythonAnywhere if the bots run here:

- `BOT_TOKEN`, `OPENAI_API_KEY`, `TG_API_ID`, `TG_API_HASH`, `TG_PHONE` (and optionally second account vars).

Then in the Web app or a separate console, run the commands above (or configure an Always-on task that runs one of them).

---

## 8. Scheduled reminders (cron job)

The no-reply reminder system requires a cron job to run every 5 minutes.

Go to **Tasks** tab on PythonAnywhere and add a **Scheduled task** with the following command (replace `abdurakhmon70` with your actual username):

```
/home/abdurakhmon70/brightway_consulting/venv/bin/python /home/abdurakhmon70/brightway_consulting/manage.py process_no_reply_reminders
```

Set it to run every **5 minutes** (minimum interval on paid accounts).

> **Important**: Do NOT use `workon venv` or `cd ... && source venv/bin/activate` in cron — those require an interactive shell. Always use the **full path** to the Python binary inside the local `venv/` folder.

---

## Troubleshooting

- **500 error**: Check **Web → Logs → Error log**.
- **Static files 404**: Ensure **Static files** mappings are correct and you ran `collectstatic`.
- **Import errors**: Ensure **Working directory** and **Source code** point to `brightway_consulting` and the WSGI file adds that path to `sys.path` (as in step 5).
- **CSRF / redirect issues**: Ensure `ALLOWED_HOSTS` in `.env` is exactly `yourusername.pythonanywhere.com` (no trailing slash, correct username).
