"""Fault explanations from what the module actually reports, plus guided Fault Test steps.

- VW fault number = the 3-byte UDS DTC in decimal (the number VCDS / OBDeleven / ODIS show)
- failure type byte (SAE J2012-DA) -> exact failure ("Actuator stuck", "Open circuit", ...)
- status byte (ISO 14229) -> active now / this drive / confirmed / warning lamp
- which system the module is -> parts behind it and how to exercise it.
VW's own per-number text is in VW's licensed label database, not on the car; the lookup link searches the number.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from . import dtc_db

FTB = {
    0x00: "No sub-type information", 0x01: "General electrical failure", 0x02: "General signal failure",
    0x03: "FM / PWM failure", 0x04: "System internal failure", 0x05: "System programming failure",
    0x06: "Algorithm-based failure", 0x07: "Mechanical failure", 0x08: "Bus signal / message failure",
    0x09: "Component failure",
    0x11: "Circuit short to ground", 0x12: "Circuit short to battery", 0x13: "Circuit open",
    0x14: "Circuit short to ground or open", 0x15: "Circuit short to battery or open",
    0x16: "Circuit voltage below threshold", 0x17: "Circuit voltage above threshold",
    0x18: "Circuit current below threshold", 0x19: "Circuit current above threshold",
    0x1A: "Circuit resistance below threshold", 0x1B: "Circuit resistance above threshold",
    0x1C: "Circuit voltage out of range", 0x1D: "Circuit current out of range",
    0x1E: "Circuit resistance out of range", 0x1F: "Circuit intermittent",
    0x21: "Signal amplitude below minimum", 0x22: "Signal amplitude above maximum",
    0x23: "Signal stuck low", 0x24: "Signal stuck high", 0x25: "Signal shape / waveform failure",
    0x26: "Signal rate of change below threshold", 0x27: "Signal rate of change above threshold",
    0x28: "Signal bias level out of range / zero adjustment failure", 0x29: "Signal invalid",
    0x2A: "Signal stuck in range", 0x2B: "Signal cross-coupled", 0x2F: "Signal erratic",
    0x31: "No signal", 0x32: "Signal low time below minimum", 0x33: "Signal low time above maximum",
    0x34: "Signal high time below minimum", 0x35: "Signal high time above maximum",
    0x36: "Signal frequency too low", 0x37: "Signal frequency too high", 0x38: "Signal frequency incorrect",
    0x39: "Too few pulses", 0x3A: "Too many pulses",
    0x41: "General checksum failure", 0x42: "General memory failure", 0x43: "Special memory failure",
    0x44: "Data memory failure", 0x45: "Program memory failure", 0x46: "Calibration / parameter memory failure",
    0x47: "Watchdog / safety processor failure", 0x48: "Supervision software failure",
    0x49: "Internal electronic failure", 0x4A: "Incorrect component installed", 0x4B: "Over temperature",
    0x51: "Not programmed", 0x52: "Not activated", 0x53: "Deactivated", 0x54: "Missing calibration",
    0x55: "Not configured (coding)", 0x56: "Invalid / incompatible configuration",
    0x57: "Invalid / incompatible software component",
    0x61: "Signal calculation failure", 0x62: "Signal compare failure", 0x63: "Circuit / component protection time-out",
    0x64: "Signal plausibility failure", 0x65: "Signal has too few transitions / events",
    0x66: "Signal has too many transitions / events", 0x67: "Signal incorrect after event", 0x68: "Event information",
    0x71: "Actuator stuck", 0x72: "Actuator stuck open", 0x73: "Actuator stuck closed", 0x74: "Actuator slipping",
    0x75: "Emergency position not reachable", 0x76: "Wrong mounting position", 0x77: "Commanded position not reachable",
    0x78: "Alignment or adjustment incorrect", 0x79: "Mechanical linkage failure", 0x7A: "Fluid leak or seal failure",
    0x7B: "Low fluid level",
    0x81: "Invalid serial data received", 0x82: "Alive / sequence counter incorrect",
    0x83: "Signal protection value incorrect", 0x84: "Signal below allowable range",
    0x85: "Signal above allowable range", 0x86: "Signal invalid", 0x87: "Missing message", 0x88: "Bus off",
    0x8F: "Erratic",
    0x91: "Parametric", 0x92: "Performance or incorrect operation", 0x93: "No operation",
    0x94: "Unexpected operation", 0x95: "Incorrect assembly", 0x96: "Component internal failure",
    0x97: "Component or system operation obstructed or blocked", 0x98: "Component or system over temperature",
}

CATEGORIES = {
    0x1: ("Electrical circuit",
          "A wire, connector or part in this circuit is shorted, open, or has the wrong voltage, current or resistance.",
          ["Unplug and inspect the connector of the part (corrosion, bent or pushed-back pins)",
           "Look along the wiring for chafing, breaks or water ingress",
           "Measure the part's resistance / supply voltage against spec"]),
    0x2: ("Signal",
          "The signal reaches the module but is wrong — stuck, out of range, erratic or invalid.",
          ["Check the sensor and its connector",
           "Compare the sensor's live value with reality (e.g. temperature vs. actual)",
           "Check grounds — a loose ground makes signals drift"]),
    0x3: ("Pulse / PWM signal",
          "A pulsed (PWM or frequency) signal has the wrong timing or pulse count.",
          ["Check the part driven or read by PWM (blower, fan, valve, speed sensor)", "Inspect its wiring and connector"]),
    0x4: ("Inside the control unit",
          "The control unit found a problem inside itself — memory, checksum, processor or internal electronics.",
          ["Clear it and re-test: one occurrence after low battery voltage or a jump-start is common",
           "Check battery voltage, and this module's fuse and ground",
           "If it returns immediately after clearing, the unit needs a software update or replacement"]),
    0x5: ("Programming / coding",
          "The unit's coding, calibration or software doesn't match the car (not coded, not activated, wrong configuration).",
          ["Was this module replaced or recoded recently?", "Check the coding matches the car's equipment",
           "Clear and re-test — some appear once after a battery disconnect"]),
    0x6: ("Plausibility",
          "The module compared signals and the result didn't make sense (two values disagree, or a value is impossible).",
          ["Check the sensors involved for drift or bad connections",
           "Scan the other modules — the bad signal may come from one of them"]),
    0x7: ("Mechanical / actuator",
          "A moving part (motor, flap, valve, pump) is stuck, blocked, slipping or can't reach its position.",
          ["Operate the function and listen for the motor / flap", "Check for obstruction or a broken linkage",
           "If the part was replaced, it must be calibrated (basic setting)"]),
    0x8: ("Communication",
          "A message from another module is missing or invalid, or the CAN bus dropped out.",
          ["Scan the other modules — the sender may have its own fault",
           "Very common after a flat battery, jump-start or battery change: clear and re-test",
           "If it returns: check CAN wiring and connectors of the sending module"]),
    0x9: ("Component performance",
          "The part is electrically fine but doesn't perform correctly (no operation, wrong operation, overheating).",
          ["Test the part's function directly", "Check for overheating, blockage or wear"]),
}
_GENERAL = ("General", "The module stored the fault without a more specific failure type.",
            ["Run the Fault Test to see when it appears", "Check this module's power, ground and connectors"])


def category(ftb: int):
    # 0x01-0x09 are the "general" form of each group (0x04 = general internal failure -> group 4).
    return CATEGORIES.get(ftb if 0x01 <= ftb <= 0x09 else ftb >> 4, _GENERAL)


def ftb_text(ftb: int) -> str:
    return FTB.get(ftb) or f"{category(ftb)[0]} fault (type {ftb:02X})"


def flags(status: int) -> list[str]:
    out = []
    if status & 0x01:
        out.append("Failing right now")
    if status & 0x02:
        out.append("Failed during this ignition cycle")
    if status & 0x08:
        out.append("Confirmed and stored")
    elif status & 0x04:
        out.append("Pending — seen once, not yet confirmed")
    if not status & 0x01 and status & 0x08:
        out.append("Not present now (intermittent or already fixed)")
    if status & 0x80:
        out.append("Requests the warning light")
    return out


# ---------------------------------------------------------------- systems
def system_kind(name: str) -> str:
    n = name.lower()

    def has(*k):
        return any(x in n for x in k)

    for kind, keys in (("engine", ("engine", "uce")), ("transmission", ("transmission", "gearbox", "tcu", "bva")),
                       ("brakes", ("abs", "brake", "esc", "esp")), ("column", ("steering column",)),
                       ("steering", ("steering", "mdps", "dae")), ("climate", ("air cond", "climat")),
                       ("airbag", ("airbag", "srs")), ("cluster", ("instrument", "cluster", "tdb")),
                       ("gateway", ("gateway",)), ("infotainment", ("infotainment", "audio", "radio", "multimedia", "head unit")),
                       ("door", ("door",)), ("tyres", ("tyre", "tpms")), ("parking", ("parking",)),
                       ("key", ("smart key", "immobil", "keyless", "hands-free")),
                       ("body", ("central electrics", "body", "bcm", "uch", "ipm"))):
        if has(*keys):
            return kind
    return "generic"


COMPONENTS = {
    "engine": "Sensors (air mass/pressure, coolant temp, oxygen, cam/crank), ignition coils, injectors, throttle body, fuel pump.",
    "transmission": "Gear selector, input/output speed sensors, shift solenoids, fluid temperature sensor, clutch actuators.",
    "brakes": "4 wheel-speed sensors, ABS pump & valve block, brake light switch, brake pressure sensor, steering-angle and yaw signals.",
    "steering": "Steering torque sensor, steering angle sensor, power-steering motor.",
    "column": "Steering angle sensor, clock spring, steering-wheel buttons, indicator and wiper stalks, horn.",
    "climate": "Blower motor & its regulator, refrigerant pressure/temperature sensor, flap motors (temperature, air distribution, "
               "recirculation), compressor regulating valve, cabin/evaporator temperature sensors, sunlight sensor.",
    "body": "Exterior lights & bulbs, wipers, central locking, windows, horn, interior lights, heated screens.",
    "airbag": "Airbag igniters, seat-belt pretensioners, crash sensors, seat occupancy sensor, connectors under the front seats, clock spring.",
    "cluster": "Instrument cluster, fuel level sender, oil level/temperature sensor, washer fluid level, door/handbrake switches.",
    "gateway": "The link between all modules — it stores communication faults and collects faults from other modules (often after low battery).",
    "infotainment": "Radio/navigation unit, antennas, USB/Bluetooth, speakers, display, microphone, reverse camera.",
    "door": "Window motor, door lock, mirror motor & heater, door switches and handle sensors.",
    "tyres": "Tyre pressure sensors in each wheel, receiver/antenna.",
    "parking": "Parking sensors in the bumpers, buzzer/display, reverse signal.",
    "key": "Key/card antennas, immobilizer coil, door handle sensors, start button.",
    "generic": "The sensors and actuators connected to this module.",
}

_P = "Have a passenger hold the phone / laptop."
STEPS = {
    "climate": [("Start the engine", "The compressor and its sensors are only tested with the engine running."),
                ("A/C ON, fan to maximum", "Leave it running for about 30 seconds."),
                ("Temperature to coldest, then hottest", "The temperature flap motor travels end to end. Wait ~10 s at each end."),
                ("Air distribution: windscreen → face → feet", "Tests the distribution flap motors. Pause on each one."),
                ("Recirculation on, then off", "Tests the fresh-air / recirculation flap."),
                ("Fan speed 1 → max → 1", "Tests the blower and its regulator at every speed."),
                ("Front / rear demist on, then off", "Skip if the car doesn't have it."),
                ("AUTO for one minute", "The unit now drives everything itself — just wait.")],
    "brakes": [("Start the engine", "The ABS pump and valves self-test when the engine starts."),
               ("Steering lock to lock", "Turn fully left, then fully right (steering-angle signal)."),
               ("Press the brake pedal firmly 3 times", "Tests the brake light switch and pressure sensor."),
               ("Drive slowly above 20 km/h", "Wheel speed sensors are only checked while moving. " + _P),
               ("Brake to a stop", "Normal, firm stop.")],
    "steering": [("Start the engine", "Power steering works only with the engine running."),
                 ("Steering lock to lock, standing still", "Slowly, twice."),
                 ("Drive slowly with a few turns", "Torque and angle sensors are checked while moving.")],
    "column": [("Ignition ON", ""), ("Indicators left, right, hazards", ""), ("Wipers: every speed + washer", "Front and rear."),
               ("Horn", ""), ("Steering-wheel buttons", "Press every button on the wheel (volume, phone, cruise…)."),
               ("Steering lock to lock", "Tests the steering-angle sensor and clock spring.")],
    "engine": [("Start the engine and idle 1 minute", ""), ("Rev to ~3000 rpm three times", "Hold each rev for 2–3 seconds."),
               ("Turn on heavy loads", "A/C, headlights, rear demist on — the idle must stay steady."),
               ("Let it reach operating temperature", "Many sensor tests only run warm (coolant ~90 °C)."),
               ("Short drive with acceleration", _P)],
    "transmission": [("Start the engine, foot on the brake", ""),
                     ("Selector P → R → N → D, pause 3 s each", "Manual gearbox: press the clutch and go through the gears."),
                     ("Drive and let it shift through all gears", _P)],
    "body": [("Ignition ON", ""), ("Headlights: side, low, high, flash", ""), ("Indicators left, right, hazards", ""),
             ("Press the brake pedal", "Brake lights."), ("Reverse gear (engine off, clutch in)", "Reverse lights."),
             ("Wipers front and rear + washers", ""), ("Lock and unlock with the key", ""),
             ("Open and close each door", "Interior lights and door switches."), ("Horn and rear window heater", "")],
    "airbag": [("Ignition ON — don't unplug anything", "Never touch airbag connectors with the ignition on."),
               ("Slide both front seats fully forward and back", "Connectors under the seats are the most common cause."),
               ("Buckle and unbuckle every seat belt", ""), ("Steering lock to lock", "Tests the clock spring."),
               ("Wait 30 seconds", "The airbag unit finishes its self-test.")],
    "cluster": [("Ignition ON", "Watch for warning lights that stay on."), ("Start the engine", "Oil pressure, charging and level checks."),
                ("Press the trip / menu buttons", ""), ("Open and close a door, release the handbrake", "")],
    "gateway": [("Ignition OFF for 30 seconds", ""), ("Ignition ON, then start the engine", "The gateway checks it hears every module."),
                ("Use a few functions (lights, radio, A/C)", "")],
    "infotainment": [("Radio ON, change station", ""), ("Volume up and down", "Listen to every speaker."),
                     ("Connect phone Bluetooth / USB", ""), ("Navigation / reverse camera", "If fitted.")],
    "door": [("Ignition ON", ""), ("Window fully down and fully up", ""), ("Lock and unlock", ""),
             ("Mirror: move in all directions, fold if electric", ""), ("Rear demist on (mirror heater)", ""),
             ("Open and close the door", "")],
    "tyres": [("Drive above 25 km/h for a few minutes", "Tyre sensors only transmit while rolling.")],
    "parking": [("Ignition ON, engine running", ""), ("Select reverse", "Sensors activate."),
                ("Approach an obstacle slowly", "Every sensor should beep.")],
    "key": [("Lock and unlock with the key / card", ""), ("Start and stop the engine twice", "")],
    "generic": [("Ignition ON", ""), ("Start the engine", ""), ("Use every function of this system", ""), ("Short drive", _P)],
}


def test_steps(module_name: str) -> list[tuple[str, str]]:
    return STEPS[system_kind(module_name)]


@dataclass
class Explanation:
    title: str
    headline: str
    code_line: str
    meaning: str
    checks: list[str]
    flags: list[str]
    lookup_url: str


def explain(f, module_name: str, family: str = "vag") -> Explanation:
    """f: vag.Fault."""
    kind = system_kind(module_name)
    typ = ftb_text(f.ftb)
    cat_name, meaning, checks = category(f.ftb)
    sae = f.dtc if f.ftb == 0 else f"{f.dtc} {f.ftb:02X}"
    known = dtc_db.KNOWN.get(f.dtc) if f.powertrain else None
    if f.powertrain:
        title = known or f"{module_name}: {typ}"
        code_line = f"{sae} · VW {f.raw}" if family == "vag" else sae
    else:
        title = f"{module_name}: {typ}"
        code_line = f"VW {f.raw} · {sae}"
    if known:
        meaning = f"{known}. " + ("" if f.ftb == 0 else f"Failure type: {typ}. ") + meaning
    headline = known or ("General fault" if f.ftb == 0 else typ)
    brand = {"vag": "VCDS", "hyundai": "Hyundai", "renault": "Renault"}.get(family, "")
    q = f"{f.dtc} {module_name}" if f.powertrain and family != "vag" else \
        f"{brand} {sae if f.powertrain else f.raw} {module_name}"
    return Explanation(title, headline, code_line, meaning,
                       checks + [f"Parts behind this module: {COMPONENTS[kind]}"], flags(f.status),
                       "https://www.google.com/search?q=" + quote_plus(q))
