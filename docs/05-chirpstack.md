# 05 — Installation de ChirpStack v4

On installe la stack complète **sur la passerelle elle-même** :

```
   SX1302
     │ (SPI + I2C temp sensor)
   lora_pkt_fwd                          (doc 04)
     │ (UDP 1700, JSON Semtech)
   chirpstack-gateway-bridge
     │ (MQTT topics eu868/gateway/<EUI>/...)
   mosquitto
     │ (MQTT)
   chirpstack ─── postgres ─── redis
     │ (HTTP 8080)
   navigateur
```

## Dépôt APT ChirpStack

Sur Debian Trixie (13), apt utilise désormais **Sequoia** pour la vérif des
signatures, et `apt-key` ainsi que `gpg --recv-keys` (sans dirmngr en
session root) ne fonctionnent plus de manière fiable. On récupère la clé
**en clair via HTTPS** depuis le keyserver Ubuntu, ce qui est plus robuste :

```bash
sudo apt install -y apt-transport-https ca-certificates curl
sudo install -d /etc/apt/keyrings

# Clé ChirpStack (ID 1CE2AFD36DBCCA00), ASCII-armorée
sudo curl -fsSL \
  "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x1CE2AFD36DBCCA00&options=mr" \
  -o /etc/apt/keyrings/chirpstack.asc
sudo chmod 0644 /etc/apt/keyrings/chirpstack.asc

# Dépôt ChirpStack v4 signé par cette clé
echo "deb [signed-by=/etc/apt/keyrings/chirpstack.asc] https://artifacts.chirpstack.io/packages/4.x/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/chirpstack.list

sudo apt update
```

## Mosquitto, Postgres, Redis

```bash
sudo apt install -y mosquitto mosquitto-clients postgresql redis
sudo systemctl enable --now mosquitto postgresql redis-server
```

### Mosquitto en accès anonyme local

Mosquitto 2.x refuse les connexions anonymes par défaut. Comme tout est en
localhost, on autorise l'anonymat **uniquement sur 127.0.0.1** :

```bash
sudo tee /etc/mosquitto/conf.d/local.conf <<'EOF'
allow_anonymous true
listener 1883 127.0.0.1
EOF
sudo systemctl restart mosquitto
mosquitto_pub -h 127.0.0.1 -t test -m hello && echo "MQTT OK"
```

### Postgres : rôle, base et extensions

Le DSN par défaut de ChirpStack pointe sur
`chirpstack:chirpstack@localhost/chirpstack` et les extensions `pg_trgm` +
`hstore` sont requises. Le dépôt fournit `scripts/setup-db.sql` :

```bash
# Depuis ton PC :
scp scripts/setup-db.sql pi@sensecap-gateway.local:/tmp/

# Sur le Pi :
sudo -u postgres env LANG=C LC_ALL=C psql -v ON_ERROR_STOP=1 -f /tmp/setup-db.sql
```

Vérification :

```bash
sudo -u postgres psql -d chirpstack -c "\dx"
# pg_trgm, hstore et plpgsql doivent être listés
```

> ⚠️ Mot de passe `chirpstack` = par défaut. **À changer en prod**, et
> reporter la nouvelle valeur dans `[postgresql] dsn = ...` du
> `/etc/chirpstack/chirpstack.toml`.

> 💡 Le `env LANG=C LC_ALL=C` évite le bruit Perl `Setting locale failed` si
> ta locale n'est pas complètement générée (cas fréquent sur Trixie + Pi OS
> + clavier `fr`).

## Installer ChirpStack et le Gateway Bridge

```bash
sudo apt install -y chirpstack chirpstack-gateway-bridge
```

Le paquet `chirpstack` installe la config sous `/etc/chirpstack/` avec un
fichier par région (`region_eu868.toml`, etc.).

## Configurer le Gateway Bridge

Fichier : `/etc/chirpstack-gateway-bridge/chirpstack-gateway-bridge.toml`.

Le fichier par défaut est presque bon (`udp_bind = "0.0.0.0:1700"`, MQTT
broker `tcp://127.0.0.1:1883`). Seul point à corriger : les topics doivent
être **préfixés par `eu868/`** sinon ChirpStack ne les capte pas (côté
ChirpStack, `region_eu868.toml` définit `topic_prefix = "eu868"`).

