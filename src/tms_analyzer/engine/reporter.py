
from mcstatus import JavaServer
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import init_db
from tms_analyzer.shared.models import Server, Report

import dns.resolver
import dns.exception

import tqdm
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


def resolve_minecraft_target(hostname):
    resolver = dns.resolver.Resolver()
    resolver.nameservers = ["1.1.1.1", "8.8.8.8"]
    resolver.timeout = 3.0
    resolver.lifetime = 5.0

    hostname = hostname.strip()

    # Preserve explicitly specified ports
    if hostname.startswith("[") and "]:" in hostname:
        return hostname, None

    if hostname.count(":") == 1:
        host, port = hostname.rsplit(":", 1)
        if port.isdigit():
            return hostname, None

    # Try Minecraft SRV lookup
    try:
        srv_answers = resolver.resolve(
            f"_minecraft._tcp.{hostname}",
            "SRV"
        )

        srv = next(iter(srv_answers))
        target = str(srv.target).rstrip(".")
        return f"{target}:{srv.port}", None

    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout
    ):
        pass

    # Fall back to A / AAAA records
    errors = []

    for record_type in ("A", "AAAA"):
        try:
            answers = resolver.resolve(hostname, record_type)
            address = str(next(iter(answers)))

            if record_type == "AAAA":
                address = f"[{address}]"

            return f"{address}:25565", None

        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.NoNameservers,
            dns.exception.Timeout
        ) as e:
            errors.append(e)

    return None, errors[-1] if errors else Exception("DNS resolution failed")


def check_server(ip, server_id):
    try:
        host, error = resolve_minecraft_target(ip)

        if error:
            return Report(
                server_id=server_id,
                online=False,
                player_count=0,
                status=f"DNS Error: {error!r}"
            )

        server = JavaServer.lookup(host)
        status = server.status()

        return Report(
            server_id=server_id,
            online=True,
            player_count=status.players.online,
            status="Normal"
        )

    except Exception as e:
        logging.warning("Error checking server %s: %s", ip, e)

        return Report(
            server_id=server_id,
            online=False,
            player_count=0,
            status=repr(e)
        )


if __name__ == "__main__":
    engine = init_db()

    try:
        with Session(engine) as session:
            servers = session.scalars(
                select(Server).where(Server.enabled == True)
            ).all()

            with tqdm.tqdm(
                total=len(servers),
                desc="Scanning servers"
            ) as pbar:

                for server in servers:
                    report = check_server(server.ip, server.id)
                    session.add(report)
                    pbar.update(1)

            session.commit()

    except Exception:
        logging.exception("Scanning failed")
        raise

    finally:
        engine.dispose()
