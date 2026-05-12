#!/usr/bin/env python3
"""
Analyse l'archive NDJSON produite par scripts/frame_logger.py et affiche
un rapport synthétique : devices récurrents, anomalies, opérateurs vus,
profil RF.

Sans clés, on ne déchiffre rien — l'analyse porte sur les en-têtes en clair
et la radio. Suffit pour cartographier le voisinage LoRaWAN.

Exemples :
    # Archive locale (récupérée par scp depuis /var/log/chirpstack-frames/)
    .venv/bin/python scripts/analyze_archive.py /tmp/frames.ndjson

    # Lecture via stdin (par exemple ssh + cat) — pas de streaming temps réel,
    # le rapport est imprimé une fois l'entrée fermée.
    ssh pi@gw 'cat /var/log/chirpstack-frames/frames.ndjson' \\
        | .venv/bin/python scripts/analyze_archive.py -

    # Fenêtre temporelle
    .venv/bin/python scripts/analyze_archive.py frames.ndjson --since 24h

    # Focus sur un device
    .venv/bin/python scripts/analyze_archive.py frames.ndjson --dev-addr 260bed3c
"""
import argparse
import collections
import datetime as dt
import json
import re
import statistics
import sys

# ──────────────────────────────────────────────────────────────────────
#  Décodage d'identifiants
# ──────────────────────────────────────────────────────────────────────

# Quelques couples (type, NwkID) connus, pour donner un indice d'opérateur.
# La table NetID complète est tenue par la LoRa Alliance.
KNOWN_NETS: dict[tuple[int, int], str] = {
    (0, 0x00): "expérimental",
    (0, 0x01): "expérimental",
    (0, 0x13): "TTN community (NetID 0x000013)",
    (0, 0x0F): "opérateur privé (souvent FR)",
    (6, 0x000013): "Helium (NetID 0x600013)",
}


def decode_dev_addr(addr_hex: str) -> tuple[int, int, str]:
    """Retourne (type, nwk_id, label) en respectant le format LoRaWAN :
    le 'type' est encodé par les bits de tête (préfixe unaire de 1
    terminé par un 0), et le NwkID prend ensuite un nombre de bits
    différent selon le type.

        Type 0  prefix 0     : NwkID 6 bits, NwkAddr 25 bits
        Type 1  prefix 10    : NwkID 6 bits, NwkAddr 24 bits
        Type 2  prefix 110   : NwkID 9 bits, NwkAddr 20 bits
        Type 3  prefix 1110  : NwkID 11 bits
        Type 4  prefix 11110 : NwkID 12 bits
        Type 5  prefix 111110: NwkID 13 bits
        Type 6  prefix 111111 0: NwkID 15 bits
        Type 7  prefix 1111111: NwkID 17 bits
    """
    addr = int(addr_hex, 16)
    if (addr >> 31) == 0:                       # Type 0
        nwk_type, prefix_len, nwk_bits = 0, 1, 6
    elif (addr >> 30) == 0b10:                  # Type 1
        nwk_type, prefix_len, nwk_bits = 1, 2, 6
    elif (addr >> 29) == 0b110:                 # Type 2
        nwk_type, prefix_len, nwk_bits = 2, 3, 9
    elif (addr >> 28) == 0b1110:                # Type 3
        nwk_type, prefix_len, nwk_bits = 3, 4, 11
    elif (addr >> 27) == 0b11110:               # Type 4
        nwk_type, prefix_len, nwk_bits = 4, 5, 12
    elif (addr >> 26) == 0b111110:              # Type 5
        nwk_type, prefix_len, nwk_bits = 5, 6, 13
    elif (addr >> 25) == 0b1111110:             # Type 6
        nwk_type, prefix_len, nwk_bits = 6, 7, 15
    else:                                        # Type 7
        nwk_type, prefix_len, nwk_bits = 7, 7, 17
    nwk_addr_bits = 32 - prefix_len - nwk_bits
    nwk_id = (addr >> nwk_addr_bits) & ((1 << nwk_bits) - 1)
    label = KNOWN_NETS.get(
        (nwk_type, nwk_id),
        f"Type {nwk_type} / NwkID 0x{nwk_id:0{(nwk_bits+3)//4}x}",
    )
    return nwk_type, nwk_id, label


def ascii_hint(hex_str: str) -> str | None:
    """Tente un décodage ASCII des octets imprimables. Retourne None si
    moins de la moitié des octets sont des caractères imprimables."""
    b = bytes.fromhex(hex_str)
    s = "".join(chr(c) if 32 <= c < 127 else "·" for c in b)
    printable = sum(1 for c in b if 32 <= c < 127)
    if printable >= len(b) / 2:
        return s
    return None


