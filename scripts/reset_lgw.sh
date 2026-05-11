#!/bin/sh
# reset_lgw.sh — version patchée pour Raspberry Pi OS Bookworm/Trixie.
#
# Le script d'origine de Semtech (sx1302_hal/tools/reset_lgw.sh) utilise
# /sys/class/gpio/, qui n'est plus disponible sur Debian Trixie (kernel
# 6.12). On le remplace par `pinctrl`, qui écrit directement dans les
# registres GPIO du SoC via /dev/gpiomem (état persistant après la commande).
#
# GPIOs (numéros BCM) — valeurs validées pour la SenseCAP M1 (WM1302) :
#   - RESET    = 17  (le défaut Semtech CoreCell est 23 — différent ici)
#   - POWER_EN = 18
#   - SX1261_RESET = 22
# Surcharge possible via variables d'environnement.

SX1302_RESET_PIN=${SX1302_RESET_PIN:-17}
SX1302_POWER_EN_PIN=${SX1302_POWER_EN_PIN:-18}
SX1261_RESET_PIN=${SX1261_RESET_PIN:-22}

WAIT_GPIO() {
    sleep 0.1
}

reset() {
    echo "CoreCell reset (RESET=$SX1302_RESET_PIN, POWER_EN=$SX1302_POWER_EN_PIN, SX1261_RESET=$SX1261_RESET_PIN)"

    # Power enable HIGH — alimente l'étage RF du SX1302
    pinctrl set "$SX1302_POWER_EN_PIN" op dh; WAIT_GPIO

    # Impulsion de reset sur le SX1302 : HIGH -> LOW
    pinctrl set "$SX1302_RESET_PIN" op dh; WAIT_GPIO
    pinctrl set "$SX1302_RESET_PIN" dl;     WAIT_GPIO

    # Reset du SX1261 (LBT / spectral scan) : LOW -> HIGH
    pinctrl set "$SX1261_RESET_PIN" op dl; WAIT_GPIO
    pinctrl set "$SX1261_RESET_PIN" dh;    WAIT_GPIO
}

stop() {
    pinctrl set "$SX1302_POWER_EN_PIN" ip
    pinctrl set "$SX1302_RESET_PIN"    ip
    pinctrl set "$SX1261_RESET_PIN"    ip
}

case "$1" in
    start) reset ;;
    stop)  stop  ;;
    *)
        echo "Usage: $0 {start|stop}"
        exit 1
        ;;
esac

exit 0
