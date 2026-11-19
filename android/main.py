"""OBD Pro for Android (Kivy). Reuses the desktop app's diagnostic core (obdpro.*) unchanged:
adapter profiles, generic OBD-II, VW Group modules, Hyundai/Kia and Renault discovery, reports."""
import os
import threading
import time
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex as hexc, platform

BG, CARD, TEXT, MUTED = hexc("#111214"), hexc("#1C1D21"), hexc("#F2F2F7"), hexc("#8E8E93")
ACCENT, GREEN, ORANGE, RED, YELLOW = hexc("#0A84FF"), hexc("#30D158"), hexc("#FF9F0A"), hexc("#FF453A"), hexc("#FFD60A")
Window.clearcolor = BG
HERE = os.path.dirname(os.path.abspath(__file__))


def setup_storage(app):
    """Point the core's JSON store / logs at the app's private folder."""
    d = app.user_data_dir
    os.environ["XDG_CONFIG_HOME"] = d
    os.environ["HOME"] = d


def request_android_permissions():
    if platform != "android":
        return
    from android.permissions import Permission, request_permissions   # noqa
    perms = [Permission.ACCESS_FINE_LOCATION]
    for name in ("BLUETOOTH_SCAN", "BLUETOOTH_CONNECT"):
        if hasattr(Permission, name):
            perms.append(getattr(Permission, name))
    request_permissions(perms)


# ---------------------------------------------------------------- widgets
def lbl(text="", size=15, color=TEXT, bold=False, halign="left", **kw):
    w = Label(text=text, font_size=sp(size), color=color, bold=bold, halign=halign, valign="middle", markup=True, **kw)
    w.bind(width=lambda *_: setattr(w, "text_size", (w.width, None)))
    w.bind(texture_size=lambda *_: setattr(w, "height", max(dp(24), w.texture_size[1])))
    w.size_hint_y = None
    return w


def btn(text, on_press=None, color=None, **kw):
    b = Button(text=text, font_size=sp(15), size_hint_y=None, height=dp(48), background_normal="",
               background_color=color or CARD, color=TEXT, **kw)
    if on_press:
        b.bind(on_press=lambda *_: on_press())
    return b


def card(*children, padding=12, spacing=8):
    from kivy.graphics import Color, RoundedRectangle
    box = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(padding), spacing=dp(spacing))
    box.bind(minimum_height=box.setter("height"))
    with box.canvas.before:
        Color(*CARD)
        rr = RoundedRectangle(radius=[dp(14)])
    box.bind(pos=lambda *_: setattr(rr, "pos", box.pos), size=lambda *_: setattr(rr, "size", box.size))
    for c in children:
        box.add_widget(c)
    return box


def scroller():
    sv = ScrollView(do_scroll_x=False)
    col = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(12), spacing=dp(10))
    col.bind(minimum_height=col.setter("height"))
    sv.add_widget(col)
    return sv, col


def bg(fn, done=None, fail=None):
    def run():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            if fail:
                Clock.schedule_once(lambda *_: fail(str(e) or e.__class__.__name__))
            return
        if done:
            Clock.schedule_once(lambda *_: done(r))
    threading.Thread(target=run, daemon=True).start()


def alert(title, text):
    Popup(title=title, content=lbl(text), size_hint=(0.9, None), height=dp(260)).open()


def fault_popup(f, module, family):
    """What a fault means and what to check."""
    import webbrowser
    e = f.explain(module.name, family)
    box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    sv, col = scroller()
    col.add_widget(lbl(f"[b]{e.title}[/b]", 17))
    col.add_widget(lbl(e.code_line, 13, MUTED))
    for fl in e.flags:
        hot = fl.startswith(("Failing", "Requests"))
        col.add_widget(lbl(("• " if hot else "· ") + fl, 14, ORANGE if hot else MUTED))
    col.add_widget(lbl("[b]What it means[/b]", 15))
    col.add_widget(lbl(e.meaning, 14))
    col.add_widget(lbl("[b]What to check[/b]", 15))
    for i, c in enumerate(e.checks, 1):
        col.add_widget(lbl(f"{i}.  {c}", 14))
    box.add_widget(sv)
    pop = Popup(title=f.code, content=box, size_hint=(0.95, 0.9))
    box.add_widget(btn(f"Look up the exact part for {f.dtc if f.powertrain else f.raw}",
                       lambda: webbrowser.open(e.lookup_url), color=ACCENT))
    box.add_widget(btn("Close", pop.dismiss))
    pop.open()


