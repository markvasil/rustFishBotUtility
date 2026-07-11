"""
Rust Utility Overlay — оверлей поверх игры Rust с полезными инструментами.

Запуск: python main.py
Горячая клавиша: F5 — показать/скрыть оверлей
"""

from __future__ import annotations

import keyboard

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


def main() -> None:
    session = SessionStore()

    overlay = OverlayWindow([])
    timer_manager = TimerManager(
        overlay.root,
        on_complete=lambda t: _on_timer_done(t, overlay, session, timer_manager_ref),
    )
    timer_manager_ref = timer_manager
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

    shutting_down = False

    def shutdown() -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        session.update_feature("timers", active=timer_manager.dump())
        timer_manager.stop()
        keyboard.unhook_all()
        overlay.quit()

    def on_toggle() -> None:
        overlay.root.after(0, overlay.toggle)

    def request_shutdown() -> None:
        overlay.root.after(0, shutdown)

    keyboard.add_hotkey("f5", on_toggle, suppress=False)
    keyboard.add_hotkey("f6", request_shutdown, suppress=False)

    print("Rust Utility Overlay запущен.")
    print("F5 — показать/скрыть оверлей.")
    print("F6 — выход из приложения.")

    try:
        overlay.run()
    finally:
        session.update_feature("timers", active=timer_manager.dump())
        timer_manager.stop()
        keyboard.unhook_all()
        overlay.destroy()


def _on_timer_done(timer, overlay, session, timer_manager) -> None:
    TimersFeature.on_timer_complete(timer, overlay.show)
    session.update_feature("timers", active=timer_manager.dump())
    timers_feature = overlay.get_feature("timers")
    if timers_feature:
        overlay.root.after(0, timers_feature._refresh)


if __name__ == "__main__":
    main()
