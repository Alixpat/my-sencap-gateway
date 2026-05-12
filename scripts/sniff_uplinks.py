#!/usr/bin/env python3
"""
Affiche les uplinks LoRaWAN reçus par toutes les gateways du broker
ChirpStack, **y compris ceux d'appareils non enregistrés**. Utile pour :

- valider la radio (la passerelle capte-t-elle vraiment quelque chose ?) ;
- voir le trafic du voisinage (TTN, Helium, capteurs proprios) ;
- débugger une nouvelle gateway sans avoir à déclarer un device.

Le broker mosquitto n'écoutant qu'en 127.0.0.1 sur la passerelle, ouvre
d'abord un tunnel SSH depuis ta machine :

    ssh -L 1884:127.0.0.1:1883 -fN pi@<gateway-ip>

Puis :

    .venv/bin/python scripts/sniff_uplinks.py --port 1884

Stoppe avec Ctrl-C.
"""
import argparse
import paho.mqtt.client as mqtt
from chirpstack_api.gw import gw_pb2

MTYPE_NAMES = {
    0: "JoinReq", 1: "JoinAcc",
    2: "UnconfUp", 3: "UnconfDn",
    4: "ConfUp", 5: "ConfDn",
    6: "RFU", 7: "Proprietary",
}


def fmt_uplink(up: gw_pb2.UplinkFrame, i: int) -> str:
    rx, tx = up.rx_info, up.tx_info
    p = up.phy_payload
    mtype = (p[0] >> 5) & 0x07
    if mtype in (2, 3, 4, 5):       # MAC payload : DevAddr est en LE
        ident = "0x" + bytes(reversed(p[1:5])).hex()
    elif mtype == 0:                # JoinRequest : DevEUI en LE après AppEUI
        ident = "DevEUI=" + bytes(reversed(p[9:17])).hex()
    else:
        ident = "-"
    sf = tx.modulation.lora.spreading_factor
    bw = tx.modulation.lora.bandwidth // 1000
    crc = "OK" if rx.crc_status == 1 else "FAIL"
    return (f"#{i:<4d} {MTYPE_NAMES[mtype]:9s} {ident:24s} "
            f"{tx.frequency/1e6:6.2f}MHz SF{sf}BW{bw}  "
            f"RSSI={rx.rssi:>4d}dBm SNR={rx.snr:+5.1f}dB  "
            f"{len(p):3d}B  CRC={crc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1",
                        help="Hôte MQTT (défaut: 127.0.0.1 via tunnel SSH)")
    parser.add_argument("--port", type=int, default=1884,
                        help="Port MQTT (défaut: 1884 = tunnel)")
    parser.add_argument("--region", default="eu868",
                        help="Préfixe région (eu868, us915, etc.)")
    parser.add_argument("--max", type=int, default=0,
                        help="Sortir après N trames (0 = infini)")
    args = parser.parse_args()

    seen = 0
    topic = f"{args.region}/gateway/+/event/up"

    def on_connect(c, _u, _f, rc, _p=None):
        print(f"# Connected to MQTT ({rc}), subscribing to {topic}", flush=True)
        c.subscribe(topic)

    def on_msg(_c, _u, m):
        nonlocal seen
        seen += 1
        up = gw_pb2.UplinkFrame.FromString(m.payload)
        print(fmt_uplink(up, seen), flush=True)
        if args.max and seen >= args.max:
            _c.disconnect()

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_connect = on_connect
    c.on_message = on_msg
    c.connect(args.host, args.port, keepalive=60)
    try:
        c.loop_forever()
    except KeyboardInterrupt:
        print(f"\n# Stopped. {seen} uplink(s) captured.")


if __name__ == "__main__":
    main()