class FaultTestPopup(Popup):
    """Guided Fault Test: the module's fault memory is read live while the user operates the system."""

    def __init__(self, s, module, on_done=None):
        from obdpro import fault_info
        self.s, self.module, self.on_done, self.test = s, module, on_done, None
        self.box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        super().__init__(title=f"Fault Test · {module.name}", content=self.box, size_hint=(0.95, 0.92),
                         auto_dismiss=False)
        self.steps = fault_info.test_steps(module.name)
        self._intro()

    def _intro(self):
        self.box.clear_widgets()
        sv, col = scroller()
        col.add_widget(lbl(f"Many faults only show up while the part is working — like an A/C fault that appears once "
                           f"the A/C runs. The app watches {self.module.name} live while you go through the steps; any "
                           f"fault pops up the moment the module detects it.", 14, MUTED))
        col.add_widget(lbl("[b]You'll be asked to[/b]", 15))
        for i, (t, _d) in enumerate(self.steps, 1):
            col.add_widget(lbl(f"{i}. {t}", 14))
        self.box.add_widget(sv)
        self.box.add_widget(btn("Clear stored faults, then start", lambda: self._start(True), color=ACCENT))
        self.box.add_widget(btn("Start without clearing", lambda: self._start(False)))
        self.box.add_widget(btn("Close", self.dismiss))

    def _start(self, clear_first):
        from obdpro.fault_test import FaultTest
        self.test = FaultTest(self.s.tool, self.module, clear_first,
                              on_change=lambda: Clock.schedule_once(lambda *_: self._render()))
        self.test.start()
        self._render()

    def _render(self):
        t = self.test
        if t is None:
            return
        self.box.clear_widgets()
        sv, col = scroller()
        if t.phase in ("preparing", "clearing"):
            col.add_widget(lbl("Clearing stored faults…" if t.phase == "clearing" else f"Connecting to {self.module.name}…", 16))
        elif t.phase == "error":
            col.add_widget(lbl(t.error, 16, ORANGE))
        elif t.phase == "watching":
            st, de = t.steps[t.step]
            col.add_widget(lbl(f"Step {t.step + 1} of {len(t.steps)}   ·   [color=#30D158]•[/color] watching live ({t.reads})", 13, MUTED))
            col.add_widget(lbl(f"[b]{st}[/b]", 22))
            if de:
                col.add_widget(lbl(de, 14, MUTED))
        else:
            if t.hits:
                col.add_widget(lbl(f"[b]{len(t.hits)} fault{'s' if len(t.hits) != 1 else ''} appeared[/b]", 20, ORANGE))
            else:
                col.add_widget(lbl("[b]No faults appeared[/b]", 20, GREEN))
                col.add_widget(lbl(f"{self.module.name} worked through every step without detecting a fault "
                                   f"({t.reads} live checks).", 14, MUTED))
        if t.note:
            col.add_widget(lbl(t.note, 12, ORANGE))
        fam = self.s.family
        for h in t.hits:
            e = h.fault.explain(self.module.name, fam)
            b = btn(f"[b]! {h.fault.code}[/b]  {e.headline}\n[color=#8E8E93]at step {h.step + 1}: {t.steps[h.step][0]}[/color]",
                    lambda ff=h.fault: fault_popup(ff, self.module, fam), color=hexc("#3A2A12"))
            b.markup, b.halign, b.height = True, "left", dp(70)
            b.bind(width=lambda w, *_: setattr(w, "text_size", (w.width - dp(20), None)))
            col.add_widget(b)
        hit = {h.fault.code for h in t.hits}
        for f in t.before:
            if f.code not in hit:
                b = btn(f"Stored before: {f.code}  {f.explain(self.module.name, fam).headline}",
                        lambda ff=f: fault_popup(ff, self.module, fam))
                b.color = MUTED
                col.add_widget(b)
        self.box.add_widget(sv)
        if t.phase == "watching":
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
            back = btn("Back", t.back)
            back.disabled = t.step == 0
            last = t.step + 1 >= len(t.steps)
            row.add_widget(back)
            row.add_widget(btn("Finish" if last else "Done — next", t.finish if last else t.next, color=ACCENT))
            self.box.add_widget(row)
        elif not t.running:
            self.box.add_widget(btn("Test again", self._intro))
        self.box.add_widget(btn("Stop & close" if t.running else "Close", self._close))

    def _close(self):
        t = self.test
        if t and t.running:
            t.finish()
        self.dismiss()
        if self.on_done and t:
            Clock.schedule_once(lambda *_: self.on_done(t.last), 1.0)