# ──────────────────────────────────────────────────────────────────────
#  Chargement + filtres
# ──────────────────────────────────────────────────────────────────────

def parse_since(spec: str) -> dt.datetime:
    """Accepte '24h', '30m', '7d', ou un ISO timestamp."""
    m = re.fullmatch(r"(\d+)([dhm])", spec.strip().lower())
    if m:
        unit_kw = {"d": "days", "h": "hours", "m": "minutes"}[m.group(2)]
        delta = dt.timedelta(**{unit_kw: int(m.group(1))})
        return dt.datetime.now(dt.timezone.utc) - delta
    return dt.datetime.fromisoformat(spec)


def load_frames(path: str) -> list[dict]:
    f = sys.stdin if path == "-" else open(path, "r", encoding="utf-8")
    out = []
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if f is not sys.stdin:
        f.close()
    return out


def filter_frames(frames: list[dict], args: argparse.Namespace) -> list[dict]:
    out = frames
    if args.since:
        cutoff = parse_since(args.since)
        out = [f for f in out
               if dt.datetime.fromisoformat(f["ts"]) >= cutoff]
    if args.dev_addr:
        out = [f for f in out if f.get("dev_addr") == args.dev_addr.lower()]
    if args.dev_eui:
        out = [f for f in out if f.get("dev_eui") == args.dev_eui.lower()]
    return out


# ──────────────────────────────────────────────────────────────────────
#  Sections du rapport
# ──────────────────────────────────────────────────────────────────────

def section_volume(frames: list[dict]) -> None:
    times = sorted(dt.datetime.fromisoformat(f["ts"]) for f in frames)
    span = (times[-1] - times[0]).total_seconds() if len(times) > 1 else 0
    print("══ Volume ══")
    print(f"  {len(frames)} trames")
    if span:
        print(f"  de {times[0].astimezone().strftime('%Y-%m-%d %H:%M:%S')} "
              f"à {times[-1].astimezone().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  durée {span/3600:.1f} h  →  {len(frames)*3600/span:.1f} trames/h")
    print()


def section_mtype(frames: list[dict]) -> None:
    by_mt = collections.Counter(f["mtype"] for f in frames if "mtype" in f)
    print("══ Par type MAC ══")
    for k, v in by_mt.most_common():
        print(f"  {k:11s} {v:>4d}")
    print()


def inter_arrival_stats(times: list[dt.datetime]) -> dict | None:
    if len(times) < 2:
        return None
    deltas = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    m = statistics.mean(deltas)
    sd = statistics.pstdev(deltas) if len(deltas) > 1 else 0
    regular = sd < max(2.0, 0.05 * m)         # <5% var ou <2 s
    return {"mean": m, "sd": sd, "regular": regular, "deltas": deltas}


def section_devaddr(frames: list[dict], top: int) -> None:
    by_addr: dict[str, list[dict]] = collections.defaultdict(list)
    for f in frames:
        if "dev_addr" in f:
            by_addr[f["dev_addr"]].append(f)
    if not by_addr:
        print("══ DevAddr récurrents ══   (aucun)\n")
        return
    print(f"══ DevAddr récurrents ══   ({len(by_addr)} uniques)")
    sorted_addrs = sorted(by_addr.items(), key=lambda kv: -len(kv[1]))[:top]
    for addr, fs in sorted_addrs:
        fs.sort(key=lambda x: x["ts"])
        times = [dt.datetime.fromisoformat(x["ts"]) for x in fs]
        fcs = sorted({x.get("f_cnt", -1) for x in fs})
        rssis = [x["rssi"] for x in fs]
        sfs = sorted({x["sf"] for x in fs})
        ports = sorted({x.get("f_port") for x in fs if x.get("f_port") is not None})
        adr_pct = sum(1 for x in fs if x.get("flags", {}).get("adr")) * 100 // len(fs)
        _, _, nwk_label = decode_dev_addr(addr)

        print(f"\n  ─ {addr}  ({nwk_label})")
        print(f"      n={len(fs)}  fcnt={fcs[0]}..{fcs[-1]}  "
              f"RSSI={min(rssis)}..{max(rssis)}dBm  SF={sfs}  port={ports}  ADR={adr_pct}%")

        ia = inter_arrival_stats(times)
        if ia:
            tag = "régulière" if ia["regular"] else "irrégulière"
            print(f"      Δt moyen={ia['mean']:.1f}s  σ={ia['sd']:.1f}s  ({tag})")

        # Anomalies repérées
        flags = []
        if len(fcs) == 1 and fcs[0] == 0 and len(fs) >= 2:
            flags.append("FCnt toujours 0 — re-init session probable")
        if len(fcs) > 1 and (max(fcs) - min(fcs)) < len(fs) - 2:
            flags.append("FCnt qui régresse")
        if max(rssis) > -70:
            flags.append("RSSI très haut — device probablement proche")
        if flags:
            for fl in flags:
                print(f"      ⚠ {fl}")
    print()


