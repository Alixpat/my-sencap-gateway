#!/usr/bin/env python3
"""
Affiche les uplinks LoRaWAN reçus par toutes les gateways du broker
ChirpStack et, à la sortie, une synthèse cumulative.

Ce que le décodeur extrait sans clés (tout l'en-tête LoRaWAN est en clair) :
- MAC payload : DevAddr, FCnt, drapeaux FCtrl (ADR/ACK/ClassB/FPending),
  FPort, taille du FRMPayload chiffré, MIC.
- JoinRequest : AppEUI (JoinEUI), DevEUI, DevNonce.
- Couche radio : fréquence, SF, BW, RSSI, SNR, état du CRC.

Le broker mosquitto n'écoutant qu'en 127.0.0.1 sur la passerelle, ouvre
d'abord un tunnel SSH depuis ta machine :

    ssh -L 1884:127.0.0.1:1883 -fN pi@<gateway-ip>

Puis :

    .venv/bin/python scripts/sniff_uplinks.py             # infini
    .venv/bin/python scripts/sniff_uplinks.py --duration 300   # 5 min
    .venv/bin/python scripts/sniff_uplinks.py --max 10    # 10 trames
    .venv/bin/python scripts/sniff_uplinks.py --quiet     # synthèse seule

Stoppe avec Ctrl-C — la synthèse est imprimée dans tous les cas.
"""
import argparse
import collections
import signal
import threading
import time

import paho.mqtt.client as mqtt
from chirpstack_api.gw import gw_pb2

MTYPE_NAMES = {
    0: "JoinReq", 1: "JoinAcc",
    2: "UnconfUp", 3: "UnconfDn",
    4: "ConfUp", 5: "ConfDn",
    6: "RFU", 7: "Proprietary",
}


def parse_phy(p: bytes) -> dict:
    """Décode l'entête LoRaWAN. Retourne un dict des champs trouvés."""
    out = {"mtype": (p[0] >> 5) & 0x07, "len": len(p)}
    if out["mtype"] == 0 and len(p) >= 23:
        # JoinRequest : AppEUI(8 LE) | DevEUI(8 LE) | DevNonce(2 LE) | MIC(4)
        out["app_eui"] = bytes(reversed(p[1:9])).hex()
        out["dev_eui"] = bytes(reversed(p[9:17])).hex()
        out["dev_nonce"] = int.from_bytes(p[17:19], "little")
    elif out["mtype"] in (2, 4) and len(p) >= 12:
        # Uplink MAC payload :
        #   DevAddr(4 LE) | FCtrl(1) | FCnt(2 LE) | FOpts(FOptsLen) | FPort? | FRM? | MIC(4)
        out["dev_addr"] = bytes(reversed(p[1:5])).hex()
        fctrl = p[5]
        out["adr"] = bool(fctrl & 0x80)
        out["ack"] = bool(fctrl & 0x20)
        out["class_b"] = bool(fctrl & 0x10)
        out["f_opts_len"] = fctrl & 0x0F
        out["f_cnt"] = int.from_bytes(p[6:8], "little")
        head = 8 + out["f_opts_len"]
        # Si reste autre chose que les 4 octets du MIC, le 1er est FPort.
        if head < len(p) - 4:
            out["f_port"] = p[head]
            out["frm_len"] = len(p) - 4 - head - 1
    return out