# ---------------------------------------------------------------- session (no Qt)
class Session:
    def __init__(self, app):
        from obdpro import features as F
        from obdpro.store import Store
        self.app = app
        self.store = Store()
        self.F = F
        self.elm = self.obd = self.tool = None
        self.state, self.detail = "idle", ""
        self.supported = set()
        self.vin = None
        self.values = {}
        self.oil = None
        self.polling = False
        self._stop = threading.Event()
        veh = self.store.get("vehicle", {}) or {}
        self.brand = veh.get("brand", "seat")
        self.model = veh.get("model", "")
        self.listeners = []

    @property
    def family(self):
        from obdpro import catalog
        return catalog.FAMILY.get(self.brand, "vag")

    def make_tool(self):
        from obdpro.hyundai import Hyundai
        from obdpro.vag import VAG
        return Hyundai(self.elm, self.family) if self.family in ("hyundai", "renault") else VAG(self.elm)

    def notify(self):
        for fn in list(self.listeners):
            Clock.schedule_once(lambda *_, f=fn: f())

    def connect(self, kind, arg):
        from obdpro import adapters as AD
        from obdpro.elm import ELM327
        from obdpro.obd import OBD
        self.disconnect()
        self.state, self.detail = "connecting", str(arg)
        self.notify()

        def work():
            if kind == "ble":
                from obdpro.transport import BLETransport
                t = BLETransport(arg)
            elif kind == "tcp":
                from obdpro.transport import TCPTransport
                t = TCPTransport(arg[0], int(arg[1]))
            else:
                from obdpro.sim import SimTransport
                t = SimTransport(arg)
            elm = ELM327(t)
            try:
                elm.initialize()
            except Exception:
                t.close()
                raise
            o = OBD(elm)
            return elm, o, o.supported_pids()

        def done(r):
            self.elm, self.obd, self.supported = r
            self.tool = self.make_tool()
            name = {"ble": "Bluetooth adapter", "tcp": "Wi-Fi adapter", "sim": f"Demo {arg}"}.get(kind, kind)
            AD.remember(self.store, kind, arg, name, self.elm.profile)
            self.F.set_setting(self.store, "last_conn", [kind, list(arg) if isinstance(arg, tuple) else arg])
            self.state = "connected"
            self.detail = f"{self.elm.profile.chip} · {self.elm.protocol_name}"
            self.notify()
            bg(lambda: self.obd.mode09(0x02), self._got_vin)
            self.start_poll()

        def fail(m):
            self.state, self.detail = "failed", m
            self.notify()

        bg(work, done, fail)

    def _got_vin(self, vin):
        from obdpro import catalog
        self.vin = vin
        if vin and catalog.WMI.get(vin[:3].upper()):
            b = catalog.WMI[vin[:3].upper()]
            if b != self.brand:
                self.set_vehicle(b, catalog.BRANDS[b][2][0][0])
        self.notify()

    def set_vehicle(self, brand, model):
        self.brand, self.model = brand, model
        self.store.set("vehicle", {"brand": brand, "model": model})
        if self.elm:
            self.tool = self.make_tool()

    def disconnect(self):
        self._stop.set()
        if self.elm:
            try:
                self.elm.close()
            except Exception:
                pass
        self.elm = self.obd = self.tool = None
        if self.state != "idle":
            self.state, self.detail = "idle", ""
            self.notify()

    def start_poll(self):
        self._stop = threading.Event()
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        from obdpro import pids
        from obdpro.elm import ELMError
        from obdpro.vag import MODULE_BY_ADDR, numeric
        ids = [p for p in (0x0C, 0x0D, 0x05, 0x0F, 0x11, 0x04, 0x42, 0x2F) if not self.supported or p in self.supported]
        cycle = 0
        while not self._stop.is_set():
            if not self.polling or not self.elm:
                time.sleep(0.2)
                continue
            try:
                with self.elm.lock:
                    v = self.obd.read(ids)
                    if 0x42 not in v and cycle % 20 == 0:
                        bv = self.elm.battery_voltage()
                        if bv is not None:
                            v["volts_adapter"] = bv
                    if self.family == "vag" and self.tool and self.tool.supported and cycle % 10 == 0:
                        m = MODULE_BY_ADDR["01"]
                        with self.tool.channel(m):
                            try:
                                self.oil = numeric(self.F.VAG_PRESETS[0], self.tool.read_did(0x11BD))
                            except ELMError:
                                pass
                self.values.update(v)
                cycle += 1
                self.notify()
            except ELMError:
                pass
            except Exception as e:           # link lost
                self.state, self.detail = "failed", f"Connection lost: {e}"
                self.notify()
                return
            time.sleep(0.05)