def section_joins(frames: list[dict], top: int) -> None:
    joins = [f for f in frames if f.get("mtype") == "JoinReq"]
    if not joins:
        return
    by_eui: dict[str, list[dict]] = collections.defaultdict(list)
    for f in joins:
        by_eui[f["dev_eui"]].append(f)
    print(f"══ JoinRequests ══   ({len(joins)} tentatives, {len(by_eui)} DevEUI uniques)")
    for eui, fs in sorted(by_eui.items(), key=lambda kv: -len(kv[1]))[:top]:
        app_euis = sorted({f["app_eui"] for f in fs})
        nonces = sorted({f["dev_nonce"] for f in fs})
        rssis = [f["rssi"] for f in fs]
        print(f"\n  ─ DevEUI={eui}  n={len(fs)}  {len(nonces)} nonce(s) distincts  "
              f"RSSI {min(rssis)}..{max(rssis)}dBm")
        for app in app_euis:
            hint = ascii_hint(app)
            extra = f"  → \"{hint}\"" if hint else ""
            print(f"      AppEUI={app}{extra}")
        # Anomalies
        if any(f["dev_eui"] == f["app_eui"] for f in fs):
            print(f"      ⚠ DevEUI == AppEUI — valeur placeholder, ne joindra jamais un vrai réseau")
        if len(fs) >= 5 and len(nonces) == len(fs):
            print(f"      ⚠ rejeu en boucle (~chaque tentative un nouveau nonce)")
    print()


def section_radio(frames: list[dict]) -> None:
    if not frames:
        return
    print("══ Profil radio ══")
    ch = collections.Counter(f["freq"] for f in frames)
    print("  Canaux : " +
          "  ".join(f"{f/1e6:.2f}={n}" for f, n in sorted(ch.items())))
    sf = collections.Counter(f["sf"] for f in frames)
    print("  SF     : " + "  ".join(f"SF{k}={v}" for k, v in sorted(sf.items())))
    rssis = [f["rssi"] for f in frames]
    snrs = [f["snr"]  for f in frames]
    print(f"  RSSI : min={min(rssis)}  max={max(rssis)}  "
          f"moy={statistics.mean(rssis):+.1f}  median={statistics.median(rssis):+.0f}")
    print(f"  SNR  : min={min(snrs):+.1f}  max={max(snrs):+.1f}  "
          f"moy={statistics.mean(snrs):+.1f}")
    print()


def section_ascii_hints(frames: list[dict]) -> None:
    """Dévoile les AppEUI/suffixes DevEUI qui ressemblent à de l'ASCII."""
    hints = []
    for f in frames:
        for k in ("app_eui", "dev_eui"):
            if k in f:
                h = ascii_hint(f[k])
                if h:
                    hints.append((k, f[k], h))
    if not hints:
        return
    print("══ EUI lisibles en ASCII (curiosités) ══")
    seen = set()
    for k, hex_, hint in hints:
        if (k, hex_) in seen:
            continue
        seen.add((k, hex_))
        print(f"  {k:8s} {hex_}  →  \"{hint}\"")
    print()


# ──────────────────────────────────────────────────────────────────────
#  main
# ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ndjson", help="Fichier NDJSON (ou '-' pour stdin)")
    parser.add_argument("--top", type=int, default=20,
                        help="Nombre max d'entrées par tableau (défaut: 20)")
    parser.add_argument("--since", help="Filtre temporel : '24h', '30m', '7d' ou ISO timestamp")
    parser.add_argument("--dev-addr", help="Focus sur un DevAddr précis")
    parser.add_argument("--dev-eui",  help="Focus sur un DevEUI précis")
    args = parser.parse_args()

    frames = load_frames(args.ndjson)
    if not frames:
        print("(aucune trame dans l'archive)", file=sys.stderr)
        return 1
    frames = filter_frames(frames, args)
    if not frames:
        print("(aucune trame après filtrage)", file=sys.stderr)
        return 1

    section_volume(frames)
    section_mtype(frames)
    section_devaddr(frames, args.top)
    section_joins(frames, args.top)
    section_radio(frames)
    section_ascii_hints(frames)
    return 0


if __name__ == "__main__":
    sys.exit(main())
