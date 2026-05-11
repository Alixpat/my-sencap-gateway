# 01 — Matériel & démontage

## Ce qu'il y a dans cette variante de SenseCAP M1

| Élément | Détail |
| --- | --- |
| Calculateur | **Raspberry Pi 4 B** (1 ou 2 ou 4 Go RAM selon le batch) |
| Stockage | **microSD** (insérée dans le slot SD du Pi 4) |
| Concentrateur LoRa | Carte fille SPI à base de **SX1302** (souvent WM1302) |
| Réseau | Ethernet + WiFi (du Pi 4) |
| Alim | 5 V via prise jack convertie en USB-C / GPIO selon la carte |
| RF | Connecteur SMA femelle pour l'antenne 868 MHz |

## Démontage

1. Débranche l'alimentation et l'antenne.
2. Retourne le boîtier ; sous les patins en caoutchouc, **4 vis** cruciformes
   (parfois Torx).
3. Sépare doucement les deux demi-coques. Un câble plat peut relier l'antenne
   externe à la carte — déclipse-le délicatement avant de tout ouvrir.
4. Tu vois le Pi 4 + la carte concentratrice SX1302 connectée sur le **GPIO
   40 broches** (HAT) ou via un adaptateur Mini PCIe → Pi.
5. **La microSD est dans le slot SD du Pi 4**, sur le bord opposé aux ports
   USB/Ethernet. Sors-la délicatement (pression pour la libérer).

## Sauvegarde de la SD Helium (recommandé)

Si tu veux pouvoir **revenir à Helium** ou simplement avoir le filet :

- Sur ton PC, insère la SD dans un lecteur USB.
- Identifie le device (⚠️ **pas** ton disque système) :
  ```bash
  lsblk
  ```
- Clone l'image :
  ```bash
  sudo dd if=/dev/sdX of=helium-backup.img bs=4M status=progress conv=fsync
  ```
- Compresse si tu veux la garder : `xz -T0 helium-backup.img`.

Sous Windows / macOS, utilise **Win32 Disk Imager**, **Etcher** ou
**ApplePiBaker** pour faire l'équivalent (clone vers fichier `.img`).

> Tu peux aussi simplement utiliser **une nouvelle microSD vierge** pour la
> nouvelle install et garder la SD Helium intacte dans un tiroir : c'est le
> moyen le plus sûr de revenir en arrière sans manip.

## Brochage utile pour la doc 04

La carte SX1302 est pilotée en SPI par le Pi 4 avec deux GPIO de service :

| Rôle | GPIO BCM (typique) |
| --- | --- |
| SPI bus | SPI0 (CE0) |
| Reset SX1302 | **GPIO 17** |
| Power Enable | **GPIO 18** |

⚠️ Ces valeurs sont les plus courantes sur les designs Seeed et les HAT
WM1302 / RAK2287, mais elles **peuvent différer** sur ta révision. Vérifie le
wiki Seeed pour ton produit avant la doc 04 : un mauvais GPIO de reset =
packet forwarder qui refuse de démarrer.

## Avant de remonter

- Note le **modèle exact** de la carte concentratrice (souvent imprimé sur le
  blindage). Ça aide en cas de souci de config dans la doc 04.
- Vérifie que le câble d'antenne interne (s'il y en a un) est bien clipsé.
- Garde un accès facile au slot SD au cas où tu doives reflasher : tu peux
  laisser le boîtier ouvert tant que tu n'as pas terminé la doc 06.
