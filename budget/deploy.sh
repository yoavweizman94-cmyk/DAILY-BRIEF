#!/usr/bin/env bash
# One-command first deploy for the couple budget tracker.
# Prerequisite: `npx wrangler login` (opens a browser once).
# Safe to re-run: every step skips itself if already done.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "בודק חיבור לחשבון Cloudflare..."
if ! npx wrangler whoami >/dev/null 2>&1; then
  echo "לא מחובר. מריץ התחברות (ייפתח דפדפן — אשר את הגישה):"
  npx wrangler login
fi

# 1. Random secret path (only if still the default from the repo)
if grep -q 'APP_PATH = "app-7kq9x2mfrt3vbn8w"' wrangler.toml; then
  NEW_PATH="app-$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 16)"
  sed -i.bak "s|APP_PATH = \"app-7kq9x2mfrt3vbn8w\"|APP_PATH = \"$NEW_PATH\"|" wrangler.toml && rm -f wrangler.toml.bak
  say "נוצר path סודי חדש: $NEW_PATH"
fi

# 2. Create the D1 database (only if the id is still the placeholder)
if grep -q '^database_id = "PASTE_DATABASE_ID_HERE"' wrangler.toml; then
  say "יוצר בסיס נתונים D1..."
  OUT=$(npx wrangler d1 create couple-budget-db 2>&1) || { echo "$OUT"; exit 1; }
  DB_ID=$(echo "$OUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
  [ -n "$DB_ID" ] || { echo "לא הצלחתי לחלץ database_id מהפלט:"; echo "$OUT"; exit 1; }
  sed -i.bak "s|^database_id = \"PASTE_DATABASE_ID_HERE\"|database_id = \"$DB_ID\"|" wrangler.toml && rm -f wrangler.toml.bak
  echo "database_id נשמר ב-wrangler.toml: $DB_ID"
fi

# 3. Apply the schema (idempotent — IF NOT EXISTS everywhere)
say "טוען את הסכמה לבסיס הנתונים..."
npx wrangler d1 execute couple-budget-db --remote --file=schema.sql -y

# 4. Deploy the Worker
say "פורס את האפליקציה..."
npx wrangler deploy

# 5. PIN secret
say "קביעת קוד כניסה (PIN) — הקלד 4-6 ספרות:"
npx wrangler secret put APP_PIN

# 6. Print the final URL
APP_PATH=$(grep 'APP_PATH' wrangler.toml | sed 's/.*"\(.*\)".*/\1/')
say "זהו! הכתובת של הדף שלכם:"
echo "  קחו את כתובת ה-Worker משורת הפריסה למעלה (https://couple-budget...workers.dev)"
echo "  והוסיפו בסופה: /$APP_PATH"
echo "פתחו בנייד, הזינו את ה-PIN, ואשף ההגדרה יוביל אתכם."
