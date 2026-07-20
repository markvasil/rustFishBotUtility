"""
Rust Utility Overlay — оверлей поверх игры Rust с полезными инструментами.

Запуск: python main.py
Горячая клавиша: F5 — показать/скрыть оверлей
"""

from __future__ import annotations

import ctypes
import sys
import keyboard

from features.click_scripts.widget import ClickScriptsFeature
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
from overlay.splash import StartupSplash
from overlay.startup_sound import play_soft_pop
from overlay.window import OverlayWindow
from services.app.autostart import is_autostart_enabled, set_autostart
from services.app.lifecycle import force_exit
from services.app.single_instance import ensure_single_instance
from services.app.system_tray import SystemTray
from services.rustplus.service import RustPlusService
from services.timer_manager import TimerManager
from storage.session import SessionStore


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    _enable_dpi_awareness()
    if not ensure_single_instance():
        print("Rust Utility Overlay уже запущен.")
        sys.exit(0)

    session = SessionStore()
    rustplus = RustPlusService()

    overlay_pos = session.get_feature("_overlay")
    initial_overlay_pos = None
    if overlay_pos.get("x") is not None and overlay_pos.get("y") is not None:
        initial_overlay_pos = (int(overlay_pos["x"]), int(overlay_pos["y"]))
    initial_overlay_size = None
    if overlay_pos.get("w") is not None and overlay_pos.get("h") is not None:
        initial_overlay_size = (int(overlay_pos["w"]), int(overlay_pos["h"]))

    overlay = OverlayWindow(
        [],
        initial_position=initial_overlay_pos,
        initial_size=initial_overlay_size,
        on_geometry_changed=lambda x, y, w, h: session.update_feature(
            "_overlay", x=x, y=y, w=w, h=h
        ),
    )

    splash = StartupSplash(overlay.root)
    splash.show("Запуск оверлея…")
    splash.set_progress(0.12)

    splash.set_status("Прицел и таймеры…")
    crosshair = CrosshairWindow(overlay.root, rustplus.store.get_settings)
    timer_manager = TimerManager(
        overlay.root,
        on_complete=lambda t: _on_timer_done(t, overlay, session, timer_manager_ref),
    )
    timer_manager_ref = timer_manager
    timer_manager.load(session.get_feature("timers").get("active", []))
    splash.set_progress(0.28)

    splash.set_status("Загрузка модулей…")
    features = [
        RustPlusHubFeature(rustplus, overlay, crosshair),
        RaidCalculatorFeature(session),
        CraftCalculatorFeature(session),
        FurnaceCalculatorFeature(),
        ResourceMachinesFeature(),
        NotesFeature(session),
        TimersFeature(session, timer_manager),
        GeneticsFeature(session=session),
        ElectricityFeature(),
        ClickScriptsFeature(session, overlay),
    ]
    splash.set_progress(0.62)

    splash.set_status("Сборка интерфейса…")
    overlay.set_features(features)
    splash.set_progress(0.78)

    splash.set_status("Rust+ сервис…")
    rustplus.start()
    splash.set_progress(0.9)

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
            try:
                tray.stop()
            except Exception:
                pass
            tray = None

        for feature in features:
            try:
                feature.on_shutdown()
            except Exception:
                pass

        try:
            crosshair.destroy()
        except Exception:
            pass

        try:
            session.update_feature("timers", active=timer_manager.dump())
        except Exception:
            pass

        try:
            timer_manager.stop()
        except Exception:
            pass

        try:
            rustplus.stop()
        except Exception:
            pass

        try:
            keyboard.unhook_all()
        except Exception:
            pass

        try:
            overlay.destroy()
        except Exception:
            pass

        force_exit(0)

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

    splash.set_status("Готово")
    splash.set_progress(1.0)
    splash.close()
    play_soft_pop()

    print("Rust Utility Overlay запущен.")
    print("F5 — показать/скрыть оверлей.")
    print("F6 — выход из приложения.")

    try:
        overlay.run()
    finally:
        if not shutting_down:
            shutdown()


def _on_timer_done(timer, overlay, session, timer_manager) -> None:
    TimersFeature.on_timer_complete(timer, overlay.show)
    session.update_feature("timers", active=timer_manager.dump())
    timers_feature = overlay.get_feature("timers")
    if timers_feature:
        overlay.root.after(0, timers_feature._refresh)


if __name__ == "__main__":
    main()
