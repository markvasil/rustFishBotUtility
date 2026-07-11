from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app_paths import get_fcm_config_path, get_runtime_dir, get_rustplus_dir
from services.rustplus.event_bus import EventBus, EventType


from storage.rustplus_store import RustPlusStore


class FCMBridge:
    """
    FCM pairing через Node.js + rustplus.js (как Rust+ Desktop).

    Требует runtime/node-win-x64/node.exe и runtime/rustplus-cli/.
    Установка: scripts/setup_rustplus_runtime.ps1
    """

    _SUBPROCESS_KWARGS = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }

    def __init__(self, event_bus: EventBus, store: Optional[RustPlusStore] = None) -> None:
        self._bus = event_bus
        self._store = store
        self._process: Optional[subprocess.Popen] = None
        self._register_process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._registering = False

    @property
    def is_listening(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    @property
    def is_registering(self) -> bool:
        return self._registering

    def has_config(self) -> bool:
        path = get_fcm_config_path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return bool(data.get("fcm_credentials"))
        except (json.JSONDecodeError, OSError):
            return False

    def find_node(self) -> Optional[Path]:
        bundled = get_runtime_dir() / "node-win-x64" / "node.exe"
        if bundled.exists():
            return bundled
        system = shutil.which("node")
        return Path(system) if system else None

    def find_cli(self) -> Optional[Path]:
        bundled = (
            get_runtime_dir()
            / "rustplus-cli"
            / "node_modules"
            / "@liamcottle"
            / "rustplus.js"
            / "cli"
            / "index.js"
        )
        if bundled.exists():
            return bundled
        local = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "RustUtilityOverlay"
            / "runtime"
            / "rustplus-cli"
            / "node_modules"
            / "@liamcottle"
            / "rustplus.js"
            / "cli"
            / "index.js"
        )
        if local.exists():
            return local
        return None

    def find_custom_register(self) -> Optional[Path]:
        path = get_runtime_dir() / "fcm_register_custom.js"
        return path if path.exists() else None

    def find_custom_listen(self) -> Optional[Path]:
        path = get_runtime_dir() / "fcm_listen_custom.js"
        return path if path.exists() else None

    def runtime_ready(self) -> bool:
        return self.find_node() is not None and self.find_cli() is not None

    def register(self, browser: str = "auto", on_done: Optional[Callable[[bool, str], None]] = None) -> tuple[bool, str]:
        if self._registering:
            return False, "Регистрация уже выполняется"

        node = self.find_node()
        if not node:
            return False, "Установите runtime: scripts/setup_rustplus_runtime.ps1"

        config = get_fcm_config_path()
        config.parent.mkdir(parents=True, exist_ok=True)

        custom = self.find_custom_register()
        if custom:
            cmd = [str(node), str(custom), str(config), browser]
        else:
            cli = self.find_cli()
            if not cli:
                return False, "rustplus-cli не найден"
            cmd = [str(node), str(cli), "fcm-register", "--config-file", str(config)]

        self._registering = True
        self._bus.emit(
            EventType.STATUS,
            message="Открывается браузер. Разрешите всплывающие окна для localhost:3000",
        )

        def worker() -> None:
            ok, msg = self._run_register(cmd, config)
            self._registering = False
            if ok:
                self._bus.emit(EventType.STATUS, message=msg)
            else:
                self._bus.emit(EventType.ERROR, message=msg)
            if on_done:
                on_done(ok, msg)

        threading.Thread(target=worker, daemon=True).start()
        return True, "Регистрация запущена — завершите вход в браузере"

    def _run_register(self, cmd: list[str], config: Path) -> tuple[bool, str]:
        try:
            proc = subprocess.Popen(
                cmd,
                **self._SUBPROCESS_KWARGS,
            )
            self._register_process = proc
            output_lines: list[str] = []
            if proc.stdout:
                for line in proc.stdout:
                    output_lines.append(line.rstrip())
            proc.wait(timeout=600)
            output = "\n".join(output_lines)

            if self.has_config():
                if self._store:
                    self._store.mark_fcm_registered()
                return True, "Steam-авторизация завершена"

            if "Failed to send login message" in output:
                return False, (
                    "Facepunch не получил токен от браузера.\n"
                    "1) Разрешите всплывающие окна (popups) для localhost\n"
                    "2) Попробуйте кнопку Edge вместо Chrome\n"
                    "3) Отключите блокировку localhost в антивирусе\n"
                    "4) Закройте другие окна Rust+ / Companion"
                )

            if "EADDRINUSE" in output or "address already in use" in output:
                return False, (
                    "Порт 3000 занят другим процессом.\n"
                    "Закройте старые окна браузера/Node и нажмите Сброс FCM.\n"
                    "Или в PowerShell: netstat -ano | findstr :3000\n"
                    "Затем: taskkill /PID <номер> /F"
                )

            tail = "\n".join(output_lines[-8:]) if output_lines else "Регистрация не завершена"
            return False, tail
        except subprocess.TimeoutExpired:
            return False, "Таймаут регистрации (10 мин)"
        except Exception as exc:
            return False, str(exc)
        finally:
            self._register_process = None

    def reset_config(self) -> None:
        path = get_fcm_config_path()
        if path.exists():
            path.unlink()
        self._bus.emit(EventType.STATUS, message="FCM config удалён — зарегистрируйтесь заново")

    def import_config(self, source: Path) -> tuple[bool, str]:
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            if not data.get("fcm_credentials"):
                return False, "В файле нет fcm_credentials"
            dest = get_fcm_config_path()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True, f"Импортировано из {source.name}"
        except Exception as exc:
            return False, str(exc)

    def start_listen(self) -> tuple[bool, str]:
        if self.is_listening:
            self.stop_listen()

        node = self.find_node()
        cli = self.find_cli()
        if not node or not cli:
            return False, "Нет Node/runtime"
        if not self.has_config():
            return False, "Сначала выполните регистрацию FCM (Steam)"

        config = get_fcm_config_path()
        custom = self.find_custom_listen()
        if custom:
            cmd = [str(node), str(custom), str(config)]
        else:
            cli = self.find_cli()
            if not cli:
                return False, "rustplus-cli не найден"
            cmd = [str(node), str(cli), "fcm-listen", "--config-file", str(config)]

        try:
            self._process = subprocess.Popen(
                cmd,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                **self._SUBPROCESS_KWARGS,
            )
            self._running = True
            self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
            self._reader_thread.start()
            self._bus.emit(
                EventType.STATUS,
                message=(
                    "FCM listener запущен.\n"
                    "В игре: Rust+ → Pair Server → затем Resend notification"
                ),
            )
            return True, "Listener запущен — сделайте Pair + Resend notification"
        except Exception as exc:
            return False, str(exc)

    def stop_listen(self) -> None:
        self._running = False
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None
        self._bus.emit(EventType.STATUS, message="FCM listener остановлен")

    def _read_output(self) -> None:
        if not self._process or not self._process.stdout:
            return
        buffer = ""
        try:
            for line in self._process.stdout:
                if not self._running:
                    break
                buffer += line
                self._try_parse_line(line.strip())
                if len(buffer) > 20000:
                    buffer = buffer[-10000:]
        except UnicodeDecodeError:
            self._bus.emit(
                EventType.ERROR,
                message="Ошибка кодировки вывода FCM listener (перезапустите listener)",
            )

        if self._process.poll() is not None and self._running:
            self._running = False
            self._bus.emit(EventType.ERROR, message="FCM listener завершился")

    def _try_parse_line(self, line: str) -> None:
        if not line:
            return

        marker = "@@RUSTPLUS@@"
        if marker in line:
            idx = line.index(marker)
            try:
                payload = json.loads(line[idx + len(marker):])
                self._handle_pairing_payload(payload)
                return
            except json.JSONDecodeError:
                pass

        for chunk in self._extract_json_chunks(line):
            if chunk.get("type") in {"server", "entity"} and chunk.get("channelId") == "pairing":
                self._handle_pairing_payload(chunk)

        if "@@RUSTPLUS@@" not in line and "playerToken" in line and "channelId" in line:
            self._try_parse_loose_pairing(line)

    @staticmethod
    def _extract_json_chunks(text: str) -> list[Dict[str, Any]]:
        results: list[Dict[str, Any]] = []
        for match in re.finditer(r"\{[^{}]*\}", text):
            try:
                obj = json.loads(match.group())
                if isinstance(obj, dict):
                    results.append(obj)
            except json.JSONDecodeError:
                continue
        if not results:
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    results.append(obj)
            except json.JSONDecodeError:
                pass
        return results

    def _handle_pairing_payload(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return

        pairing_type = str(data.get("type", "")).lower()
        if pairing_type == "alarm":
            name = str(data.get("name", data.get("title", "Smart Alarm")))
            message = str(data.get("message", data.get("title", "Сработала тревога")))
            if self._store and not self._store.get_alert_settings().alarm:
                return
            self._bus.emit(
                EventType.LIVE_ALERT,
                title=name,
                message=f"🚨 {name}: {message}",
                category="alarm",
            )
            return

        if pairing_type == "server":
            self._emit_server_pairing(data)
            return

        if pairing_type == "entity":
            body = {
                "entityId": data.get("entityId", data.get("entity_id")),
                "name": data.get("name", data.get("entityName", "Device")),
                "entityType": data.get("entityType", data.get("device_type", "smart_switch")),
            }
            self._emit_device_pairing(body)
            return

        # Legacy fallback for old listener output
        body = data.get("body", data)
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = data
        if not isinstance(body, dict):
            body = data

        entity_type = str(body.get("type", body.get("entityType", ""))).lower()
        if entity_type == "server" and body.get("ip") and body.get("playerToken"):
            self._emit_server_pairing(body)
            return

        if entity_type == "entity" and body.get("entityId"):
            self._emit_device_pairing(body)

    def _emit_server_pairing(self, body: Dict[str, Any]) -> None:
        try:
            port_int = int(body.get("port", body.get("appPort", 0)))
            player_id = int(body.get("playerId", body.get("player_id", 0)))
            player_token = int(body.get("playerToken", body.get("player_token", 0)))
        except (TypeError, ValueError):
            self._bus.emit(EventType.ERROR, message="Некорректные данные паринга сервера")
            return

        if not body.get("ip") or not player_token:
            self._bus.emit(EventType.ERROR, message="Паринг: нет IP или playerToken")
            return

        if port_int <= 0:
            self._bus.emit(EventType.ERROR, message="Паринг: некорректный порт")
            return

        payload = {
            "name": str(body.get("name", "Server")),
            "ip": str(body.get("ip", "")),
            "port": port_int,
            "player_id": player_id,
            "player_token": player_token,
        }
        self._log_pairing("server", payload)
        self._bus.emit(EventType.SERVER_PAIRED, **payload)

    def _emit_device_pairing(self, body: Dict[str, Any]) -> None:
        try:
            entity_id = int(body.get("entityId", body.get("entity_id", 0)))
        except (TypeError, ValueError):
            return

        raw_type = str(body.get("entityType", body.get("type", "smart_switch"))).lower()
        if "switch" in raw_type:
            device_type = "smart_switch"
        elif "alarm" in raw_type:
            device_type = "smart_alarm"
        elif "storage" in raw_type or "monitor" in raw_type:
            device_type = "storage_monitor"
        else:
            device_type = raw_type or "smart_switch"

        payload = {
            "entity_id": entity_id,
            "name": str(body.get("name", body.get("entityName", "Device"))),
            "device_type": device_type,
        }
        self._log_pairing("entity", payload)
        self._bus.emit(EventType.DEVICE_PAIRED, **payload)

    @staticmethod
    def _log_pairing(kind: str, payload: Dict[str, Any]) -> None:
        try:
            log_path = get_rustplus_dir() / "pairing.log"
            line = json.dumps({"kind": kind, **payload}, ensure_ascii=False)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    def _try_parse_loose_pairing(self, text: str) -> None:
        """Fallback for node util.inspect output from stock fcm-listen."""
        fields: Dict[str, str] = {}
        for key in ("ip", "port", "name", "type", "playerId", "playerToken"):
            match = re.search(rf"{key}:\s*'([^']*)'", text)
            if match:
                fields[key] = match.group(1)
            else:
                match = re.search(rf"{key}:\s*(\d+)", text)
                if match:
                    fields[key] = match.group(1)
        if fields.get("ip") and fields.get("playerToken"):
            self._handle_pairing_payload(fields)
