import sys
from xml.sax.saxutils import escape

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/architecture.svg"

W, H = 1110, 1196
SANS = "Figtree, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "Consolas, 'Cascadia Mono', Menlo, monospace"

BG, CARD, EDGE = "#0b0b0b", "#171717", "#2e2e2e"
TEXT, TEXT2, MUTED = "#fafafa", "#a3a3a3", "#737373"
GOLD, GOLD_T = "#e0a93b", "#ffb84d"
PY, SQL, OUTC = "#7aa7ff", "#5fd3a8", "#ffb84d"
ARROW = "#8a8a8a"

BW, BH = 220, 92
LX, RX = 250, 900
ROW = [130, 280, 446, 596, 746, 896, 1046]
LINE_X = 720

out = []
def add(s): out.append(s)

def text(x, y, s, size=12.5, fill=TEXT2, weight=400, anchor="start", family=SANS, spacing=None, extra=""):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}"{ls}{extra}>{escape(s)}</text>')

def box(cx, top, tag, tag_color, name, l1, l2, gate=False, dashed=False):
    x = cx - BW / 2
    fill = "rgba(224,169,59,0.08)" if gate else CARD
    stroke = GOLD if gate else EDGE
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    add(f'<rect x="{x}" y="{top}" width="{BW}" height="{BH}" rx="12" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{1.5 if gate else 1}"{dash}/>')
    text(x + 16, top + 22, tag, size=10.5, fill=tag_color, weight=700, spacing="1.2")
    text(x + 16, top + 44, name, size=14, fill=TEXT, weight=700, family=MONO)
    text(x + 16, top + 64, l1)
    text(x + 16, top + 82, l2)

def marker(cx, top, n, shift=0):
    x, y = cx + BW / 2 - 4 - shift, top + 4
    add(f'<circle cx="{x}" cy="{y}" r="12" fill="{GOLD}" stroke="{BG}" stroke-width="3"/>')
    text(x, y + 4.5, str(n), size=12.5, fill="#171717", weight=800, anchor="middle")

def varrow(cx, top_row, label1, label2=None, color=ARROW, dashed=False):
    y1, y2 = ROW[top_row] + BH, ROW[top_row + 1]
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    mk = "ag" if color == GOLD else "a"
    add(f'<line x1="{cx}" y1="{y1 + 2}" x2="{cx}" y2="{y2 - 4}" stroke="{color}" stroke-width="2"{dash} marker-end="url(#{mk})"/>')
    mid = (y1 + y2) / 2
    if label2:
        text(cx + 14, mid - 3, label1, size=12, fill=TEXT2)
        text(cx + 14, mid + 13, label2, size=12, fill=MUTED)
    else:
        text(cx + 14, mid + 4, label1, size=12, fill=TEXT2)

add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
    f'aria-label="Sledge analytics pipeline: events are validated and loaded into SQL Server, a founder dashboard reads '
    f'the sensitive warehouse, and only five categorical, hashed fields cross the GA4 boundary through a separate low-privilege exporter.">')
add('<defs>'
    f'<marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    f'<path d="M0,0 L10,5 L0,10 z" fill="{ARROW}"/></marker>'
    f'<marker id="ag" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    f'<path d="M0,0 L10,5 L0,10 z" fill="{GOLD}"/></marker>'
    '</defs>')
add(f'<rect width="{W}" height="{H}" fill="{BG}"/>')

text(40, 46, "Sledge analytics pipeline", size=26, fill=TEXT, weight=800)
text(40, 72, "How a made-up construction app event becomes a founder dashboard number, and a GA4-safe event",
     size=14, fill=TEXT2)

text(40, 108, "INSIDE SLEDGE · FULL DETAIL", size=11.5, fill=MUTED, weight=700, spacing="1.6")
text(LINE_X + 30, 108, "MAY LEAVE SLEDGE · GA4-SAFE ONLY", size=11.5, fill=GOLD_T, weight=700, spacing="1.6")
add(f'<line x1="{LINE_X}" y1="92" x2="{LINE_X}" y2="{H - 40}" stroke="{GOLD}" stroke-width="2" '
    f'stroke-dasharray="9 7" opacity="0.85"/>')
text(LINE_X - 10, 440, "GA4 DATA BOUNDARY", size=11.5, fill=GOLD_T, weight=700, spacing="2", anchor="middle",
     extra=f' transform="rotate(-90 {LINE_X - 10} 440)"')

top_r, arm_top, bot = ROW[2] - 14, ROW[4] - 12, ROW[4] + BH + 14
add(f'<path d="M120,{top_r} H380 V{arm_top} H1030 V{bot} H120 Z" fill="rgba(43,127,255,0.05)" '
    f'stroke="rgba(122,167,255,0.5)" stroke-width="1.2" stroke-dasharray="6 5" stroke-linejoin="round"/>')
mid = (top_r + bot) / 2
text(108, mid, "SQL SERVER · TPM-05 · DATABASE poc", size=10.5, fill=PY, weight=700, spacing="1.2",
     anchor="middle", extra=f' transform="rotate(-90 108 {mid})"')

