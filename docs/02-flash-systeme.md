# 02 — Flash de la microSD

On installe **Raspberry Pi OS Lite 64-bit**. Pas d'interface graphique : la
M1 sera pilotée en SSH, et la web UI de ChirpStack tournera dessus.

## Choix de l'OS

- Distribution : **Raspberry Pi OS Lite 64-bit**, base Debian **Trixie (13)**
  par défaut dans Pi Imager depuis fin 2025. Les commandes des docs suivantes
  fonctionnent aussi sur Bookworm (12).
- Pourquoi pas Ubuntu Server ? Possible, mais le `sx1302_hal` est testé en
  priorité sur Raspberry Pi OS et certains scripts GPIO supposent ses chemins.
- 64 bits parce que ChirpStack v4 a des paquets ARM64 propres et que c'est
  l'avenir des Pi.

## Préparation

- Une **microSD** d'au moins **16 Go** (32 Go conseillé), classe 10 / A1
  minimum (sinon Postgres rame).
- Un **lecteur de carte microSD** branché sur ton PC.
- **Raspberry Pi Imager** : https://www.raspberrypi.com/software/

> Tu peux soit reflasher la SD Helium d'origine (après l'avoir clonée — voir
> doc 01), soit utiliser une SD vierge neuve. La seconde option est plus sûre
> si tu veux pouvoir remettre Helium d'un simple swap de carte.

## Flasher avec Raspberry Pi Imager

1. Lance `rpi-imager`.
2. **Device** → `Raspberry Pi 4`.
3. **OS** → "Raspberry Pi OS (other)" → **Raspberry Pi OS Lite (64-bit)**.
4. **Stockage** : choisis la microSD (vérifie la taille — surtout pas un
   autre disque).
5. **Edit Settings** (engrenage) — étape importante, configure :
   - **Hostname** : `sensecap-gateway`
   - **SSH** : activé, **clé publique** plutôt que mot de passe :
     ```bash
     # côté PC, si pas encore de clé :
     ssh-keygen -t ed25519
     # puis colle ~/.ssh/id_ed25519.pub dans Pi Imager
     ```
   - **User** : `pi` (ou autre) + mot de passe si tu n'utilises pas la clé.
   - **WiFi** : optionnel ici, l'Ethernet suffira pour la suite.
   - **Locale** : `Europe/Paris`, clavier `fr`.
6. **Save**, puis **Write**. Confirme l'écrasement.
7. Une fois l'écriture et la vérification terminées, éjecte proprement la SD.

## Remettre la SD dans la M1

1. Insère la microSD flashée dans le slot SD du Pi 4.
2. Branche le câble Ethernet.
3. Visse l'antenne 868 MHz sur le SMA (⚠️ jamais d'alim sans antenne).
4. Alimente la passerelle.

## Vérification rapide

La LED verte (ACT) du Pi 4 doit clignoter (lecture de la SD). L'Ethernet doit
prendre une IP en DHCP en ~30 s. La suite (trouver l'IP, SSH, etc.) se passe
dans la doc 03.
