# 06 — Vérification de bout en bout

But : confirmer que la chaîne complète **fonctionne** et qu'un capteur LoRaWAN
peut joindre ton réseau privé.

## 1. La gateway est vue par ChirpStack

Dans l'UI (`http://<ip>:8080`, login `admin`/`admin` à changer) :

1. **Tenants** → `ChirpStack` (par défaut).
2. **Gateways** → **Add gateway**.
   - **Name** : `sencap-m1-01`.
   - **Gateway ID** : le `gateway_ID` que tu as noté à la fin de la doc 04
     (16 hex). Sans `0x`.
   - **Region** : `eu868`.
   - Sauve.
3. Sur la fiche de la gateway, le champ **Last seen** doit passer en vert au
   bout de 30 s à 1 min (le packet forwarder envoie un keep-alive toutes les
   ~10 s).

Si **Last seen** reste vide :

- `journalctl -u lora-pkt-fwd -f` — vois-tu des envois UDP ?
- `journalctl -u chirpstack-gateway-bridge -f` — reçoit-il les PUSH_DATA ?
- `mosquitto_sub -h 127.0.0.1 -t 'eu868/#' -v` — vois-tu des messages MQTT ?

Tu remontes le tuyau jusqu'à trouver le maillon muet.

## 2. Créer un device profile

**Device profiles** → **Add**.

- Name : `generic-otaa-eu868`.
- Region : `eu868`.
- MAC version : `LoRaWAN 1.0.3`.
- Regional Parameters revision : `RP002-1.0.3` (ou `A` selon l'UI).
- Join (OTAA / ABP) : **OTAA** (le plus courant).
- Adv. payload codec : aucun pour le test, on lira la trame brute.

## 3. Créer une application + un device

**Applications** → **Add** → `test-app`.

Dans `test-app` → **Devices** → **Add device** :

- DevEUI : celui imprimé sur ton capteur (ou généré pour un node DIY).
- Name : `test-node-01`.
- Device profile : `generic-otaa-eu868`.

Puis **OTAA keys** :

- AppKey : celle livrée par le fabricant (ou que tu as flashée toi-même).

## 4. Faire émettre le capteur

Allume le capteur, lance son join. Dans l'UI ChirpStack :

- **Devices** → `test-node-01` → onglet **LoRaWAN frames** : tu dois voir un
  **JoinRequest** entrant, puis un **JoinAccept** sortant.
- Onglet **Events** : un événement `joined` apparaît.
- Premier uplink applicatif : onglet **Events** → tu vois `up` avec le
  payload hex.

## 5. Si rien ne se passe

Checklist rapide :

- **Antenne 868 MHz vissée** sur le SMA ? (sinon, RX très atténué).
- Le capteur est-il bien en EU868 ?
- Les 8 canaux EU868 du `global_conf.json` correspondent-ils aux canaux de
  join du capteur (les 3 canaux par défaut `868.1 / 868.3 / 868.5` doivent y
  être) ?
- DevEUI / AppKey : recopiés sans coquille (attention aux `0` vs `O`).
- Distance et obstacles : tente un test à 1-2 m, antenne dégagée.

## 6. Bonus : sniffer brut

Pour debug, tu peux installer `tcpdump` et voir le trafic UDP local :

```bash
sudo apt install -y tcpdump
sudo tcpdump -i lo -n udp port 1700 -A
```

Et côté MQTT :

```bash
mosquitto_sub -h 127.0.0.1 -t '#' -v
```

## Et après ?

- Mettre la passerelle dans son boîtier, fixer l'antenne dehors, faire un
  test de portée.
- Sauvegarder `/etc/chirpstack/`, `/etc/chirpstack-gateway-bridge/`,
  `~/sx1302_hal/packet_forwarder/global_conf.json` dans ce dépôt (sous
  `config/`, avec les secrets retirés).
- Mettre en place un backup régulier de la base Postgres (`pg_dump`).
- (Optionnel) Reverse-proxy + HTTPS via Caddy ou nginx si tu veux ouvrir la
  web UI au-delà du LAN.
