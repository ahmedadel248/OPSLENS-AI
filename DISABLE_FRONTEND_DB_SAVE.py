from pathlib import Path
import re

path = Path("web/app.js")

if not path.exists():
    raise SystemExit("ERROR: web/app.js not found")

text = path.read_text(encoding="utf-8", errors="ignore")

# Replace any old frontend save function with a hard no-op.
pattern = r'async function saveCurrentReportToDatabase\s*\([^)]*\)\s*\{.*?\n\}\s*\n\s*function showToast'

replacement = '''async function saveCurrentReportToDatabase() {
  return null;
}

function showToast'''

new_text, count = re.subn(pattern, replacement, text, flags=re.S)

if count == 0:
    print("WARN: saveCurrentReportToDatabase block not found by regex.")
else:
    text = new_text
    print(f"OK: disabled saveCurrentReportToDatabase block. Replacements: {count}")

# Hard block any remaining accidental direct frontend DB save calls.
text = text.replace(
    'await api("/api/db/reports/save",',
    'await Promise.resolve(null) /* frontend DB save disabled */ && api("/api/db/reports/save",'
)

text = text.replace(
    'api("/api/db/reports/save",',
    'Promise.resolve(null) /* frontend DB save disabled */ && api("/api/db/reports/save",'
)

path.write_text(text, encoding="utf-8")

print("DONE: frontend DB save disabled.")