# ---------------------------------------------------------------- screens
class ConnectScreen(Screen):
    def __init__(self, s, **kw):
        super().__init__(name="connect", **kw)
        self.s = s
        sv, col = scroller()
        self.add_widget(sv)
        col.add_widget(lbl("OBD Pro", 26, bold=True))
        self.status = lbl("Not connected", 17, MUTED, bold=True)
        self.detail = lbl("", 13, MUTED)
        self.disc = btn("Disconnect", s.disconnect, color=hexc("#3A1D1D"))
        col.add_widget(card(self.status, self.detail, self.disc))
        # BLE
        self.ble_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.ble_box.bind(minimum_height=self.ble_box.setter("height"))
        self.scan_btn = btn("Scan for Bluetooth adapters", self.scan, color=ACCENT)
        col.add_widget(card(lbl("Bluetooth LE", 17, bold=True), self.scan_btn, self.ble_box))
        # Wi-Fi
        st = s.store.get("settings", {}) or {}
        self.host = TextInput(text=st.get("host", "192.168.0.10"), multiline=False, size_hint_y=None, height=dp(44))
        self.port = TextInput(text=str(st.get("port", 35000)), multiline=False, input_filter="int", size_hint_y=None,
                              height=dp(44))
        col.add_widget(card(lbl("Wi-Fi adapter", 17, bold=True), self.host, self.port,
                            btn("Connect Wi-Fi", lambda: s.connect("tcp", (self.host.text.strip(), int(self.port.text or 35000))))))
        # My adapters
        self.my = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.my.bind(minimum_height=self.my.setter("height"))
        col.add_widget(card(lbl("My adapters", 17, bold=True), self.my))
        # Demo
        col.add_widget(card(lbl("Demo cars (no adapter needed)", 17, bold=True),
                            btn("Demo SEAT", lambda: s.connect("sim", "seat")),
                            btn("Demo Hyundai Grand i10", lambda: s.connect("sim", "hyundai")),
                            btn("Demo Renault Clio", lambda: s.connect("sim", "renault"))))
        s.listeners.append(self.refresh)
        self.refresh()

    def refresh(self):
        from obdpro import adapters as AD
        s = self.s
        col = {"connected": GREEN, "failed": RED, "connecting": YELLOW}.get(s.state, MUTED)
        self.status.text = {"idle": "Not connected", "connecting": "Connecting…", "connected": "Connected",
                            "failed": "Connection failed"}.get(s.state, s.state)
        self.status.color = col
        self.detail.text = s.detail
        self.disc.opacity = 1 if s.state in ("connected", "connecting") else 0
        self.my.clear_widgets()
        for a in AD.all_adapters(s.store)[:6]:
            arg = tuple(a["arg"]) if isinstance(a["arg"], list) else a["arg"]
            off = a.get("volt_offset")
            extra = f" · voltmeter {off:+.1f} V corrected" if off is not None and abs(off) >= 0.2 else ""
            self.my.add_widget(btn(f"{a['name']} — {a['chip']}{extra}", lambda k=a["kind"], g=arg: s.connect(k, g)))

    def scan(self):
        from obdpro.transport import scan_ble
        request_android_permissions()
        self.scan_btn.text = "Scanning…"
        self.ble_box.clear_widgets()

        def done(res):
            self.scan_btn.text = "Scan for Bluetooth adapters"
            if not res:
                self.ble_box.add_widget(lbl("No Bluetooth LE devices found", 14, MUTED))
            for addr, name, rssi in res[:12]:
                self.ble_box.add_widget(btn(f"{name}   {rssi} dBm", lambda a=addr: self.s.connect("ble", a)))

        def fail(m):
            self.scan_btn.text = "Scan for Bluetooth adapters"
            alert("Bluetooth", m)

        bg(lambda: scan_ble(6), done, fail)


class LiveScreen(Screen):
    ITEMS = [("RPM", 0x0C, "rpm", "{:.0f}"), ("Speed", 0x0D, "km/h", "{:.0f}"), ("Coolant", 0x05, "°C", "{:.0f}"),
             ("Intake air", 0x0F, "°C", "{:.0f}"), ("Throttle", 0x11, "%", "{:.0f}"), ("Load", 0x04, "%", "{:.0f}"),
             ("Battery", 0x42, "V", "{:.1f}"), ("Fuel", 0x2F, "%", "{:.0f}")]

    def __init__(self, s, **kw):
        super().__init__(name="live", **kw)
        self.s = s
        sv, col = scroller()
        self.add_widget(sv)
        col.add_widget(lbl("Live data", 24, bold=True))
        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        self.vals = {}
        for name, pid, unit, _ in self.ITEMS + [("Oil (SEAT/VW)", "oil", "°C", "{:.0f}")]:
            v = lbl("—", 30, TEXT, bold=True)
            grid.add_widget(card(lbl(name.upper(), 12, MUTED, bold=True), v, lbl(unit, 12, MUTED)))
            self.vals[pid] = v
        col.add_widget(grid)
        s.listeners.append(self.refresh)

    def on_enter(self, *a):
        self.s.polling = True

    def on_leave(self, *a):
        self.s.polling = False

    def refresh(self):
        for name, pid, unit, fmt in self.ITEMS:
            v = self.s.values.get(pid)
            if pid == 0x42 and v is None:
                v = self.s.values.get("volts_adapter")
            self.vals[pid].text = fmt.format(v) if v is not None else "—"
        self.vals["oil"].text = f"{self.s.oil:.0f}" if self.s.oil is not None else "—"


