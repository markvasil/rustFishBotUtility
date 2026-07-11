#!/usr/bin/env node
/**
 * FCM register with Windows fixes:
 * - dynamic free port (3000-3010)
 * - correct temp profile dir
 * - Chrome / Edge fallback
 */
const path = require("path");
const os = require("os");
const fs = require("fs");
const net = require("net");
const { spawn } = require("child_process");

const axios = require(path.join(__dirname, "rustplus-cli", "node_modules", "axios"));
const express = require(path.join(__dirname, "rustplus-cli", "node_modules", "express"));
const { v4: uuidv4 } = require(path.join(__dirname, "rustplus-cli", "node_modules", "uuid"));
const AndroidFCM = require(path.join(__dirname, "rustplus-cli", "node_modules", "@liamcottle", "push-receiver", "src", "android", "fcm"));

const configFile = process.argv[2];
const browserArg = (process.argv[3] || "auto").toLowerCase();

if (!configFile) {
    console.error("Usage: node fcm_register_custom.js <config-file> [chrome|edge|auto]");
    process.exit(1);
}

function readConfig(file) {
    try {
        return JSON.parse(fs.readFileSync(file, "utf8"));
    } catch {
        return {};
    }
}

function writeConfig(file, patch) {
    const current = readConfig(file);
    fs.writeFileSync(file, JSON.stringify({ ...current, ...patch }, null, 2), "utf8");
}

function findFreePort(start, end) {
    return new Promise((resolve, reject) => {
        let port = start;
        const tryPort = () => {
            if (port > end) {
                reject(new Error(`No free port in range ${start}-${end}`));
                return;
            }
            const tester = net.createServer()
                .once("error", () => {
                    port += 1;
                    tryPort();
                })
                .once("listening", () => {
                    tester.close(() => resolve(port));
                })
                .listen(port, "127.0.0.1");
        };
        tryPort();
    });
}

function pairHtml(port) {
    return `<!DOCTYPE html>
<html lang="en">
<head><title>RustPlus Pairing</title></head>
<body>
<div>Allow popups, then log in with Steam in the popup window.</div>
<script>
var popupWindow = window.open("https://companion-rust.facepunch.com/login", "rustplus_login", "width=900,height=700");
if (!popupWindow) {
    document.body.innerHTML = "<b>Popup blocked!</b> Allow popups for localhost:${port} and refresh.";
}
var handlerInterval = setInterval(function() {
    if (!popupWindow || popupWindow.closed) return;
    try {
        if (popupWindow.ReactNativeWebView === undefined) {
            popupWindow.ReactNativeWebView = {
                postMessage: function(message) {
                    clearInterval(handlerInterval);
                    var auth = JSON.parse(message);
                    window.location.href = "http://localhost:${port}/callback?token=" + encodeURIComponent(auth.Token);
                    popupWindow.close();
                }
            };
        }
    } catch (e) {}
}, 250);
</script>
</body>
</html>`;
}

async function getExpoPushToken(fcmToken) {
    const response = await axios.post("https://exp.host/--/api/v2/push/getExpoPushToken", {
        type: "fcm",
        deviceId: uuidv4(),
        development: false,
        appId: "com.facepunch.rust.companion",
        deviceToken: fcmToken,
        projectId: "49451aca-a822-41e6-ad59-955718d0ff9c",
    });
    return response.data.data.expoPushToken;
}

function findChrome() {
    const candidates = [
        process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, "Google", "Chrome", "Application", "chrome.exe"),
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    ].filter(Boolean);
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    return null;
}

function findEdge() {
    const candidates = [
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
        "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    return null;
}

function launchBrowser(port, mode) {
    const profileDir = path.join(os.tmpdir(), "rustplus-chrome-profile");
    const flags = [
        `--user-data-dir=${profileDir}`,
        "--disable-web-security",
        "--disable-popup-blocking",
        "--disable-site-isolation-trials",
        "--no-first-run",
        "--no-default-browser-check",
        `http://localhost:${port}/`,
    ];

    let exe = null;
    if (mode === "chrome" || mode === "auto") exe = findChrome();
    if (!exe && (mode === "edge" || mode === "auto")) exe = findEdge();

    if (!exe) {
        throw new Error("Chrome/Edge not found. Install Google Chrome or Microsoft Edge.");
    }

    console.log(`Launching browser: ${exe}`);
    console.log(`Pair page: http://localhost:${port}/`);
    const child = spawn(exe, flags, { detached: true, stdio: "ignore" });
    child.unref();
    return child;
}

async function linkSteamWithRustPlus(mode) {
    const port = await findFreePort(3000, 3010);
    console.log(`Using port ${port} for Steam callback`);

    return new Promise((resolve, reject) => {
        const app = express();
        let server;

        app.get("/", (_req, res) => {
            res.type("html").send(pairHtml(port));
        });

        app.get("/callback", (req, res) => {
            const authToken = req.query.token;
            if (authToken) {
                res.send("Steam linked successfully. Close this window and return to Rust Utility Overlay.");
                server.close();
                resolve(authToken);
            } else {
                res.status(400).send("Token missing from request!");
                server.close();
                reject(new Error("Token missing from callback"));
            }
        });

        server = app.listen(port, "127.0.0.1", () => {
            try {
                launchBrowser(port, mode);
            } catch (err) {
                server.close();
                reject(err);
            }
        });

        server.on("error", (err) => reject(err));

        const timeout = setTimeout(() => {
            server.close();
            reject(new Error("Steam login timeout (5 min). Allow popups and try again."));
        }, 300000);

        server.on("close", () => clearTimeout(timeout));
    });
}

async function main() {
    console.log("Registering with FCM...");
    const apiKey = "AIzaSyB5y2y-Tzqb4-I4Qnlsh_9naYv_TD8pCvY";
    const projectId = "rust-companion-app";
    const gcmSenderId = "976529667804";
    const gmsAppId = "1:976529667804:android:d6f1ddeb4403b338fea619";
    const androidPackageName = "com.facepunch.rust.companion";
    const androidPackageCert = "E28D05345FB78A7A1A63D70F4A302DBF426CA5AD";

    const fcmCredentials = await AndroidFCM.register(
        apiKey, projectId, gcmSenderId, gmsAppId, androidPackageName, androidPackageCert
    );

    console.log("Fetching Expo Push Token...");
    const expoPushToken = await getExpoPushToken(fcmCredentials.fcm.token);
    console.log("Expo Push Token OK");

    console.log("Opening browser for Steam + Rust+ login...");
    console.log("IMPORTANT: allow popups for localhost");
    const rustplusAuthToken = await linkSteamWithRustPlus(browserArg);

    console.log("Registering with Rust Companion API...");
    await axios.post("https://companion-rust.facepunch.com:443/api/push/register", {
        AuthToken: rustplusAuthToken,
        DeviceId: "rustplus.js",
        PushKind: 3,
        PushToken: expoPushToken,
    });

    writeConfig(configFile, {
        fcm_credentials: fcmCredentials,
        expo_push_token: expoPushToken,
        rustplus_auth_token: rustplusAuthToken,
    });

    console.log("SUCCESS: saved to " + configFile);
}

main().catch((err) => {
    console.error("FCM register failed:", err.message || err);
    process.exit(1);
});
