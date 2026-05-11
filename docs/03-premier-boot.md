# 03 — Premier boot & SSH

## Trouver l'IP de la passerelle

Depuis ton PC (sur le même LAN) :

```bash
# soit via mDNS si Avahi est dispo
ping sensecap-gateway.local

# soit en scannant le réseau
nmap -sn 192.168.1.0/24 | grep -B2 -i raspberry
```

Sinon, va voir la table DHCP de ta box / routeur.

## Se connecter en SSH

```bash
ssh pi@sensecap-gateway.local
# ou
ssh pi@192.168.1.42
```

Si tu as choisi la clé publique dans Pi Imager, ça passe direct ; sinon, mot
de passe défini à l'étape 02.

## Mises à jour de base

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y git build-essential vim curl ca-certificates
sudo reboot
```

Reconnecte-toi en SSH après le redémarrage.

## Réglages système

```bash
# Hostname (déjà fait via Pi Imager normalement)
sudo hostnamectl set-hostname sensecap-gateway

# Timezone
sudo timedatectl set-timezone Europe/Paris

# Locale (si pas faite via Pi Imager)
sudo dpkg-reconfigure locales
```

## Activer SPI et I2C

Le SX1302 communique en **SPI** ; le capteur de température STTS751 monté à
côté est lu en **I2C**. Sans I2C, le packet forwarder refusera de démarrer
(« failed to open I2C for temperature sensor on port 0x39 »).

```bash
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
```

Ou en édition manuelle dans `/boot/firmware/config.txt` :

```
dtparam=spi=on
dtparam=i2c_arm=on
```

Puis :

```bash
sudo reboot
```

Après reboot, vérifie :

```bash
ls /dev/spidev*
# doit afficher /dev/spidev0.0 et /dev/spidev0.1

ls /dev/i2c*
# doit afficher au moins /dev/i2c-1

sudo apt install -y i2c-tools
sudo i2cdetect -y 1
# doit faire apparaître 0x39 (STTS751) et 0x60 (DAC AD5338R)
```

## (Optionnel) Désactiver la console série

Si à la doc 04 tu remarques que `GPIO 14/15` (UART) ou un autre GPIO te pose
problème pour le reset du SX1302, désactive la console série :

```bash
sudo raspi-config nonint do_serial_cons 1   # console désactivée
sudo raspi-config nonint do_serial_hw 0     # hardware UART activé (utile rarement)
```

## Fixer l'IP (recommandé)

ChirpStack sera accessible via cette IP, autant qu'elle ne bouge pas. Le plus
simple : faire une réservation DHCP côté box pour la MAC de la M1. Sinon,
édite `/etc/dhcpcd.conf` ou crée un profil NetworkManager.

## Préparer les dépendances de la suite

```bash
sudo apt install -y \
  cmake \
  pkg-config \
  libusb-1.0-0-dev \
  apt-transport-https \
  dirmngr \
  gnupg
```

À ce stade ton OS est prêt. Place à la doc 04 pour faire vivre le SX1302.
