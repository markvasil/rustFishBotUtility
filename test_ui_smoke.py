"""Smoke-тест UI: создаёт оверлей, переключает вкладки, проверяет базовые действия."""

from __future__ import annotations

import sys

from features.craft_calculator.widget import CraftCalculatorFeature
from features.electricity.widget import ElectricityFeature
from features.furnace_calculator.widget import FurnaceCalculatorFeature
from features.genetics.widget import GeneticsFeature
from features.notes.widget import NotesFeature
from features.raid_calculator.widget import RaidCalculatorFeature
from features.resource_machines.widget import ResourceMachinesFeature
from features.timers.widget import TimersFeature
from overlay.window import OverlayWindow
from services.timer_manager import TimerManager
from storage.session import SessionStore


def run_smoke() -> None:
    session = SessionStore()
    overlay = OverlayWindow([])
    errors: list[str] = []

    def on_complete(timer):
        TimersFeature.on_timer_complete(timer, lambda: None)

    timer_manager = TimerManager(overlay.root, on_complete=on_complete)
    timer_manager.load(session.get_feature("timers").get("active", []))

    features = [
        RaidCalculatorFeature(session),
        CraftCalculatorFeature(session),
        FurnaceCalculatorFeature(),
        ResourceMachinesFeature(),
        NotesFeature(session),
        TimersFeature(session, timer_manager),
        GeneticsFeature(),
        ElectricityFeature(),
    ]
    overlay.set_features(features)

    for feature in features:
        overlay._show_feature(feature.id)
        overlay.root.update_idletasks()

    notes = overlay.get_feature("notes")
    assert notes is not None
    assert notes._text is not None
    notes._text.delete("1.0", "end")
    notes._text.insert("1.0", "Test note line\nкод 1234")
    notes._save()
    overlay.root.update_idletasks()
    assert "Test note line" in notes._content
    assert session.get_feature("notes").get("text", "").startswith("Test note line")

    timers = overlay.get_feature("timers")
    assert timers is not None
    timers._minutes_var.set("1")
    timers._start_reminder()
    overlay.root.update_idletasks()
    assert len(timer_manager.list_active()) >= 1

    machines = overlay.get_feature("resource_machines")
    assert machines is not None
    machines._diesel_var.set("3")
    machines._add()
    overlay.root.update_idletasks()

    genetics = overlay.get_feature("genetics")
    assert genetics is not None
    genetics._calculate()
    overlay.root.update_idletasks()

    electricity = overlay.get_feature("electricity")
    assert electricity is not None
    electricity._source_vars["solar"].set("2")
    electricity._calculate()
    overlay.root.update_idletasks()

    overlay.fit_to_content()
    overlay.root.update_idletasks()
    overlay.toggle()
    overlay.root.update_idletasks()
    overlay.toggle()

    timer_manager.stop()
    overlay.quit()
    overlay.destroy()

    if errors:
        raise RuntimeError("\n".join(errors))


if __name__ == "__main__":
    try:
        run_smoke()
        print("UI SMOKE TEST PASSED")
    except Exception as exc:
        print(f"UI SMOKE TEST FAILED: {exc}", file=sys.stderr)
        raise