```bash
sudo sed -i 's|event_topic_template="gateway/|event_topic_template="eu868/gateway/|' \
  /etc/chirpstack-gateway-bridge/chirpstack-gateway-bridge.toml
sudo sed -i 's|command_topic_template="gateway/|command_topic_template="eu868/gateway/|' \
  /etc/chirpstack-gateway-bridge/chirpstack-gateway-bridge.toml
sudo systemctl restart chirpstack-gateway-bridge
```

Vérification :

```bash
sudo grep -E "event_topic|command_topic" /etc/chirpstack-gateway-bridge/chirpstack-gateway-bridge.toml
# event_topic_template="eu868/gateway/{{ .GatewayID }}/event/{{ .EventType }}"
# command_topic_template="eu868/gateway/{{ .GatewayID }}/command/#"

journalctl -u chirpstack-gateway-bridge -n 20 --no-pager
# Doit montrer "starting gateway udp listener addr=0.0.0.0:1700"
# puis "connected to mqtt broker"
# puis "publishing event event=stats" toutes les 30 s.
```

## Configurer ChirpStack

Fichier : `/etc/chirpstack/chirpstack.toml`.

Deux changements seulement par rapport au défaut :

1. **`enabled_regions`** : on garde uniquement `eu868` (par défaut la liste
   énumère ~15 régions, ce qui charge le serveur pour rien) :

   ```bash
   sudo python3 - <<'PY'
   import re
   f = "/etc/chirpstack/chirpstack.toml"
   t = open(f).read()
   t = re.sub(r"enabled_regions\s*=\s*\[[^\]]*\]",
              'enabled_regions = ["eu868"]', t, flags=re.S)
   open(f, "w").write(t)
   PY
   ```

2. **`[api].secret`** : remplacer `"you-must-replace-this"` par une valeur
   aléatoire (JWT signing secret) :

   ```bash
   SECRET=$(openssl rand -hex 32)
   sudo sed -i "s|secret = \"you-must-replace-this\"|secret = \"$SECRET\"|" \
     /etc/chirpstack/chirpstack.toml
   ```

Le DSN Postgres, l'URL Redis et le broker MQTT sont déjà bons par défaut.

```bash
sudo systemctl restart chirpstack
sudo systemctl status chirpstack --no-pager
```

Si le service échoue, le 1er suspect est la base Postgres : vérifier que le
rôle, la base et les extensions ont bien été créés (cf. plus haut).

## Mettre la vraie EUI du SX1302 dans le packet forwarder

Le fichier `global_conf.json` du forwarder contient encore l'EUI placeholder
`AA555A0000000000`. À remplacer par la vraie EUI relevée à la doc 04 (visible
dans `journalctl -u lora-pkt-fwd | grep "concentrator EUI"`) :

```bash
sudo sed -i \
  's/"gateway_ID": "AA555A0000000000"/"gateway_ID": "0016C0XXXXXXXXXX"/' \
  ~/sx1302_hal/packet_forwarder/global_conf.json
sudo systemctl restart lora-pkt-fwd
```

À partir de là, le bridge publie ses stats sous l'EUI réelle, par exemple
`eu868/gateway/0016c0xxxxxxxxxx/event/stats`. C'est cette EUI qu'on déclare
dans l'UI de ChirpStack (doc 06).

## Accéder à l'interface

Sur ton PC :

```
http://sensecap-gateway.local:8080
# ou
http://<ip-de-la-passerelle>:8080
```

Identifiants par défaut : `admin` / `admin`. **Change-les immédiatement**
(menu utilisateur en haut à droite).

## Activer le démarrage automatique

Les paquets activent déjà `chirpstack` et `chirpstack-gateway-bridge` au
boot. À vérifier :

```bash
for s in mosquitto postgresql redis-server chirpstack-gateway-bridge chirpstack lora-pkt-fwd; do
  printf "%-30s %s %s\n" "$s" \
    "$(systemctl is-active $s)" \
    "$(systemctl is-enabled $s)"
done
```

Tous doivent être `active enabled`.

À ce stade : tout tourne, mais on n'a encore **rien déclaré** dans
ChirpStack. C'est l'objet de la doc 06.
