"""Full vehicle scan report (VCDS/OBDeleven-style auto-scan) → structured dict + standalone HTML."""
from __future__ import annotations

import html
import time
from datetime import datetime

from . import catalog, pids
from .elm import ELM327, ELMError, to_hex
from .obd import OBD
from .vag import MODULES, STANDARD_DIDS, VAG

# Known VAG data identifiers confirmed on this platform (MQB-A0 1.6 MPI) — extend as more are found.
ENGINE_DIDS = {
    0x10E0: ("Odometer (engine)", lambda p: f"{int.from_bytes(bytes(p[-3:]), 'big'):,} km"),
    0x11BD: ("Oil temperature", lambda p: f"{(p[0] << 8 | p[1]) / 10 - 273.15:.1f} °C"),
    0x1063: ("Coolant temperature (engine)", lambda p: f"{(p[0] << 8 | p[1]) / 10 - 273.15:.1f} °C"),
}

# Modules that keep their own copy of the odometer (address → DID, 3-byte km at the end of the payload).
MILEAGE_SOURCES = {"01": (0x10E0, "Engine"), "5F": (0x02BD, "Infotainment")}

SNAPSHOT_PIDS = [0x0C, 0x0D, 0x05, 0x0F, 0x46, 0x04, 0x11, 0x42, 0x33, 0x2F, 0x06, 0x07, 0x1F, 0x21, 0x31, 0x4D, 0x4E]


def _clean(p: list[int]) -> str:
    q = list(p)
    while q and q[-1] in (0x00, 0xAA, 0xFF, 0x20):
        q.pop()
    if q and all(0x20 <= b <= 0x7E for b in q):
        return bytes(q).decode().strip()
    return to_hex(p)


def build(elm: ELM327, progress=lambda pct, msg: None) -> dict:
    o, v = OBD(elm), VAG(elm)
    r: dict = {"date": datetime.now().isoformat(timespec="seconds"), "adapter": elm.version,
               "protocol": elm.protocol_name, "modules": [], "notes": []}
    t0 = time.monotonic()
    with elm.lock:
        progress(2, "Vehicle identification")
        r["battery"] = None
        r["vin"] = o.mode09(0x02)
        r["cal_id"] = o.mode09(0x04)
        brand = catalog.WMI.get((r["vin"] or "")[:3].upper())
        r["brand"] = catalog.BRANDS[brand][0] if brand else None
        progress(6, "Readiness & live snapshot")
        sup = o.supported_pids()
        rd = o.readiness()
        r["mil"] = rd.mil_on if rd else None
        r["readiness"] = [(n, c) for n, s, c in rd.monitors if s] if rd else []
        snap = o.read([p for p in SNAPSHOT_PIDS if p in sup])
        # The car's own module voltage (PID 42) is accurate; cheap adapters' ATRV can read volts off.
        r["battery"] = snap.get(0x42) or elm.battery_voltage()
        r["snapshot"] = [(pids.BY_ID[k].name, f"{val:.1f} {pids.BY_ID[k].unit}") for k, val in snap.items()]
        progress(10, "Generic OBD-II codes")
        r["obd"] = []
        for ecu in o.discover_ecus():
            r["obd"].append((ecu.name, [(d.code, d.kind, d.description) for d in o.dtcs_for(ecu)]))
        r["vag"] = v.supported
        mods = MODULES if v.supported else []
        for i, m in enumerate(mods):
            progress(12 + int(80 * i / max(1, len(mods))), f"{m.address} · {m.name}")
            rep = v.report(m)
            entry = {"address": m.address, "name": m.name, "category": m.category, "present": rep.present,
                     "faults": [(f.code, f.state, f.description, f.detail) for f in rep.faults], "ident": [],
                     "coding": None, "extra": []}
            if rep.present:
                with v.channel(m):
                    for did, name in STANDARD_DIDS:
                        if did == 0x0600:
                            continue
                        try:
                            entry["ident"].append((name, _clean(v.read_did(did))))
                        except ELMError:
                            pass
                    try:
                        entry["coding"] = to_hex(v.read_did(0x0600))
                    except ELMError:
                        pass
                    if m.address == "01":
                        for did, (name, fmt) in ENGINE_DIDS.items():
                            try:
                                entry["extra"].append((name, fmt(v.read_did(did))))
                            except (ELMError, IndexError):
                                pass
                    if m.address in MILEAGE_SOURCES:
                        did, src = MILEAGE_SOURCES[m.address]
                        try:
                            p = v.read_did(did)
                            km = int.from_bytes(bytes(p[1:4]), "big") if len(p) >= 4 else None   # bytes 1..3
                            if km:
                                r.setdefault("mileage", []).append((src, km))
                                if m.address != "01":
                                    entry["extra"].append(("Odometer copy", f"{km:,} km"))
                        except ELMError:
                            pass
            r["modules"].append(entry)
        # crash / integrity notes
        ab = next((m for m in r["modules"] if m["address"] == "15"), None)
        if ab and ab["present"]:
            r["notes"].append(("Airbag", "No airbag faults stored — no deployment crash recorded in this module."
                               if not ab["faults"] else
                               f"Airbag module has {len(ab['faults'])} fault(s) — check for crash data stored."))
        miles = r.get("mileage", [])
        if len(miles) >= 2:
            lo, hi = min(k for _, k in miles), max(k for _, k in miles)
            srcs = ", ".join(f"{n} {k:,} km" for n, k in miles)
            r["notes"].append(("Mileage", f"Consistent across modules ({srcs}) — no sign of tampering."
                               if hi - lo <= 50 else
                               f"MISMATCH between modules ({srcs}) — difference {hi - lo:,} km. A module may have "
                               f"been swapped, or the odometer altered."))
        eng = next((m for m in r["modules"] if m["address"] == "01"), None)
        odo = next((x[1] for x in (eng or {}).get("extra", []) if x[0].startswith("Odometer")), None)
        if odo:
            r["odometer"] = odo
    r["duration"] = time.monotonic() - t0
    progress(100, "Done")
    return r