def fmt_uplink(up: gw_pb2.UplinkFrame, i: int, info: dict) -> str:
    rx, tx = up.rx_info, up.tx_info
    mtype = info["mtype"]
    if mtype in (2, 4):
        ident = f"{info['dev_addr']}  fcnt={info['f_cnt']:>5d}"
        flags = []
        if info.get("adr"): flags.append("ADR")
        if info.get("ack"): flags.append("ACK")
        if info.get("class_b"): flags.append("B")
        port = f"p{info.get('f_port', '-')}"
        extra = f"{port:5s} [{','.join(flags) or '-':10s}] frm={info.get('frm_len', 0):>3d}B"
    elif mtype == 0:
        ident = f"DevEUI={info['dev_eui']}"
        extra = f"AppEUI={info['app_eui']} nonce={info['dev_nonce']}"
    else:
        ident = f"raw={up.phy_payload.hex()[:16]}…"
        extra = ""
    sf = tx.modulation.lora.spreading_factor
    bw = tx.modulation.lora.bandwidth // 1000
    return (f"#{i:<4d} {MTYPE_NAMES[mtype]:9s} {ident:30s} "
            f"{tx.frequency/1e6:6.2f}MHz SF{sf}BW{bw} "
            f"RSSI={rx.rssi:>4d} SNR={rx.snr:+5.1f}  "
            f"{up.phy_payload.__len__():3d}B  {extra}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1884)
    parser.add_argument("--region", default="eu868")
    parser.add_argument("--max", type=int, default=0,
                        help="Sortir après N trames (0 = illimité)")
    parser.add_argument("--duration", type=int, default=0,
                        help="Sortir après N secondes (0 = illimité)")
    parser.add_argument("--quiet", action="store_true",
                        help="Pas d'affichage par trame, juste la synthèse")
    args = parser.parse_args()

    state = {
        "n": 0,
        "by_devaddr": collections.Counter(),
        "by_deveui": collections.Counter(),
        "by_appeui": collections.Counter(),
        "by_mtype": collections.Counter(),
        "by_freq": collections.Counter(),
        "by_sf": collections.Counter(),
        "fcnt_by_devaddr": collections.defaultdict(list),
        "rssi": [],
        "snr": [],
        "started": time.time(),
    }
    topic = f"{args.region}/gateway/+/event/up"

    def on_connect(c, _u, _f, rc, _p=None):
        print(f"# Connected ({rc}), sub {topic}", flush=True)
        c.subscribe(topic)

    def on_msg(_c, _u, m):
        state["n"] += 1
        up = gw_pb2.UplinkFrame.FromString(m.payload)
        info = parse_phy(bytes(up.phy_payload))
        state["by_mtype"][MTYPE_NAMES[info["mtype"]]] += 1
        state["by_freq"][up.tx_info.frequency] += 1
        state["by_sf"][up.tx_info.modulation.lora.spreading_factor] += 1
        state["rssi"].append(up.rx_info.rssi)
        state["snr"].append(up.rx_info.snr)
        if "dev_addr" in info:
            state["by_devaddr"][info["dev_addr"]] += 1
            state["fcnt_by_devaddr"][info["dev_addr"]].append(info["f_cnt"])
        if "dev_eui" in info:
            state["by_deveui"][info["dev_eui"]] += 1
            state["by_appeui"][info["app_eui"]] += 1
        if not args.quiet:
            print(fmt_uplink(up, state["n"], info), flush=True)
        if args.max and state["n"] >= args.max:
            _c.disconnect()

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_connect = on_connect
    c.on_message = on_msg
    c.connect(args.host, args.port, keepalive=60)

    if args.duration:
        threading.Timer(args.duration, c.disconnect).start()
    signal.signal(signal.SIGINT, lambda *_: c.disconnect())

    try:
        c.loop_forever()
    except KeyboardInterrupt:
        pass

    print_summary(state)


def print_summary(s: dict) -> None:
    elapsed = max(1, time.time() - s["started"])
    print()
    print(f"# ── Synthèse ── {s['n']} trame(s) en {elapsed:.0f}s "
          f"({s['n']*60/elapsed:.1f} trames/min)")
    if s["by_mtype"]:
        print("# Par type MAC :  " +
              " ".join(f"{k}={v}" for k, v in s["by_mtype"].most_common()))
    if s["by_devaddr"]:
        print(f"# DevAddr uniques : {len(s['by_devaddr'])}")
        for a, c in s["by_devaddr"].most_common(10):
            fcs = sorted(set(s["fcnt_by_devaddr"][a]))
            span = f"fcnt {min(fcs)}..{max(fcs)}" if len(fcs) > 1 else f"fcnt {fcs[0]}"
            print(f"#   {a}  {c} trame(s)  {span}")
    if s["by_deveui"]:
        print(f"# DevEUI uniques (JoinReq) : {len(s['by_deveui'])}")
        for e, c in s["by_deveui"].most_common(10):
            print(f"#   DevEUI={e}  {c} join(s)")
    if s["by_appeui"]:
        print("# AppEUI vus en join :  " +
              ", ".join(f"{e} ×{c}" for e, c in s["by_appeui"].most_common(5)))
    if s["by_freq"]:
        print("# Canaux (MHz) :  " +
              " ".join(f"{f/1e6:.2f}={c}" for f, c in s["by_freq"].most_common()))
    if s["by_sf"]:
        print("# SF :            " +
              " ".join(f"SF{k}={v}" for k, v in sorted(s["by_sf"].items())))
    if s["rssi"]:
        print(f"# RSSI : min={min(s['rssi'])} max={max(s['rssi'])} "
              f"moy={sum(s['rssi'])/len(s['rssi']):+.1f} dBm")
        print(f"# SNR  : min={min(s['snr']):+.1f} max={max(s['snr']):+.1f} "
              f"moy={sum(s['snr'])/len(s['snr']):+.1f} dB")


if __name__ == "__main__":
    main()
