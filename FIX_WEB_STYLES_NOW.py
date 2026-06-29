from pathlib import Path

path = Path("web/styles.css")

if not path.exists():
    raise SystemExit("ERROR: web/styles.css not found")

css = path.read_text(encoding="utf-8", errors="ignore")

patch = r'''

/* =========================================================
   OpsLens final records + incident grouping cleanup
   ========================================================= */

.record-card.backend-record {
  grid-template-columns: 1.25fr 0.75fr 0.55fr 0.85fr auto;
}

.record-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
}

.record-actions button,
.open-record-btn,
.download-record-btn {
  border: 0;
  border-radius: 4px;
  padding: 8px 11px;
  color: #ffffff;
  font-size: 12px;
  font-weight: 800;
  background: rgba(109,109,110,0.75);
}

.record-actions button:hover,
.open-record-btn:hover,
.download-record-btn:hover {
  background: var(--red);
}

.incident-grouping-card {
  grid-column: 1 / -1;
  border-color: rgba(229, 9, 20, 0.22);
  background:
    linear-gradient(135deg, rgba(229,9,20,0.12), rgba(20,20,20,0.98) 36%),
    #141414;
}

.section-title {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.section-title span {
  display: block;
  color: #ffffff;
  font-size: 22px;
  font-weight: 900;
  letter-spacing: -0.03em;
}

.section-title small {
  color: var(--muted);
  line-height: 1.45;
}

.incident-group-item {
  margin-top: 12px;
  padding: 14px;
  border-radius: 10px;
  background: rgba(0,0,0,0.28);
  border: 1px solid rgba(255,255,255,0.08);
}

.incident-group-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.incident-group-header strong {
  color: #ffffff;
}

.incident-group-header span {
  color: var(--muted);
  font-size: 13px;
}

.incident-signal-list {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.incident-signal-list li {
  padding: 10px 11px;
  border-radius: 8px;
  background: #101010;
  border: 1px solid var(--line);
}

.incident-signal-list strong {
  display: block;
  margin-bottom: 4px;
  color: #ffffff;
}

.incident-signal-list span {
  display: block;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
}

.opslens-export-report-picker {
  display: none !important;
}

@media (max-width: 1050px) {
  .record-card.backend-record {
    grid-template-columns: 1fr;
  }

  .record-actions {
    justify-content: flex-start;
  }

  .section-title,
  .incident-group-header {
    flex-direction: column;
  }
}
'''

if "OpsLens final records + incident grouping cleanup" not in css:
    css = css.rstrip() + "\n\n" + patch.strip() + "\n"

path.write_text(css, encoding="utf-8")

print("DONE: web/styles.css patched.")
