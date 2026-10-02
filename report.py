"""Render a single self-contained HTML report."""
import html
import datetime as dt

LABEL = {"rush": "Rushing yds", "rec": "Receiving yds", "pass": "Passing yds", "rr": "Rush+Rec yds"}

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a1d23;--mut:#6b7280;--line:#e5e7eb;--good:#0f7b4a;--bad:#b42318;--acc:#2456d6;--chip:#eef2ff}
@media(prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--ink:#e8eaee;--mut:#9aa3b2;--line:#272c36;--good:#4ade80;--bad:#f87171;--acc:#7aa2ff;--chip:#1f2640}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,system-ui,Segoe UI,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px}
.sub{color:var(--mut)}.banner{background:#fff4d6;color:#6b4e00;border-radius:8px;padding:10px 12px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.tabs{display:flex;gap:6px;margin:16px 0 10px;flex-wrap:wrap}.tabs button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:6px 12px;border-radius:999px;cursor:pointer;font:inherit}
.tabs select{margin-left:auto;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:6px 10px;border-radius:8px;font:inherit}
.tabs button.on{background:var(--acc);border-color:var(--acc);color:#fff}
table{width:100%;border-collapse:collapse}th,td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:12px;color:var(--mut);font-weight:600;cursor:pointer;user-select:none;background:var(--card);position:sticky;top:0}
th:first-child,td:first-child{text-align:left}tr:last-child td{border-bottom:0}.scroll{overflow-x:auto}
.pick{font-weight:600}.over{color:var(--good)}.under{color:var(--bad)}.pos{color:var(--good);font-weight:600}.mut{color:var(--mut);font-size:12px}
.chip{background:var(--chip);color:var(--acc);border-radius:6px;padding:1px 6px;font-size:12px;margin-left:4px}.q{color:#b45309}
.spark{display:inline-flex;align-items:flex-end;gap:2px;height:18px;vertical-align:middle}.spark i{width:5px;background:var(--acc);opacity:.7;border-radius:1px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}.stat{padding:12px 14px}.stat b{font-size:18px}
footer{margin-top:28px;color:var(--mut);font-size:12px}
"""

JS = """
let kind='all';
const sel=document.getElementById('game'),tabs=document.querySelectorAll('[data-tab]');
function apply(){document.querySelectorAll('tr[data-kind]').forEach(r=>r.style.display=
((kind==='all'||r.dataset.kind===kind)&&(sel.value==='all'||r.dataset.game===sel.value))?'':'none');}
tabs.forEach(b=>b.onclick=()=>{kind=b.dataset.tab;tabs.forEach(x=>x.classList.toggle('on',x===b));apply();});
sel.onchange=apply;
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const t=th.closest('table'),i=[...th.parentNode.children].indexOf(th),
rows=[...t.tBodies[0].rows],dir=th.dir=th.dir==='a'?'d':'a';
rows.sort((a,b)=>{const x=a.cells[i].dataset.v??a.cells[i].textContent,y=b.cells[i].dataset.v??b.cells[i].textContent,
n=parseFloat(x)-parseFloat(y);return(isNaN(n)?x.localeCompare(y):n)*(dir==='a'?1:-1)});rows.forEach(r=>t.tBodies[0].appendChild(r));});
"""


def spark(vals):
    if not vals:
        return ""
    m = max(max(vals), 1)
    return '<span class="spark">' + "".join(f'<i style="height:{max(2, v / m * 18):.0f}px" title="{v:.0f}"></i>' for v in vals) + "</span>"


def pct(x):
    return f"{x * 100:.1f}%"


def matchup(r):
    return f"{'vs' if r.home else '@'} {r.opp}"


def when(r):
    try:
        d = dt.date.fromisoformat(str(r.gameday)).strftime("%a")
    except Exception:
        d = ""
    return f"{d} {r.gametime}" if str(r.gametime) != "nan" else d


def picks_table(p):
    rows = []
    for r in p.itertuples():
        cls = "over" if r.side == "Over" else "under"
        st = f'<span class="q"> {html.escape(r.status)}</span>' if r.status else ""
        rows.append(
            f'<tr data-kind="{r.kind}" data-game="{r.game_id}"><td><span class="pick">{html.escape(r.name)}</span> <span class="mut">{r.pos} {r.team}</span>{st}<br>'
            f'<span class="mut">{matchup(r)} · {when(r)}</span></td>'
            f'<td>{LABEL[r.kind]}</td>'
            f'<td class="pick {cls}">{r.side} {r.line:g}<br><span class="mut">{r.odds:+d} · {html.escape(r.book)}</span></td>'
            f'<td data-v="{r.mu:.2f}">{r.mu:.0f}<br><span class="mut">±{r.sd:.0f}</span></td>'
            f'<td data-v="{r.edge_yds:.2f}">{r.edge_yds:+.1f}</td>'
            f'<td data-v="{r.p_model:.4f}">{pct(r.p_model)}<br><span class="mut">mkt {pct(r.p_mkt)}</span></td>'
            f'<td data-v="{r.ev:.4f}" class="pos">{r.ev * 100:+.1f}%</td>'
            f'<td data-v="{r.kelly:.4f}">{r.kelly * 100:.1f}%</td>'
            f'<td>{spark(r.last5)}</td></tr>')
    return ('<div class="card scroll"><table><thead><tr><th>Player</th><th>Market</th><th>Pick</th><th data-k>Proj</th>'
            '<th data-k title="Projection minus line, in the pick direction">Edge yds</th><th data-k>Win prob</th>'
            '<th data-k>EV</th><th data-k title="Quarter Kelly, % of bankroll">¼ Kelly</th><th>Last 5</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def proj_table(proj):
    rows = []
    for r in proj.sort_values("mu", ascending=False).itertuples():
        st = f'<span class="q"> {html.escape(r.status)}</span>' if r.status else ""
        rows.append(
            f'<tr data-kind="{r.kind}" data-game="{r.game_id}"><td><span class="pick">{html.escape(r.name)}</span> <span class="mut">{r.pos} {r.team}</span>{st}</td>'
            f'<td>{LABEL[r.kind]}</td><td>{matchup(r)}</td><td data-v="{r.mu:.2f}"><b>{r.mu:.0f}</b></td>'
            f'<td>±{r.sd:.0f}</td><td>{r.vol:.1f}</td><td>{r.eff:.2f}</td><td>{r.spread:+.1f}</td><td>{spark(r.last5)}</td></tr>')
    return ('<div class="card scroll"><table><thead><tr><th>Player</th><th>Market</th><th>Game</th><th data-k>Proj</th><th>SD</th>'
            '<th data-k>Volume</th><th data-k>Yds/att</th><th data-k>Spread</th><th>Last 5</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def game_label(gid):
    _, _, away, home = gid.split("_", 3)
    return f"{away} @ {home}"


def game_select(proj):
    games = proj.drop_duplicates("game_id").sort_values(["gameday", "gametime", "game_id"])
    opts = "".join(f'<option value="{g.game_id}">{game_label(g.game_id)} · {when(g)}</option>' for g in games.itertuples())
    return f'<select id="game" aria-label="Filter by game"><option value="all">All games</option>{opts}</select>'


def write(path, season, week, proj, picks, bt, var_params, demo=False):
    parts = [f'<h1>NFL Rush &amp; Receiving Yard Props</h1><div class="sub">{season} Week {week} · generated '
             f'{dt.datetime.now():%b %d, %Y %H:%M}</div>']
    if demo:
        parts.append('<div class="banner"><b>DEMO LINES.</b> Lines below are synthetic, generated near the projections, so the "edges" mean nothing. '
                     'Set <code>ODDS_API_KEY</code> or pass <code>--lines-csv</code> for real picks.</div>')
    elif picks is None:
        parts.append('<div class="banner">No prop lines supplied, so this is projections only. Set <code>ODDS_API_KEY</code> '
                     '(The Odds API) or pass <code>--lines-csv lines.csv</code> to get ranked picks.</div>')
    parts.append('<div class="tabs"><button class="on" data-tab="all">All</button><button data-tab="rush">Rushing</button>'
                 '<button data-tab="rec">Receiving</button>'
                 '<button data-tab="pass">Passing</button><button data-tab="rr">Rush+Rec</button>'
                 + game_select(proj) + '</div>')
    if picks is not None:
        parts.append("<h2>Best props</h2>")
        parts.append(picks_table(picks.head(40)) if len(picks) else '<div class="card stat">No plays clear the EV threshold.</div>')
    parts.append("<h2>All projections</h2>" + proj_table(proj))
    cards = "".join(
        f'<div class="card stat"><div class="mut">{LABEL[k]} backtest (n={v["n"]})</div><b>MAE {v["mae_model"]:.1f}</b> '
        f'<span class="mut">vs last-5 avg {v["mae_naive"]:.1f} · bias {v["bias"]:+.1f}</span></div>' for k, v in bt.items())
    parts.append(f"<h2>Model check</h2><div class='grid'>{cards}</div>")
    parts.append(
        "<footer>Yards = volume × efficiency, recency-weighted and shrunk to position means, adjusted for opponent and "
        "spread-based game script. Win probability uses a gamma outcome distribution fit from a walk-forward backtest, "
        "blended with the market's no-vig probability. EV assumes that blend is right; large edges usually mean the model is "
        "missing something (role change, injury to a teammate, weather). Bet responsibly.</footer>")
    with open(path, "w") as f:
        f.write(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                f"<title>NFL Prop Picks</title><style>{CSS}</style></head><body><div class='wrap'>{''.join(parts)}</div><script>{JS}</script></body></html>")
