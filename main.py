"""
Rust Utility Overlay — оверлей поверх игры Rust с полезными инструментами.

Запуск: python main.py
Горячая клавиша: F5 — показать/скрыть оверлей
"""

from __future__ import annotations

import sys

import keyboard

from features.craft_calculator.widget import CraftCalculatorFeature
from features.crosshair.window import CrosshairWindow
from features.electricity.widget import ElectricityFeature
from features.furnace_calculator.widget import FurnaceCalculatorFeature
from features.genetics.widget import GeneticsFeature
from features.notes.widget import NotesFeature
from features.raid_calculator.widget import RaidCalculatorFeature
from features.resource_machines.widget import ResourceMachinesFeature
from features.rustplus_hub.widget import RustPlusHubFeature
from features.timers.widget import TimersFeature
from overlay.window import OverlayWindow
from services.app.autostart import is_autostart_enabled, set_autostart
from services.app.single_instance import ensure_single_instance
from services.app.system_tray import SystemTray
from services.rustplus.service import RustPlusService
from services.timer_manager import TimerManager
from storage.session import SessionStore


def main() -> None:
    if not ensure_single_instance():
        print("Rust Utility Overlay уже запущен.")
        sys.exit(0)

    session = SessionStore()
    rustplus = RustPlusService()

    overlay = OverlayWindow([])
    crosshair = CrosshairWindow(overlay.root, rustplus.store.get_settings)
    timer_manager = TimerManager(
        overlay.root,
        on_complete=lambda t: _on_timer_done(t, overlay, session, timer_manager_ref),
    )
    timer_manager_ref = timer_manager
    timer_manager.load(session.get_feature("timers").get("active", []))

    features = [
        RustPlusHubFeature(rustplus, overlay, crosshair),
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
    rustplus.start()

    settings = rustplus.store.get_settings()
    if settings.autostart != is_autostart_enabled():
        set_autostart(settings.autostart)
    if settings.crosshair_enabled:
        crosshair.apply_settings()

    shutting_down = False
    tray: SystemTray | None = None

    def shutdown() -> None:
        nonlocal shutting_down, tray
        if shutting_down:
            return
        shutting_down = True
        if tray:
            tray.stop()
            tray = None
        for feature in features:
            feature.on_shutdown()
        crosshair.destroy()
        session.update_feature("timers", active=timer_manager.dump())
        timer_manager.stop()
        rustplus.stop()
        keyboard.unhook_all()
        overlay.quit()

    def on_toggle() -> None:
        overlay.root.after(0, overlay.toggle)

    def request_shutdown() -> None:
        overlay.root.after(0, shutdown)

    def on_tray_show() -> None:
        overlay.root.after(0, overlay.show)

    keyboard.add_hotkey("f5", on_toggle, suppress=False)
    keyboard.add_hotkey("f6", request_shutdown, suppress=False)

    if settings.minimize_to_tray:
        try:
            hwnd = overlay.root.winfo_id()
            tray = SystemTray(hwnd, on_show=on_tray_show, on_quit=request_shutdown)
            tray.start()
        except Exception:
            tray = None

    print("Rust Utility Overlay запущен.")
    print("F5 — показать/скрыть оверлей.")
    print("F6 — выход из приложения.")

    try:
        overlay.run()
    finally:
        if tray:
            tray.stop()
        for feature in features:
            feature.on_shutdown()
        crosshair.destroy()
        session.update_feature("timers", active=timer_manager.dump())
        timer_manager.stop()
        rustplus.stop()
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