class VehicleScreen(Screen):
    def __init__(self, s, **kw):
        super().__init__(name="vehicle", **kw)
        from obdpro import catalog
        self.s = s
        self.reports = {}
        self.modules = []
        sv, col = scroller()
        self.add_widget(sv)
        col.add_widget(lbl("Vehicle", 24, bold=True))
        brands = list(catalog.BRANDS.keys())
        self.brand = Spinner(text=catalog.BRANDS.get(s.brand, ("SEAT",))[0], values=[catalog.BRANDS[b][0] for b in brands],
                             size_hint_y=None, height=dp(44))
        self.model = Spinner(text=s.model or "", values=[], size_hint_y=None, height=dp(44))
        self.brand.bind(text=lambda *_: self._brand_changed())
        self.model.bind(text=lambda *_: self._model_changed())
        self.vin = lbl("", 13, MUTED)
        col.add_widget(card(self.brand, self.model, self.vin))
        self.view = "side"
        self.img = Image(size_hint_y=None, height=dp(170), fit_mode="contain")
        self.img.bind(on_touch_down=lambda w, t: self._flip() if w.collide_point(*t.pos) else None)
        col.add_widget(card(self.img, lbl("Tap the car to switch side / front view", 12, MUTED, halign="center")))
        self.prog = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(8), opacity=0)
        self.note = lbl("", 13, MUTED)
        self.scan_btn = btn("Full Scan", self.scan, color=ACCENT)
        self.clear_btn = btn("Clear Faulty Modules", self.clear_faulty, color=hexc("#3A1D1D"))
        self.redisc = btn("Re-discover modules (≈2 min)", lambda: self.scan(True))
        col.add_widget(card(self.scan_btn, self.prog, self.note, self.clear_btn, self.redisc))
        self.list = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.list.bind(minimum_height=self.list.setter("height"))
        col.add_widget(self.list)
        self._fill_models(s.model)
        s.listeners.append(self._sync)

    def _brand_key(self):
        from obdpro import catalog
        return next((k for k, v in catalog.BRANDS.items() if v[0] == self.brand.text), "seat")

    def _fill_models(self, select=None):
        from obdpro import catalog
        models = [m for m, _ in catalog.BRANDS[self._brand_key()][2]]
        self.model.values = models
        self.model.text = select if select in models else models[0]

    def _brand_changed(self):
        self._fill_models()

    def _model_changed(self):
        self.s.set_vehicle(self._brand_key(), self.model.text)
        self.reports, self.modules = {}, []
        self._render()
        self._car()

    def _sync(self):
        from obdpro import catalog
        if self.s.vin:
            self.vin.text = f"VIN {self.s.vin}"
        if self.s.brand != self._brand_key():
            self.brand.text = catalog.BRANDS[self.s.brand][0]
            self._fill_models(self.s.model)
        self.redisc.opacity = 1 if self.s.family in ("hyundai", "renault") else 0

    def _shape_key(self):
        n, b = self.model.text.lower(), self._brand_key()
        for k, key in (("grand i10", "grandi10"), ("i10", "i10"), ("arona", "arona"), ("ibiza", "ibiza"), ("leon", "leon"),
                       ("león", "leon"), ("clio iv", "clio4"), ("clio", "clio5"), ("captur", "captur"), ("mégane", "megane"),
                       ("megane", "megane"), ("symbol", "symbol")):
            if k in n:
                return key
        from obdpro import catalog
        body = dict(catalog.BRANDS[b][2]).get(self.model.text, "hatch")
        return {"suv": "generic_suv", "van": "generic_suv", "sedan": "generic_sedan"}.get(body, "generic_hatch")

    def _car(self):
        self.img.source = os.path.join(HERE, "assets", "cars", f"{self._shape_key()}_{self.view}.png")

    def _flip(self):
        self.view = "front" if self.view == "side" else "side"
        self._car()

    def on_enter(self, *a):
        self._car()
        self._sync()

    def scan(self, rediscover=False):
        s = self.s
        if s.state != "connected" or not s.tool:
            return alert("Not connected", "Connect to an adapter (or a demo car) first.")
        if not s.tool.supported:
            return alert("Not supported", "Module scan needs a CAN car. Use Diagnose for generic codes.")
        self.prog.opacity, self.prog.value = 1, 0
        self.scan_btn.disabled = True
        from obdpro import features as F
        from obdpro.hyundai import module_for
        from obdpro.vag import MODULES

        def work():
            tool = s.tool
            if s.family in ("hyundai", "renault"):
                byvin = s.store.get("hy_modules_by_vin", {}) or {}
                known = byvin.get(s.vin or "")
                if known and not rediscover:
                    mods = [module_for(a, s.family) for a in known]
                else:
                    self._note("Searching for modules on the car…")
                    mods = tool.discover(lambda f, n: self._progress(f * 100, f"Searching… {n} found"))
                    byvin[s.vin or ""] = [m.address for m in mods]
                    s.store.set("hy_modules_by_vin", byvin)
            else:
                mods = list(MODULES)
            reps = {}
            for i, m in enumerate(mods):
                self._progress(100 * i / max(1, len(mods)), f"{m.name}")
                r = tool.report(m)
                if r.present:
                    F.record_faults(s.store, s.vin, m.address, [(f.code, f.state) for f in r.faults])
                reps[m.address] = r
            return mods, reps

        def done(r):
            self.modules, self.reports = r
            self.prog.opacity = 0
            self.scan_btn.disabled = False
            n = sum(len(x.faults) for x in self.reports.values())
            self.note.text = "No faults found" if n == 0 else f"{n} fault(s)"
            self._render()

        def fail(m):
            self.prog.opacity = 0
            self.scan_btn.disabled = False
            alert("Scan failed", m)

        bg(work, done, fail)

    @mainthread
    def _progress(self, v, text):
        self.prog.value = v
        self.note.text = text

    @mainthread
    def _note(self, text):
        self.note.text = text

    def _render(self):
        self.list.clear_widgets()
        reps = sorted((r for r in self.reports.values() if r.present), key=lambda r: (not r.faulty, r.module.address))
        for r in reps:
            col = ORANGE if r.faulty else GREEN
            txt = f"[b]{r.module.address} · {r.module.name}[/b]\n" + (f"{len(r.faults)} fault(s)" if r.faulty else "No faults")
            b = btn(txt, lambda rr=r: self.detail(rr))
            b.height = dp(62)
            b.color = col
            b.halign = "left"
            b.markup = True
            self.list.add_widget(b)

    def detail(self, r):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        sv, col = scroller()
        fam = self.s.family
        if not r.faults:
            col.add_widget(lbl("No faults stored", 15, GREEN))
        else:
            col.add_widget(lbl("Tap a fault for what it means and what to check.", 12, MUTED))
        for f in r.faults:
            e = f.explain(r.module.name, fam)
            b = btn(f"[b]{f.code}[/b]   {f.state}\n{e.headline}\n[color=#8E8E93]{e.code_line}[/color]",
                    lambda ff=f: fault_popup(ff, r.module, fam))
            b.markup, b.halign, b.height = True, "left", dp(84)
            b.bind(width=lambda w, *_: setattr(w, "text_size", (w.width - dp(20), None)))
            col.add_widget(b)
        if r.part:
            col.add_widget(lbl(f"Part number: {r.part}", 12, MUTED))
        box.add_widget(sv)
        pop = Popup(title=f"{r.module.address} · {r.module.name}", content=box, size_hint=(0.95, 0.85))

        def clear():
            pop.dismiss()
            self._clear([r])

        def test():
            pop.dismiss()
            FaultTestPopup(self.s, r.module, on_done=lambda last: self._after_test(r.module, last)).open()

        box.add_widget(btn("Fault Test — watch it live while you use it", test, color=ACCENT))
        if r.faults:
            box.add_widget(btn("Clear this module", clear, color=hexc("#3A1D1D")))
        box.add_widget(btn("Close", pop.dismiss))
        pop.open()

    def _after_test(self, module, last):
        if last is None:
            return
        from obdpro import features as F
        from obdpro.vag import Report
        F.record_faults(self.s.store, self.s.vin, module.address, [(f.code, f.state) for f in last])
        old = self.reports.get(module.address)
        self.reports[module.address] = Report(module, True, list(last), getattr(old, "part", None),
                                              getattr(old, "system", None))
        self._render()

    def clear_faulty(self):
        self._clear([r for r in self.reports.values() if r.faulty])

    def _clear(self, reps):
        if not reps:
            return
        s = self.s
        from obdpro import features as F

        def work():
            errs = []
            for r in reps:
                try:
                    s.tool.clear(r.module)
                    F.record_clear(s.store, s.vin, r.module.address)
                except Exception as e:  # noqa: BLE001
                    errs.append(str(e))
                self.reports[r.module.address] = s.tool.report(r.module)
            return errs

        def done(errs):
            self._render()
            still = [x for x in self.reports.values() if x.faulty]
            msg = list(errs) + [f"{x.module.name}: {', '.join(f.code for f in x.faults if f.active) or 'codes'} came back "
                                f"(cause still present)" for x in still]
            if msg:
                alert("Clear result", "\n\n".join(msg))

        bg(work, done, lambda m: alert("Clear failed", m))


