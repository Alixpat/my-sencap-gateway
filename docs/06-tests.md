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
