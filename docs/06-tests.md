# 06 — Vérification de bout en bout (via API)

But : confirmer que la chaîne complète fonctionne et qu'on peut administrer
ChirpStack **entièrement en API**. L'UI web reste disponible pour un coup
d'œil mais on n'en a pas besoin pour valider.

## Pré-requis : SDK Python et token

Côté ton PC :

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Puis charge le `.env` (créé à la doc 05) :

```bash
set -a && source .env && set +a
echo $CHIRPSTACK_SERVER       # ex. 192.168.2.136:8080
echo ${CHIRPSTACK_API_TOKEN:0:20}…   # début du token
```

## 1. Enregistrer la gateway

Le script `scripts/register_gateway.py` se charge de :

- lister les tenants (et prendre le premier — le tenant `ChirpStack` par
  défaut, créé à l'init de la base) ;
- créer la gateway avec l'EUI64, le nom et la `stats_interval` souhaitée.

```bash
.venv/bin/python scripts/register_gateway.py \
    --eui 0016c001f10c84bf \
    --name sensecap-m1 \
    --description "SenseCAP M1 Pi4B EU868 (indoor)"
```

Sortie attendue :

```
Tenant : ChirpStack (835c8443-...)
Gateway 0016c001f10c84bf créée.
```

Le script est **idempotent** : un second appel renvoie « existe déjà »
plutôt que de planter.

## 2. Vérifier l'état de la gateway

Une dizaine de lignes Python suffit, à coller dans ta session (ou à
extraire en script si tu veux le réutiliser) :

```python
import os, grpc
from chirpstack_api import api

ch = grpc.insecure_channel(os.environ["CHIRPSTACK_SERVER"])
auth = [("authorization", f"Bearer {os.environ['CHIRPSTACK_API_TOKEN']}")]

resp = api.GatewayServiceStub(ch).Get(
    api.GetGatewayRequest(gateway_id="0016c001f10c84bf"),
    metadata=auth,
)
gw = resp.gateway
print(f"Name        : {gw.name}")
print(f"EUI         : {gw.gateway_id}")
print(f"Created at  : {resp.created_at.ToDatetime()}")
print(f"Last seen   : {resp.last_seen_at.ToDatetime() if resp.last_seen_at.seconds else 'NEVER'}")
```

**`Last seen` doit s'actualiser toutes les ~30 s** (la `stats_interval`).
Si `NEVER` persiste, déroule la chaîne :

- `journalctl -u lora-pkt-fwd -f` : le forwarder pousse-t-il en UDP ?
- `journalctl -u chirpstack-gateway-bridge -f` : voit-on
  « publishing event event=stats » ?
- `mosquitto_sub -h 127.0.0.1 -t 'eu868/#' -v` : les messages MQTT arrivent ?
- `journalctl -u chirpstack -f | grep gateway` : ChirpStack matche-t-il
  les topics ?

## 3. Aller plus loin — applications, devices, payloads

L'API expose tout :

| Service | Méthode | Utilité |
| --- | --- | --- |
| `TenantService` | `Get`, `Update` | Tenant et settings |
| `ApplicationService` | `Create`, `List` | Applications |
| `DeviceProfileService` | `Create` | Profils OTAA/ABP, MAC version |
| `DeviceService` | `Create`, `Get`, `Activate` | Devices OTAA/ABP |
| `DeviceService` | `GetEventLogs` | Trames RX en temps réel (streaming) |
| `GatewayService` | `GetMetrics`, `GetDutyCycleMetrics` | Stats RF |

Tu peux découvrir les types avec :

```bash
.venv/bin/python3 -c "
from chirpstack_api import api
print([x for x in dir(api) if 'Device' in x][:30])
"
```

Pour la suite (enregistrer un capteur, écouter ses uplinks), prochaine
étape : un script `scripts/register_device.py` sur le même modèle.

## 4. UI en complément (optionnel)

Si tu veux un dashboard visuel ponctuellement (graphes RSSI/SNR, paquets
reçus dans le temps) :

```
http://<ip-de-la-passerelle>:8080
```

Toutes les ressources créées par l'API sont visibles dans l'UI, et vice
versa.

## Archiver l'ensemble des trames reçues

**Par défaut, aucune trame n'est stockée** :

| Source | Contenu | Persistance |
| --- | --- | --- |
| `journalctl -u lora-pkt-fwd` | métadonnées RF agrégées | systemd journal |
| `journalctl -u chirpstack-gateway-bridge` | `uplink_id=N` (id seul) | systemd journal |
| MQTT `eu868/.../event/up` | trame + métadonnées radio | QoS=0 non retenu, éphémère |
| ChirpStack Postgres | tables admin, **pas** de table de trames | persistant mais vide pour les trames |
| ChirpStack Redis | uplinks des devices **enregistrés** | TTL court |

Pour avoir une archive complète (y compris des devices non enregistrés du
voisinage), le dépôt fournit :

- `scripts/frame_logger.py` — subscriber MQTT qui écrit chaque trame en
  **NDJSON** (1 ligne JSON / trame), avec phy_payload en hex pour
  re-décodage offline.
- `scripts/frame-logger.service` — unit systemd qui le lance au boot.

### Déploiement sur la passerelle

```bash
ssh pi@sensecap-gateway.local
mkdir -p ~/frame-logger && cd ~/frame-logger
python3 -m venv .venv
.venv/bin/pip install paho-mqtt chirpstack-api
exit
```

Depuis ton PC :

```bash
scp scripts/frame_logger.py pi@sensecap-gateway.local:/home/pi/frame-logger/
scp scripts/frame-logger.service pi@sensecap-gateway.local:/tmp/

ssh pi@sensecap-gateway.local '
  sudo install -d -o pi -g pi /var/log/chirpstack-frames
  sudo install -m 644 /tmp/frame-logger.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now frame-logger
  systemctl is-active frame-logger
'
```

### Exploiter l'archive

L'archive vit dans `/var/log/chirpstack-frames/frames.ndjson`. Une ligne =
une trame. Quelques requêtes utiles avec `jq` :

```bash
# Tous les DevAddr vus, avec leur fréquence d'apparition
jq -r 'select(.dev_addr) | .dev_addr' frames.ndjson | sort | uniq -c | sort -rn

# Devices proches (RSSI > -80)
jq -c 'select(.rssi > -80)' frames.ndjson

# Histogramme SF
jq -r 'select(.sf) | "SF\(.sf)"' frames.ndjson | sort | uniq -c

# Stats par device : nb trames, RSSI moyen
jq -sr 'group_by(.dev_addr) | map({
    dev_addr: .[0].dev_addr,
    n: length,
    rssi_avg: (map(.rssi) | add/length)
  }) | sort_by(-.n) | .[]' frames.ndjson | head -20

# Rotation (à appeler via cron / logrotate)
mv frames.ndjson frames-$(date +%F).ndjson
systemctl reload frame-logger || systemctl restart frame-logger
```

Pour une analyse en Python, c'est trivial à charger :

```python
import json
with open("frames.ndjson") as f:
    frames = [json.loads(l) for l in f]
```

### Volume attendu

~200 octets par ligne NDJSON. Sur une moyenne observée de 18 trames/h
(zone urbaine FR), ça donne ~85 ko/jour, ~30 Mo/an. Pas besoin de
rotation agressive ; un `logrotate` mensuel suffit.

## Et après ?

- Mettre la passerelle dans son boîtier, fixer l'antenne dehors, faire un
  test de portée.
- Sauvegarder `/etc/chirpstack/`, `/etc/chirpstack-gateway-bridge/`,
  `~/sx1302_hal/packet_forwarder/global_conf.json` dans ce dépôt (sous
  `config/`, secrets retirés).
- Backup régulier de la base Postgres :
  `sudo -u postgres pg_dump chirpstack | gzip > chirpstack-$(date +%F).sql.gz`
- (Optionnel) Reverse-proxy + HTTPS via Caddy ou nginx si tu ouvres la web
  UI / l'API gRPC au-delà du LAN.
