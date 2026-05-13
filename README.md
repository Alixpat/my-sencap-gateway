# my-sencap-gateway

Recyclage d'une **SenseCAP M1 (EU868, origine Helium)** en passerelle
**LoRaWAN sous ChirpStack v4**, en mode **tout-en-un sur l'appareil**
(packet forwarder + Gateway Bridge + ChirpStack + Postgres + Redis +
Mosquitto sur le même Pi).

## Ce que tu obtiens à la fin

- Une passerelle LoRaWAN EU868 indépendante (plus de dépendance Helium).
- ChirpStack v4 accessible en local : `http://<ip-de-la-passerelle>:8080`.
- De quoi enregistrer tes propres capteurs LoRaWAN et voir leurs trames.

## Pré-requis

- Une **SenseCAP M1** variante EU868 (ici : **Raspberry Pi 4 + microSD**).
- Un PC sous Linux/macOS/Windows avec un **lecteur de carte microSD**.
- Une connexion réseau pour la M1 : Ethernet **ou** WiFi (le WiFi se
  pré-configure dans Pi Imager au moment du flash).
- Une antenne LoRa 868 MHz vissée sur le connecteur SMA.
  ⚠️ **Ne jamais alimenter la passerelle sans antenne** : tu risques de griller
  l'étage RF du SX1302.

## Plan

1. [Matériel & démontage](docs/01-materiel.md)
2. [Flash du système](docs/02-flash-systeme.md)
3. [Premier boot & SSH](docs/03-premier-boot.md)
4. [Packet forwarder SX1302](docs/04-packet-forwarder.md)
5. [Installation de ChirpStack v4](docs/05-chirpstack.md)
6. [Vérification de bout en bout](docs/06-tests.md)

## Bon à savoir avant de commencer

- La M1 visée ici est la variante **Raspberry Pi 4 + carte concentratrice
  SX1302** (WM1302 ou équivalent) **avec microSD**.
- ChirpStack tout-en-un tient sur un Pi 4 sans problème côté CPU/RAM. Compte
  ~1 Go d'occupation disque et ~500 Mo de RAM utilisée au repos.

## Accès distant (optionnel)

Pour s'affranchir du LAN local, du DHCP et du port forwarding, on peut
installer [Tailscale](https://tailscale.com/) sur la passerelle :

```bash
ssh pi@sensecap-gateway.local
curl -fsSL https://tailscale.com/install.sh | sudo sh
sudo tailscale up --hostname=sensecap-gateway
# clique sur l'URL affichée pour authentifier la machine dans ton tailnet
```

Ensuite, depuis n'importe quelle machine du tailnet :

```bash
ssh pi@sensecap-gateway              # MagicDNS résout le nom court
curl http://sensecap-gateway:8080    # ChirpStack UI / API
```

Et le `.env` du dépôt peut pointer sur `sensecap-gateway:8080` plutôt que
l'IP LAN, les scripts gRPC marchent alors depuis n'importe où.

## Sources

- Semtech `sx1302_hal` : https://github.com/Lora-net/sx1302_hal
- ChirpStack : https://www.chirpstack.io/
- Wiki Seeed SenseCAP M1 (à vérifier pour le matériel exact)

## Licence

À choisir (MIT / Apache-2.0 / CC-BY conseillés pour de la doc).
