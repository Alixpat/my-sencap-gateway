# 04 — Packet forwarder SX1302

Le **packet forwarder** est le programme qui parle au concentrateur LoRa
SX1302 en SPI et qui pousse les trames LoRa vers le réseau (ici, vers le
**ChirpStack Gateway Bridge** en UDP local).

On utilise la référence officielle Semtech : **`sx1302_hal`**.

## Compilation

```bash
cd ~
git clone https://github.com/Lora-net/sx1302_hal.git
cd sx1302_hal
make
```

La compilation prend quelques minutes sur un CM4. Tu obtiens entre autres :

- `packet_forwarder/lora_pkt_fwd` — le binaire à lancer.
- `packet_forwarder/global_conf.json.sx1250.EU868` — la **conf EU868** prête à
  l'emploi (référence à utiliser ci-dessous).
- `tools/reset_lgw.sh` — le script de reset GPIO du SX1302.

## Remplacer le script de reset GPIO

C'est **l'étape qui plante le plus souvent**, à cause de deux pièges :

1. Le script Semtech d'origine (`tools/reset_lgw.sh`) utilise
   `/sys/class/gpio/`, qui **n'existe plus sur Debian Trixie** (le sysfs GPIO
   a été retiré). Il renvoie `Directory nonexistent` / `I/O error`.
2. Ses valeurs par défaut (RESET=23, POWER_EN=18) correspondent au
   **CoreCell** de Semtech ; sur la **SenseCAP M1** (module WM1302), le bon
   mapping est **RESET=17**, POWER_EN=18.

On utilise donc une version réécrite avec **`pinctrl`** (qui écrit
directement dans les registres GPIO du SoC, état persistant après la
commande). Ce script est fourni dans `scripts/reset_lgw.sh` du présent dépôt.

Déploie-le **dans `packet_forwarder/`** (et pas seulement dans `tools/`) car
`lora_pkt_fwd` appelle `./reset_lgw.sh` depuis son répertoire courant :

```bash
# Depuis ton PC, dans le dossier du dépôt :
scp scripts/reset_lgw.sh pi@sensecap-gateway.local:/home/pi/sx1302_hal/packet_forwarder/reset_lgw.sh

# Sur le Pi :
chmod +x ~/sx1302_hal/packet_forwarder/reset_lgw.sh
```

Pas besoin d'éditer le script : ses défauts (RESET=17, POWER_EN=18,
SX1261_RESET=22) sont déjà adaptés à la M1. Surcharge possible en variables
d'environnement (`SX1302_RESET_PIN=...` etc.) si jamais ta révision diffère.

## Configurer la radio (EU868)

```bash
cd ~/sx1302_hal/packet_forwarder
cp global_conf.json.sx1250.EU868 global_conf.json
```

Édite `global_conf.json` :

- `gateway_conf.server_address` : `"localhost"` (Gateway Bridge sera en
  local — c'est déjà le défaut du fichier d'exemple).
- `gateway_conf.serv_port_up` / `serv_port_down` : passe-les à **1700** (port
  UDP par défaut du ChirpStack Gateway Bridge ; le fichier d'origine utilise
  1730) :
  ```bash
  sed -i 's/"serv_port_up": 1730/"serv_port_up": 1700/'   global_conf.json
  sed -i 's/"serv_port_down": 1730/"serv_port_down": 1700/' global_conf.json
  ```
- `gateway_conf.gateway_ID` : laisse `AA555A0000000000` dans le fichier. Au
  démarrage, `lora_pkt_fwd` lit la **vraie EUI du SX1302** (dérivée du chip)
  et l'affiche dans les logs (`INFO: concentrator EUI: 0x...`). C'est cette
  EUI réelle qu'on déclarera dans ChirpStack à la doc 06, pas la valeur du
  fichier.

## Premier test manuel

```bash
cd ~/sx1302_hal/packet_forwarder
sudo ./lora_pkt_fwd
```

Tu dois voir des lignes du type :

```
INFO: Concentrator started, packet can be received
INFO: [main] concentrator EUI: 0xaa555a0000000000
##### ... #####
### [UPSTREAM] ###
```

Si tu obtiens `ERROR: FAILED TO START THE CONCENTRATOR` :

- Vérifie le SPI (`ls /dev/spidev*`).
- Vérifie les GPIO du reset (cf. plus haut).
- Vérifie que l'antenne est bien vissée (et que tu as la bonne variante 868
  MHz et pas un module 915 MHz).

Coupe avec `Ctrl-C`.

## Lancer le forwarder au démarrage (service systemd)

Crée le fichier :

```bash
sudo vim /etc/systemd/system/lora-pkt-fwd.service
```

Contenu :

```ini
[Unit]
Description=LoRa SX1302 packet forwarder
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/pi/sx1302_hal/packet_forwarder
ExecStart=/home/pi/sx1302_hal/packet_forwarder/lora_pkt_fwd
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```

Active et lance :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lora-pkt-fwd
sudo systemctl status lora-pkt-fwd
journalctl -u lora-pkt-fwd -f
```

À ce stade, le packet forwarder **tente de pousser** les trames vers
`127.0.0.1:1700`. Comme rien n'écoute encore, il va se plaindre dans les
logs : c'est normal, on installe le destinataire à la doc 05.

## Récupère l'EUI réelle du concentrateur

Au premier démarrage (manuel ou via le service), `lora_pkt_fwd` affiche dans
les logs :

```
INFO: concentrator EUI: 0x0016c0xxxxxxxxxx
```

**Note bien cette EUI** — c'est elle qu'on déclarera dans ChirpStack (doc 06).
Pour la retrouver à tout moment :

```bash
journalctl -u lora-pkt-fwd | grep -i "concentrator EUI"
```