def to_html(r: dict) -> str:
    e = html.escape
    faulty = [m for m in r["modules"] if m["faults"]]
    present = [m for m in r["modules"] if m["present"]]
    n_faults = sum(len(m["faults"]) for m in r["modules"]) + sum(len(c) for _, c in r.get("obd", []))
    status_col = "#30D158" if n_faults == 0 else "#FF9F0A"
    rows = []
    for m in r["modules"]:
        if not m["present"]:
            rows.append(f"<tr class=na><td>{e(m['address'])}</td><td>{e(m['name'])}</td>"
                        f"<td colspan=2>Not fitted / no response</td></tr>")
            continue
        st = (f"<span class=bad>{len(m['faults'])} fault(s)</span>" if m["faults"] else "<span class=ok>OK</span>")
        ident = dict(m["ident"])
        rows.append(f"<tr><td><b>{e(m['address'])}</b></td><td>{e(m['name'])}<div class=sub>"
                    f"{e(ident.get('System Name', ''))}</div></td><td>{st}</td>"
                    f"<td class=mono>{e(ident.get('Spare Part Number', ''))}</td></tr>")
    details = []
    for m in present:
        ident = "".join(f"<tr><th>{e(k)}</th><td class=mono>{e(v)}</td></tr>" for k, v in m["ident"])
        if m["coding"]:
            ident += f"<tr><th>Coding</th><td class='mono wrap'>{e(m['coding'])}</td></tr>"
        ident += "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in m["extra"])
        faults = "".join(f"<tr><td class=mono><b>{e(c)}</b></td><td><span class='st {e(s.lower())}'>{e(s)}</span></td>"
                         f"<td>{e(d)}</td><td>{e(t)}</td></tr>" for c, s, d, t in m["faults"])
        details.append(
            f"<section class=card><h3>{e(m['address'])} · {e(m['name'])} "
            f"{'<span class=bad>● ' + str(len(m['faults'])) + ' fault(s)</span>' if m['faults'] else '<span class=ok>● OK</span>'}"
            f"</h3><table class=kv>{ident}</table>"
            + (f"<table class=faults><tr><th>Code</th><th>State</th><th>Description</th><th>Fault type</th></tr>{faults}</table>"
               if faults else "") + "</section>")
    obd = "".join(f"<tr><td>{e(n)}</td><td>" + ("<br>".join(f"<b class=mono>{e(c)}</b> {e(k)} — {e(d)}" for c, k, d in codes)
                                                 or "<span class=ok>No codes</span>") + "</td></tr>"
                  for n, codes in r.get("obd", []))
    ready = "".join(f"<span class='chip {'ok' if c else 'warn'}'>{e(n)}: {'complete' if c else 'incomplete'}</span>"
                    for n, c in r.get("readiness", []))
    snap = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in r.get("snapshot", []))
    notes = "".join(f"<li><b>{e(k)}:</b> {e(v)}</li>" for k, v in r.get("notes", []))
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Vehicle Report {e(r.get('vin') or '')}</title>
<style>
:root{{--bg:#0f1012;--card:#1b1c20;--line:#2a2b30;--text:#f2f2f7;--muted:#8e8e93}}
@media print{{:root{{--bg:#fff;--card:#fff;--line:#ddd;--text:#111;--muted:#555}} .card{{break-inside:avoid}}}}
body{{background:var(--bg);color:var(--text);font:14px/1.45 Inter,Segoe UI,Ubuntu,sans-serif;margin:0;padding:28px;max-width:1100px;margin:auto}}
h1{{font-size:28px;margin:0}} h2{{font-size:18px;margin:28px 0 10px}} h3{{margin:0 0 10px;font-size:16px}}
.sub{{color:var(--muted);font-size:12px}} .mono{{font-family:JetBrains Mono,DejaVu Sans Mono,monospace}} .wrap{{word-break:break-all}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:12px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}}
.stat b{{display:block;font-size:22px}} .stat span{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px}}
table{{width:100%;border-collapse:collapse}} td,th{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600;width:220px}} .faults th{{width:auto}}
tr.na td{{color:var(--muted)}} .ok{{color:#30D158;font-weight:600}} .bad{{color:#FF9F0A;font-weight:600}}
.st{{padding:2px 8px;border-radius:9px;font-size:12px;font-weight:600}} .st.active{{background:#4a1d1d;color:#FF453A}}
.st.stored{{background:#4a3a12;color:#FFD60A}} .st.pending,.st.intermittent{{background:#2a2b30;color:#aaa}}
.chip{{display:inline-block;padding:4px 10px;border-radius:10px;margin:3px;font-size:12px;background:#203a27}}
.chip.warn{{background:#4a3a12}} .banner{{border-left:5px solid {status_col}}}
</style></head><body>
<h1>{e(r.get('brand') or 'Vehicle')} diagnostic report</h1>
<div class=sub>{e(r['date'].replace('T', ' '))} · OBD Pro · adapter {e(r.get('adapter') or '')} · {e(r.get('protocol') or '')} · scan {r.get('duration', 0):.0f}s</div>
<div class="card banner"><b style="font-size:18px">{'No faults found' if n_faults == 0 else f'{n_faults} fault(s) in {len(faulty)} module(s)'}</b>
<div class=sub>{len(present)} modules responded · Check Engine light {'ON' if r.get('mil') else 'OFF'}</div></div>
<div class=grid>
<div class=stat><span>VIN</span><b class=mono style="font-size:15px">{e(r.get('vin') or '—')}</b></div>
<div class=stat><span>Odometer</span><b>{e(r.get('odometer') or '—')}</b></div>
<div class=stat><span>Battery</span><b>{f"{r['battery']:.1f} V" if r.get('battery') else '—'}</b></div>
<div class=stat><span>Faults</span><b class={'ok' if n_faults == 0 else 'bad'}>{n_faults}</b></div>
</div>
<h2>Modules</h2><div class=card><table><tr><th>Addr</th><th>Module</th><th>Status</th><th>Part number</th></tr>{''.join(rows)}</table></div>
{f'<h2>Notes</h2><div class=card><ul>{notes}</ul></div>' if notes else ''}
<h2>Generic OBD-II</h2><div class=card><table>{obd}</table><div style="margin-top:10px">{ready}</div></div>
<h2>Live snapshot</h2><div class=card><table class=kv>{snap}</table></div>
<h2>Module details</h2>{''.join(details)}
</body></html>"""