box(LX, ROW[0], "SOURCE", OUTC, "data/events.jsonl", "3,873 made-up app events", "amounts · names · tax IDs")
box(LX, ROW[1], "PYTHON", PY, "pipeline/load.py", "validates every event", "dedupes by event_id")
box(LX, ROW[2], "TABLE", SQL, "sledge_raw.events", "JSON exactly as received", "3,848 kept · 3 rejected")
box(LX, ROW[3], "TABLES", SQL, "sledge_core", "fact_event · dim_tenant · ref_*", "typed · cents · UTC")
box(LX, ROW[4], "VIEWS", SQL, "sledge_analytics", "weekly active · documents", "bill lifecycle · cycle time")
box(LX, ROW[5], "PYTHON · ADMIN LOGIN", PY, "dashboard/build.py", "last 12 complete weeks", "one self-contained page")
box(LX, ROW[6], "OUTPUT · FOUNDERS", OUTC, "out/dashboard.html", "13 active companies", "1,321 docs · 14.9 days")

varrow(LX, 0, "read line by line")
varrow(LX, 1, "one JSON array → OPENJSON", "malformed rows kept, flagged")
varrow(LX, 2, "T-SQL transform", "accepted rows only")
varrow(LX, 3, "views over the facts")
varrow(LX, 4, "SELECT as admin")
varrow(LX, 5, "writes HTML")

y = ROW[3] + BH / 2
add(f'<line x1="{LX + BW / 2 + 2}" y1="{y}" x2="{RX - BW / 2 - 4}" y2="{y}" stroke="{GOLD}" stroke-width="2.5" marker-end="url(#ag)"/>')
text((LX + BW / 2 + RX - BW / 2) / 2 - 10, y - 12, "reads action, module, surface, channel, tenant_id",
     size=12, fill=TEXT, anchor="middle")
text((LX + BW / 2 + RX - BW / 2) / 2 - 10, y + 22, "never reads amounts, names, tax IDs or times",
     size=12, fill=MUTED, anchor="middle")

box(RX, ROW[3], "PYTHON · THE GATE", GOLD_T, "pipeline/boundary.py", "allowlist + vocabularies", "tenant ID → HMAC-SHA256", gate=True)
box(RX, ROW[4], "TABLE · SAME DATABASE", SQL, "sledge_ga4.outbox", "4 codes + tenant_hash", "no $, names or times")
box(RX, ROW[5], "PYTHON · EXPORTER LOGIN", PY, "pipeline/ga4_export.py", "reads 7 safe columns only", "assert_safe on every line")
box(RX, ROW[6], "DESTINATION", OUTC, "Google Analytics 4", "action · module · surface", "channel · tenant_hash", dashed=True)

varrow(RX, 3, "4 codes + hashed tenant", color=GOLD)
varrow(RX, 4, "SELECT 7 safe columns", "column-level grant", color=GOLD)
varrow(RX, 5, "out/ga4_events.jsonl", "not sent in this POC", color=GOLD, dashed=True)

marker(RX, ROW[3], 2)
marker(RX, ROW[3], 1, shift=30)
marker(RX, ROW[4], 3)
marker(RX, ROW[5], 4)

cx0, cy0, cw, ch = 760, 128, 330, 412
add(f'<rect x="{cx0}" y="{cy0}" width="{cw}" height="{ch}" rx="14" fill="{CARD}" stroke="{EDGE}"/>')
text(cx0 + 20, cy0 + 34, "How the boundary is enforced", size=15.5, fill=TEXT, weight=700)
text(cx0 + 20, cy0 + 54, "Four independent checks. Any one stops a leak.", size=12, fill=MUTED)
items = [
    ("Allowlist, not blocklist", "builds a new object from 5 named fields;", "never copies the source event"),
    ("Closed vocabularies + keyed hash", "every value must be a known code;", "tenant ID is HMAC-SHA256, key stays in"),
    ("The outbox cannot hold a leak", "only code columns + 32-char hex hash;", "no $, durations, names or times"),
    ("The exporter cannot see secrets", "own login, SELECT on 7 safe columns,", "no access to raw, core or analytics"),
]
for i, (t, a, b) in enumerate(items):
    top = cy0 + 86 + i * 74
    add(f'<circle cx="{cx0 + 32}" cy="{top - 4}" r="11" fill="{GOLD}"/>')
    text(cx0 + 32, top + 0.5, str(i + 1), size=12, fill="#171717", weight=800, anchor="middle")
    text(cx0 + 54, top + 1, t, size=13, fill=TEXT, weight=700)
    text(cx0 + 54, top + 20, a, size=12)
    text(cx0 + 54, top + 37, b, size=12)
add(f'<line x1="{cx0 + 20}" y1="{cy0 + ch - 52}" x2="{cx0 + cw - 20}" y2="{cy0 + ch - 52}" stroke="{EDGE}"/>')
text(cx0 + 20, cy0 + ch - 28, "assert_safe re-checks every payload before", size=12, fill=TEXT2)
text(cx0 + 20, cy0 + ch - 11, "it is written · 12 tests guard all four", size=12, fill=TEXT2)

text(40, H - 14, "Sample data · SQL Server 2022 · Python 3 · pyodbc · see README.md for the data model", size=11.5, fill=MUTED)

add('</svg>')
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(out) + "\n")
print("wrote", OUT)