class DiagnoseScreen(Screen):
    def __init__(self, s, **kw):
        super().__init__(name="diagnose", **kw)
        self.s = s
        sv, col = scroller()
        self.add_widget(sv)
        col.add_widget(lbl("Generic OBD-II codes", 24, bold=True))
        self.btn = btn("Scan", self.scan, color=ACCENT)
        self.out = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.out.bind(minimum_height=self.out.setter("height"))
        col.add_widget(card(self.btn, lbl("Emissions codes from every engine/gearbox ECU, read and cleared per module.",
                                          13, MUTED)))
        col.add_widget(self.out)

    def scan(self):
        s = self.s
        if s.state != "connected":
            return alert("Not connected", "Connect first.")
        from obdpro.obd import ModuleReport

        def work():
            with s.elm.lock:
                return [ModuleReport(e, s.obd.dtcs_for(e)) for e in s.obd.discover_ecus()], s.obd.readiness()

        def done(r):
            reps, ready = r
            self.out.clear_widgets()
            if ready:
                self.out.add_widget(card(lbl(f"Check Engine light {'ON' if ready.mil_on else 'OFF'}", 16,
                                             ORANGE if ready.mil_on else GREEN, bold=True),
                                         lbl(" · ".join(f"{n}: {'✓' if c else '…'}" for n, sup, c in ready.monitors if sup), 12, MUTED)))
            for rep in reps:
                items = [lbl(f"[b]{rep.ecu.name}[/b]", 16)]
                if not rep.dtcs:
                    items.append(lbl("No codes", 14, GREEN))
                for d in rep.dtcs:
                    items.append(lbl(f"[b]{d.code}[/b] {d.kind} — {d.description}", 14))
                if rep.dtcs:
                    items.append(btn("Clear this module", lambda e=rep.ecu: self.clear(e), color=hexc("#3A1D1D")))
                self.out.add_widget(card(*items))

        bg(work, done, lambda m: alert("Scan failed", m))

    def clear(self, ecu):
        s = self.s

        def work():
            with s.elm.lock:
                s.obd.clear_for(ecu)
        bg(work, lambda _: self.scan(), lambda m: alert("Clear failed", m + "\n\nEngine OFF, ignition ON."))


