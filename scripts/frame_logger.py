#!/usr/bin/env python3
"""
Subscriber MQTT qui archive **toutes** les trames LoRaWAN vues par la
passerelle en NDJSON (une trame = une ligne JSON), pour analyse ultérieure
(grep, jq, pandas, etc.).

Le packet forwarder ne stocke rien, le Gateway Bridge publie en QoS=0 sans
rétention, et ChirpStack ne garde que les uplinks des devices enregistrés
(dans Redis, avec TTL). Donc sans ce logger, les trames du voisinage que
tu peux voir avec sniff_uplinks.py sont perdues à la sortie du script.

Format de sortie (une ligne par trame) :
    {"ts":"2026-05-12T19:30:00.123456+02:00",
     "gw_id":"0016c001f10c84bf",
     "mtype":"UnconfUp", "len":24,
     "dev_addr":"260bed3c", "f_cnt":2584, "f_port":6,
     "flags":{"adr":true,"ack":false,"class_b":false}, "frm_len":11,
     "freq":867900000, "sf":7, "bw":125000,
     "rssi":-47, "snr":13.8, "crc_ok":true,
     "phy":"40..."}   # phy_payload en hex (pour re-décodage offline)

Usage côté Pi (mosquitto en localhost, pas de tunnel) :
    sudo systemctl enable --now frame-logger.service

Usage interactif depuis ton poste (via tunnel SSH :1884) :
    .venv/bin/python scripts/frame_logger.py \\
        --host 127.0.0.1 --port 1884 \\
        --output frames-$(date +%F).ndjson
"""
import argparse
import datetime as dt
import json
import signal
import sys

import paho.mqtt.client as mqtt
from chirpstack_api.gw import gw_pb2

# Réutilisé par sniff_uplinks.py — gardé inline pour rendre ce script
# indépendant (utile si déployé seul sur la passerelle).
MTYPE_NAMES = {
    0: "JoinReq", 1: "JoinAcc",
    2: "UnconfUp", 3: "UnconfDn",
    4: "ConfUp", 5: "ConfDn",
    6: "RFU", 7: "Proprietary",
}


def parse_phy(p: bytes) -> dict:
    out = {"mtype": MTYPE_NAMES[(p[0] >> 5) & 0x07], "len": len(p)}
    mt = (p[0] >> 5) & 0x07
    if mt == 0 and len(p) >= 23:
        out["app_eui"] = bytes(reversed(p[1:9])).hex()
        out["dev_eui"] = bytes(reversed(p[9:17])).hex()
        out["dev_nonce"] = int.from_bytes(p[17:19], "little")
    elif mt in (2, 4) and len(p) >= 12:
        fctrl = p[5]
        out["dev_addr"] = bytes(reversed(p[1:5])).hex()
        out["flags"] = {
            "adr":     bool(fctrl & 0x80),
            "ack":     bool(fctrl & 0x20),
            "class_b": bool(fctrl & 0x10),
        }
        out["f_opts_len"] = fctrl & 0x0F
        out["f_cnt"] = int.from_bytes(p[6:8], "little")
        head = 8 + out["f_opts_len"]
        if head < len(p) - 4:
            out["f_port"] = p[head]
            out["frm_len"] = len(p) - 4 - head - 1
    return out


def make_record(topic: str, up: gw_pb2.UplinkFrame) -> dict:
    phy = bytes(up.phy_payload)
    rx, tx = up.rx_info, up.tx_info
    # topic = eu868/gateway/<EUI>/event/up
    parts = topic.split("/")
    rec = {
        "ts": dt.datetime.fromtimestamp(
            rx.gw_time.seconds + rx.gw_time.nanos / 1e9
            if rx.gw_time.seconds else dt.datetime.now(dt.timezone.utc).timestamp(),
            tz=dt.timezone.utc
        ).isoformat(),
        "gw_id": parts[2] if len(parts) >= 3 else None,
        "freq": tx.frequency,
        "sf":   tx.modulation.lora.spreading_factor,
        "bw":   tx.modulation.lora.bandwidth,
        "rssi": rx.rssi,
        "snr":  round(rx.snr, 2),
        "crc_ok": rx.crc_status == 1,
        "phy": phy.hex(),
    }
    rec.update(parse_phy(phy))
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883,
                        help="1883 si tu tournes sur le Pi, 1884 via tunnel")
    parser.add_argument("--region", default="eu868")
    parser.add_argument("--output", "-o", default="-",
                        help="Fichier de sortie (NDJSON append). '-' = stdout")
    parser.add_argument("--flush-every", type=int, default=1,
                        help="fsync toutes les N trames (1=temps réel)")
    args = parser.parse_args()

    out = sys.stdout if args.output == "-" else open(args.output, "a",
                                                     buffering=1, encoding="utf-8")
    topic = f"{args.region}/gateway/+/event/up"
    written = [0]

    def on_connect(c, _u, _f, rc, _p=None):
        print(f"# connected ({rc}), sub {topic}", file=sys.stderr, flush=True)
        c.subscribe(topic, qos=0)

    def on_msg(_c, _u, m):
        try:
            up = gw_pb2.UplinkFrame.FromString(m.payload)
            rec = make_record(m.topic, up)
        except Exception as e:
            rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "error": str(e), "topic": m.topic,
                   "raw": m.payload.hex()}
        out.write(json.dumps(rec, separators=(",", ":")) + "\n")
        written[0] += 1
        if args.flush_every and written[0] % args.flush_every == 0:
            out.flush()

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                    client_id=f"frame-logger-{dt.datetime.now().timestamp():.0f}")
    c.on_connect = on_connect
    c.on_message = on_msg
    c.connect(args.host, args.port, keepalive=60)

    signal.signal(signal.SIGTERM, lambda *_: c.disconnect())
    signal.signal(signal.SIGINT,  lambda *_: c.disconnect())

    c.loop_forever()
    print(f"# stopped, {written[0]} record(s)", file=sys.stderr)
    if out is not sys.stdout:
        out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
