#!/usr/bin/env python3
"""
Enregistre une gateway LoRaWAN dans ChirpStack via l'API gRPC.

La région opérée par la gateway est implicite : ChirpStack matche les
messages MQTT par préfixe de topic (ex : `eu868/gateway/<EUI>/...` →
configuration EU868). Le Gateway proto ne porte donc pas de champ région.

Variables d'environnement attendues (chargées depuis `.env` à la racine) :
    CHIRPSTACK_SERVER       host:port ChirpStack       ex. 192.168.2.136:8080
    CHIRPSTACK_API_TOKEN    token API globale (Bearer JWT)

Exemple :
    set -a && source .env && set +a
    .venv/bin/python scripts/register_gateway.py \\
        --eui 0016c001f10c84bf \\
        --name sensecap-m1 \\
        --description "SenseCAP M1 Pi4B EU868 (indoor)"
"""
import argparse
import os
import sys

import grpc
from chirpstack_api import api


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eui", required=True,
                        help="Gateway EUI64 (16 caractères hex, sans séparateur)")
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--stats-interval", type=int, default=30,
                        help="Doit matcher la stat_interval du packet forwarder")
    parser.add_argument("--tenant-id", default=None,
                        help="UUID du tenant (par défaut : le 1er listé)")
    args = parser.parse_args()

    server = os.environ.get("CHIRPSTACK_SERVER", "127.0.0.1:8080")
    token = os.environ.get("CHIRPSTACK_API_TOKEN")
    if not token:
        print("CHIRPSTACK_API_TOKEN n'est pas défini (charge .env d'abord)",
              file=sys.stderr)
        return 2

    channel = grpc.insecure_channel(server)
    auth = [("authorization", f"Bearer {token}")]

    tenant_id = args.tenant_id
    if tenant_id is None:
        tenants = api.TenantServiceStub(channel).List(
            api.ListTenantsRequest(limit=1), metadata=auth)
        if tenants.total_count == 0:
            print("Aucun tenant trouvé — initialise ChirpStack d'abord.",
                  file=sys.stderr)
            return 1
        tenant_id = tenants.result[0].id
        print(f"Tenant : {tenants.result[0].name} ({tenant_id})")

    gw = api.Gateway(
        gateway_id=args.eui.lower(),
        name=args.name,
        description=args.description,
        tenant_id=tenant_id,
        stats_interval=args.stats_interval,
    )
    stub = api.GatewayServiceStub(channel)
    try:
        stub.Create(api.CreateGatewayRequest(gateway=gw), metadata=auth)
        print(f"Gateway {args.eui} créée.")
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.ALREADY_EXISTS:
            print(f"Gateway {args.eui} existe déjà — rien à faire.")
            return 0
        print(f"Erreur API : {e.code().name} : {e.details()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