class ReportScreen(Screen):
    def __init__(self, s, **kw):
        super().__init__(name="report", **kw)
        self.s = s
        sv, col = scroller()
        self.add_widget(sv)
        col.add_widget(lbl("Full scan report", 24, bold=True))
        self.btn = btn("Run full scan", self.run, color=ACCENT)
        self.prog = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(8), opacity=0)
        self.status = lbl("", 13, MUTED)
        col.add_widget(card(self.btn, self.prog, self.status))
        self.out = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.out.bind(minimum_height=self.out.setter("height"))
        col.add_widget(self.out)

    @mainthread
    def _p(self, pct, msg):
        self.prog.value, self.status.text = pct, msg

    def run(self):
        s = self.s
        if s.state != "connected":
            return alert("Not connected", "Connect first.")
        from obdpro import report
        self.prog.opacity = 1
        self.btn.disabled = True

        def done(r):
            self.prog.opacity = 0
            self.btn.disabled = False
            path = s.store.logs_dir() / f"report_{datetime.now():%Y-%m-%d_%H%M}.html"
            try:
                path.write_text(report.to_html(r), encoding="utf-8")
                self.status.text = f"Saved: {path}"
            except OSError:
                pass
            self.render(r)

        def fail(m):
            self.prog.opacity = 0
            self.btn.disabled = False
            alert("Report failed", m)

        bg(lambda: report.build(s.elm, self._p, s.family), done, fail)

    def render(self, r):
        self.out.clear_widgets()
        n = sum(len(m["faults"]) for m in r["modules"]) + sum(len(c) for _, c in r.get("obd", []))
        self.out.add_widget(card(lbl("No faults found" if n == 0 else f"{n} fault(s)", 20, GREEN if n == 0 else ORANGE, bold=True),
                                 lbl(f"VIN {r.get('vin') or '—'}", 13, MUTED),
                                 lbl(f"Odometer {r.get('odometer') or '—'} · Battery "
                                     f"{(str(round(r['battery'], 1)) + ' V') if r.get('battery') else '—'}", 13, MUTED)))
        for k, v in r.get("notes", []):
            self.out.add_widget(card(lbl(f"[b]{k}:[/b] {v}", 14)))
        rows = [lbl(f"{'[color=#FF9F0A]' if m['faults'] else '[color=#30D158]'}•[/color] {m['address']} · {m['name']} — "
                    f"{len(m['faults'])} fault(s)" if m["faults"] else f"[color=#30D158]•[/color] {m['address']} · {m['name']} — OK", 14)
                for m in r["modules"] if m["present"]]
        if rows:
            self.out.add_widget(card(lbl("Modules", 17, bold=True), *rows))
        for m in r["modules"]:
            if m["faults"]:
                self.out.add_widget(card(lbl(f"[b]{m['address']} · {m['name']}[/b]", 15),
                                         *[lbl(f"[b]{c}[/b] {st} — {d}\n[color=#8E8E93]{t}[/color]", 13) for c, st, d, t in m["faults"]]))
        snap = [lbl(f"{k}: [b]{v}[/b]", 13) for k, v in r.get("snapshot", [])]
        if snap:
            self.out.add_widget(card(lbl("Live snapshot", 17, bold=True), *snap))


