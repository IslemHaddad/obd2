"""Built-in VAG service-function catalog (the thing a VCDS/ThinkDiag subscription normally provides):
named guided procedures — throttle adaptation, service reset, steering-angle calibration, ABS bleeding,
EPB service mode, battery registration — that run on the engine's existing RoutineControl / output /
adaptation primitives (run_basic_setting / run_output_test / write_did_verified).

Honesty: routine IDs differ by ECU/platform. Each function carries a `confidence` and the UI always
previews the exact UDS bytes and asks the user to confirm before anything is sent to the car. IDs marked
'common' are the widely-documented VAG values; 'template' means verify against your car (e.g. VCDS labels)
before use. Nothing here is fired automatically. Shared by the desktop and Android apps."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceFn:
    id: str
    name: str
    group: str                       # Engine · Brakes · Steering · Service · Battery · Comfort
    modules: tuple                   # applicable VAG module addresses; first is the default target
    summary: str
    kind: str                        # "routine" | "output" | "adaptation" | "procedure"
    spec: dict = field(default_factory=dict)   # engine-call params (see run_basic_setting / run_output_test)
    steps: tuple = ()                # plain-language steps shown to the user
    preconditions: tuple = ()
    caution: str = ""
    engine: str = "ignition"         # required engine state: off | ignition | running | any
    fuel: tuple = ()                 # restrict to these fuels (e.g. ("diesel",)); empty = any
    confidence: str = "common"       # verified | common | template

    def preview(self) -> str:
        """The exact UDS request(s) this function will send, as hex, for the confirm dialog."""
        s = self.spec
        if self.kind == "routine":
            rid = f"{s['routine']:04X}"
            return (f"Enter session 10 03\n"
                    f"Start   31 01 {rid} {s.get('data','')}\n"
                    f"Poll    31 03 {rid}\n"
                    f"Stop    31 02 {rid}").strip()
        if self.kind == "output":
            idh = f"{s['id']:04X}"
            if s.get("method") == "io":
                return f"Enter session 10 03\nStart  2F {idh} 03 {s.get('data','')}\nStop   2F {idh} 00"
            return f"Enter session 10 03\nStart  31 01 {idh} {s.get('data','')}\nStop   31 02 {idh}"
        if self.kind == "adaptation":
            return (f"Enter session 10 03\nRead   22 {s['did']:04X}\n"
                    f"Write  2E {s['did']:04X} <new value>\nVerify 22 {s['did']:04X}")
        return "Guided steps only — no automatic command is sent."


# ---- catalog -------------------------------------------------------------------------------------
# routine IDs below are the commonly-documented VAG values; the UI previews and confirms every one.
CATALOG: list[ServiceFn] = [
    ServiceFn(
        id="throttle_adapt", name="Throttle Body Adaptation", group="Engine", modules=("01",),
        summary="Re-learns the throttle valve's closed/open stops. Do after cleaning the throttle body "
                "or clearing throttle faults, or if idle is unstable.",
        kind="routine", spec={"routine": 0x0402, "timeout": 40, "done_offset": 0, "done_value": 0x02},
        steps=("Engine at idle, fully warmed up (coolant ≥ 80 °C).",
               "All electrical loads off (A/C, lights, fan).",
               "Do not touch the accelerator.",
               "Start the routine and wait — the throttle will cycle and settle.",
               "When it reports done, switch ignition off for 20 s."),
        preconditions=("Engine running and warm", "Accelerator released", "Loads off"),
        caution="The throttle will move on its own. Keep hands clear of the intake.",
        engine="running", confidence="template"),
    ServiceFn(
        id="service_reset", name="Service / Oil Interval Reset", group="Service", modules=("17",),
        summary="Resets the service reminder (oil / inspection) in the instrument cluster after a service.",
        kind="routine", spec={"routine": 0x0351, "timeout": 20, "done_offset": 0, "done_value": 0x02},
        steps=("Ignition ON, engine off.",
               "Confirm the service you actually performed.",
               "Run the reset; the SERVICE message clears.",
               "Cycle the ignition and check the cluster."),
        preconditions=("Ignition on, engine off", "Service actually completed"),
        caution="Only reset after the work is genuinely done — it changes the maintenance record.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="sas_calibration", name="Steering Angle Sensor Calibration", group="Steering", modules=("03", "44"),
        summary="Zeroes the steering angle sensor. Required after a wheel alignment, steering rack, "
                "or SAS replacement, and clears the ESC light when it's an angle fault.",
        kind="routine", spec={"routine": 0x0404, "timeout": 30, "done_offset": 0, "done_value": 0x02},
        steps=("On level ground, engine running.",
               "Wheels pointed perfectly straight ahead.",
               "Do not move the steering wheel during calibration.",
               "Run the routine; then drive straight briefly to confirm the light is out."),
        preconditions=("Engine running", "Wheels straight ahead", "Vehicle stationary"),
        caution="Wrong wheel position calibrates a wrong zero — make sure the steering is truly centred.",
        engine="running", confidence="template"),
    ServiceFn(
        id="abs_bleed", name="ABS Brake Bleeding", group="Brakes", modules=("03",),
        summary="Cycles the ABS pump and valves so you can bleed air from the ABS unit — needed after "
                "opening the hydraulic circuit or replacing the ABS module.",
        kind="routine", spec={"routine": 0x0301, "timeout": 120, "done_offset": 0, "done_value": 0x02},
        steps=("Engine off, ignition ON. Brake fluid reservoir topped up.",
               "Have a second person at the bleeder screws.",
               "Run the routine and follow the per-wheel pumping prompts.",
               "Keep the reservoir full throughout.",
               "Finish, then do a normal pedal bleed."),
        preconditions=("Ignition on", "Reservoir full", "Second person ready"),
        caution="Never let the reservoir run dry — it pulls air into the ABS unit.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="epb_service", name="Parking Brake Service Mode", group="Brakes", modules=("53", "03"),
        summary="Opens the electronic parking brake calipers to the service position for rear pad changes, "
                "then closes them again. Only if the car has an electronic handbrake.",
        kind="routine", spec={"routine": 0x0405, "timeout": 30},
        steps=("Ignition ON, engine off, car on level ground, wheels chocked.",
               "Run 'open' — the rear calipers retract.",
               "Change the pads.",
               "Run 'close', then press the EPB switch a few times.",
               "Check the handbrake holds before driving."),
        preconditions=("Ignition on", "Wheels chocked", "Car has electronic handbrake"),
        caution="Confirm the brake holds before moving. If the car has a manual handbrake, this doesn't apply.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="battery_reg", name="Battery Registration", group="Battery", modules=("01", "09"),
        summary="Registers a new battery's capacity and serial so the charging/energy management adapts. "
                "Only on cars with battery monitoring (usually start-stop / AGM).",
        kind="adaptation", spec={"did": 0x1480},
        steps=("Ignition ON, engine off.",
               "Enter the new battery's Ah capacity and serial from its label.",
               "Write and verify.",
               "Cycle the ignition."),
        preconditions=("Ignition on", "New battery fitted", "Car has battery monitoring"),
        caution="Wrong capacity makes the charging strategy wrong. Skip if the car has no BMS.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="injector_coding", name="Injector Coding / Calibration", group="Engine", modules=("01",),
        summary="Writes the injector correction (IMA/flow) codes after replacing injectors, so the ECU "
                "trims each cylinder correctly.",
        kind="adaptation", spec={"did": 0x0391},
        steps=("Ignition ON, engine off.",
               "Enter each injector's code from its body / paperwork, per cylinder.",
               "Write and verify.",
               "Start the engine and check idle smoothness."),
        preconditions=("Ignition on, engine off", "Injector codes to hand"),
        caution="Wrong codes cause rough running. Match each code to the correct cylinder.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="egr_adapt", name="EGR Adaptation / Learn", group="Engine", modules=("01",),
        summary="Re-learns the EGR valve range after cleaning or replacement. Mostly diesel.",
        kind="routine", spec={"routine": 0x0408, "timeout": 60, "done_offset": 0, "done_value": 0x02},
        steps=("Engine warm and idling, no loads.",
               "Do not touch the accelerator.",
               "Run the routine; the EGR valve cycles and relearns.",
               "Switch off for 20 s when done."),
        preconditions=("Engine warm and idling", "Accelerator released"),
        caution="The EGR valve moves on its own during the routine.",
        engine="running", confidence="template"),
    ServiceFn(
        id="gearbox_relearn", name="Gearbox / DSG Adaptation", group="Engine", modules=("02",),
        summary="Resets and re-learns transmission clutch/shift adaptations after service or clutch work. "
                "Follow with a defined drive cycle.",
        kind="routine", spec={"routine": 0x0401, "timeout": 60, "done_offset": 0, "done_value": 0x02},
        steps=("Engine warm, selector in P, brake held.",
               "Run the reset.",
               "Then drive the manufacturer's adaptation cycle (varied gentle shifts).",
               "Shift quality improves as it relearns."),
        preconditions=("Engine warm", "Selector in P", "Brake held"),
        caution="Shifts may feel firm until the drive-cycle relearn completes.",
        engine="running", confidence="template"),
    ServiceFn(
        id="immobilizer_reset", name="Immobilizer / Key Learn", group="Security", modules=("09", "17"),
        summary="Immobilizer adaptation (key matching / component protection). Security-protected — usually "
                "needs the vehicle's secret PIN/SKC and online access.",
        kind="procedure", spec={},
        steps=("This needs the vehicle's component-protection PIN/SKC.",
               "Without it the ECU stays security-locked (NRC 0x33).",
               "Use the dealer/ODIS online path or a known-good SKC source."),
        preconditions=("Vehicle PIN/SKC available",),
        caution="Immobilizer work can leave the car unable to start. Only with the correct secret.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="tpms_reset", name="Tyre Pressure (TPMS) Reset", group="Comfort", modules=("17",),
        summary="Resets the tyre-pressure monitor to the current pressures as the new reference, after "
                "inflation or a tyre change.",
        kind="routine", spec={"routine": 0x0409, "timeout": 20, "done_offset": 0, "done_value": 0x02},
        steps=("Set all tyres to the correct cold pressures.",
               "Ignition ON.",
               "Run the reset (or use the car's menu / SET button).",
               "Drive a few minutes to confirm the warning stays off."),
        preconditions=("Tyres at correct pressure", "Ignition on"),
        caution="On indirect TPMS this just relearns; it can't detect a real slow leak immediately.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="sunroof_init", name="Sunroof Initialisation", group="Comfort", modules=("09",),
        summary="Re-initialises the sunroof's end stops and one-touch after a battery disconnect or if it "
                "won't auto-close.",
        kind="procedure", spec={},
        steps=("Ignition ON.",
               "Hold the switch to fully close, keep holding 10–20 s.",
               "Release, then tilt/close once more to confirm one-touch works.",
               "(Some cars expose this as a basic-setting routine instead.)"),
        preconditions=("Ignition on",),
        caution="Keep fingers clear of the glass during initialisation.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="headlight_afs", name="Adaptive Front Lighting Calibration", group="Comfort", modules=("09",),
        summary="Calibrates headlight range / adaptive front-lighting (AFS) aim after a headlight or level "
                "sensor replacement.",
        kind="routine", spec={"routine": 0x040A, "timeout": 30, "done_offset": 0, "done_value": 0x02},
        steps=("Car on level ground, correct ride height, engine running.",
               "Nobody in the car, normal load.",
               "Run the calibration; the headlights sweep and centre.",
               "Check beam aim on a wall afterwards."),
        preconditions=("Level ground", "Engine running", "Normal load"),
        caution="Mis-aimed beams dazzle oncoming drivers. Verify aim after.",
        engine="running", confidence="template"),
    ServiceFn(
        id="air_suspension", name="Air Suspension Ride-Height Calibration", group="Comfort", modules=("34",),
        summary="Calibrates air-suspension ride heights after a level-sensor or strut replacement. Only on "
                "air-sprung cars.",
        kind="routine", spec={"routine": 0x040B, "timeout": 120, "done_offset": 0, "done_value": 0x02},
        steps=("Car on level ground, doors closed, normal load.",
               "Measure actual ride heights as the car asks.",
               "Enter them and run the calibration.",
               "Let the car settle and recheck."),
        preconditions=("Level ground", "Air suspension fitted"),
        caution="Wrong heights affect handling and headlight aim.",
        engine="ignition", confidence="template"),
    ServiceFn(
        id="dpf_regen", name="DPF Forced Regeneration", group="Engine", modules=("01",),
        summary="Forces a diesel particulate filter burn-off when soot load is high. Diesel only.",
        kind="routine", spec={"routine": 0x0407, "timeout": 1800, "done_offset": 0, "done_value": 0x02},
        steps=("Diesel engine, warmed up, in a well-ventilated open area.",
               "Fuel at least 1/4 tank; nothing flammable near the exhaust.",
               "Start the regen and let it run — exhaust gets very hot.",
               "Keep running until it reports complete.",
               "Do not leave the vehicle unattended."),
        preconditions=("Diesel engine", "Warm engine", "Open ventilated area", "≥1/4 tank"),
        caution="Exhaust reaches extreme temperatures. Never run indoors or near anything flammable.",
        engine="running", fuel=("diesel",), confidence="template"),
]

GROUPS = ("Engine", "Brakes", "Steering", "Service", "Battery", "Security", "Comfort")


def functions_for(address: str | None = None, family: str = "vag", fuel: str = "") -> list[ServiceFn]:
    """Service functions applicable to a module (or all, if address is None) for this car."""
    out = []
    for f in CATALOG:
        if family != "vag":
            continue
        if address is not None and address not in f.modules:
            continue
        if f.fuel and fuel and fuel not in f.fuel:
            continue
        out.append(f)
    return out
