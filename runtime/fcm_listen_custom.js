#!/usr/bin/env node
/**
 * Custom FCM listener — pairing, alarms, devices.
 * Marker: @@RUSTPLUS@@{...json...}
 */
const fs = require("fs");
const path = require("path");

const PushReceiverClient = require(path.join(
    __dirname, "rustplus-cli", "node_modules", "@liamcottle", "push-receiver", "src", "client"
));

const MARKER = "@@RUSTPLUS@@";
const configFile = process.argv[2];

if (!configFile) {
    console.error("Usage: node fcm_listen_custom.js <config-file>");
    process.exit(1);
}

function tryParseJson(value) {
    if (typeof value !== "string") return value;
    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

function appDataValue(appData, key) {
    if (!Array.isArray(appData)) return undefined;
    const item = appData.find((entry) => entry && entry.key === key);
    return item ? item.value : undefined;
}

function parseRustPlusNotification(payload) {
    if (!payload || typeof payload !== "object") return null;

    const appData = payload.appData;
    if (!Array.isArray(appData)) return null;

    const channelId = appDataValue(appData, "channelId");
    const bodyRaw = appDataValue(appData, "body");
    const title = appDataValue(appData, "title") || "";
    const message = appDataValue(appData, "message") || "";

    if (!bodyRaw && channelId !== "alarm") return null;

    const body = bodyRaw ? (tryParseJson(bodyRaw) || {}) : {};

    if (channelId === "alarm") {
        return {
            channelId,
            type: "alarm",
            title: String(title || body.title || "Тревога"),
            name: String(body.name || body.entityName || title || "Smart Alarm"),
            message: String(message || body.message || title || "Сработала тревога"),
        };
    }

    if (channelId !== "pairing") return null;

    if (body.type === "server" && body.ip && body.playerToken) {
        return {
            channelId,
            type: "server",
            name: String(body.name || "Server"),
            ip: String(body.ip),
            port: parseInt(body.port || body.appPort || 0, 10),
            playerId: String(body.playerId || body.player_id || ""),
            playerToken: String(body.playerToken || body.player_token || ""),
        };
    }

    if (body.type === "entity" && body.entityId) {
        return {
            channelId,
            type: "entity",
            name: String(body.entityName || body.name || "Device"),
            ip: String(body.ip || ""),
            port: parseInt(body.port || body.appPort || 0, 10),
            playerId: String(body.playerId || body.player_id || ""),
            playerToken: String(body.playerToken || body.player_token || ""),
            entityId: parseInt(body.entityId, 10),
            entityType: String(body.entityType || body.type || "smart_switch"),
        };
    }

    return null;
}

function emitEvent(data) {
    if (!data) return;
    console.log(MARKER + JSON.stringify(data));
}

function handlePayload(payload) {
    const parsed = parseRustPlusNotification(payload);
    if (parsed) {
        emitEvent(parsed);
        return true;
    }
    return false;
}

async function main() {
    const config = readConfig(configFile);
    const creds = config.fcm_credentials;
    if (!creds || !creds.gcm) {
        console.error("FCM credentials missing in config");
        process.exit(1);
    }

    const androidId = creds.gcm.androidId;
    const securityToken = creds.gcm.securityToken;
    const client = new PushReceiverClient(androidId, securityToken, []);

    client.on("ON_DATA_RECEIVED", (data) => {
        handlePayload(data);
    });

    console.log("Listening for FCM notifications...");
    await client.connect();

    process.on("SIGINT", () => process.exit(0));
    process.on("SIGTERM", () => process.exit(0));
}

function readConfig(file) {
    return JSON.parse(fs.readFileSync(file, "utf8"));
}

main().catch((err) => {
    console.error("FCM listen failed:", err.message || err);
    process.exit(1);
});