class Root(BoxLayout):
    def __init__(self, s, **kw):
        super().__init__(orientation="vertical", **kw)
        self.sm = ScreenManager(transition=NoTransition())
        for scr in (ConnectScreen(s), LiveScreen(s), VehicleScreen(s), DiagnoseScreen(s), ReportScreen(s)):
            self.sm.add_widget(scr)
        self.add_widget(self.sm)
        nav = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(2))
        self.tabs = {}
        for name, title in (("connect", "Connect"), ("live", "Live"), ("vehicle", "Vehicle"), ("diagnose", "Diagnose"),
                            ("report", "Report")):
            b = Button(text=title, background_normal="", background_color=CARD, color=MUTED, font_size=sp(13))
            b.bind(on_press=lambda _b, n=name: self.go(n))
            nav.add_widget(b)
            self.tabs[name] = b
        self.add_widget(nav)
        self.go("connect")

    def go(self, name):
        self.sm.current = name
        for n, b in self.tabs.items():
            b.color = ACCENT if n == name else MUTED


class OBDProApp(App):
    title = "OBD Pro"

    def build(self):
        try:
            setup_storage(self)
        except Exception:
            pass
        try:
            request_android_permissions()
        except Exception:
            pass
        try:
            self.session = Session(self)
            return Root(self.session)
        except Exception:
            import traceback
            tb = traceback.format_exc()
            try:
                with open(os.path.join(self.user_data_dir, "crash.txt"), "w") as f:
                    f.write(tb)
            except Exception:
                pass
            return self._error_view("Startup error", tb)

    def _error_view(self, title, tb):
        sv = ScrollView()
        lab = Label(text="[b]%s[/b]\n\n%s" % (title, tb), markup=True, font_size=sp(12), size_hint_y=None,
                    halign="left", color=TEXT, padding=(dp(12), dp(12)))
        lab.bind(width=lambda *_: setattr(lab, "text_size", (lab.width - dp(24), None)))
        lab.bind(texture_size=lambda *_: setattr(lab, "height", lab.texture_size[1]))
        sv.add_widget(lab)
        return sv

    def on_stop(self):
        try:
            self.session.disconnect()
        except Exception:
            pass


def main():
    try:
        OBDProApp().run()
    except Exception:
        import traceback
        from kivy.base import runTouchApp
        tb = traceback.format_exc()
        sv = ScrollView()
        lab = Label(text="[b]Fatal error[/b]\n\n" + tb, markup=True, font_size=sp(12), size_hint_y=None,
                    halign="left", color=TEXT, padding=(dp(12), dp(12)))
        lab.bind(width=lambda *_: setattr(lab, "text_size", (lab.width - dp(24), None)))
        lab.bind(texture_size=lambda *_: setattr(lab, "height", lab.texture_size[1]))
        sv.add_widget(lab)
        runTouchApp(sv)


if __name__ == "__main__":
    main()
