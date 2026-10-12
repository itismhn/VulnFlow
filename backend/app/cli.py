"""Admin CLI: `rm-admin create-admin`, `rm-admin demo`, ..."""

import secrets
import string
from pathlib import Path

import typer
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.security import hash_password, password_problems
from app.models import Network, User
from app.models.enums import Role

cli = typer.Typer(help="Report Manager administration", no_args_is_help=True)


def _random_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(20))
        if not password_problems(pw):
            return pw


@cli.command("create-admin")
def create_admin(
    username: str = typer.Option("admin", help="Login name"),
    email: str = typer.Option("admin@example.com", help="Email address"),
    password: str | None = typer.Option(None, help="Password (random if omitted)", hide_input=True),
) -> None:
    """Create an admin account. The user must change the password on first login."""
    pw = password or _random_password()
    problems = password_problems(pw)
    if problems:
        typer.secho("Password " + ", ".join(problems), fg="red")
        raise typer.Exit(1)
    with SessionLocal() as db:
        if db.scalar(select(User).where(func.lower(User.username) == username.lower())):
            typer.secho(f"User '{username}' already exists", fg="yellow")
            raise typer.Exit(1)
        db.add(
            User(
                username=username.lower(),
                email=email.lower(),
                full_name="Administrator",
                role=Role.ADMIN,
                password_hash=hash_password(pw),
                must_change_password=True,
            )
        )
        db.commit()
    typer.secho(f"Admin '{username}' created.", fg="green")
    if not password:
        typer.echo(f"Temporary password: {pw}")
    typer.echo("You will be asked to change it at first login.")


@cli.command("demo-files")
def demo_files(
    out: Path = typer.Option(Path("demo-data"), help="Output directory"),
    months: int = typer.Option(4, help="Number of monthly scans"),
    hosts_per_network: int = typer.Option(12),
) -> None:
    """Write synthetic .nessus files (fictional data, safe to share)."""
    from app.services.demo import generate_series

    for path in generate_series(out, months=months, per_network=hosts_per_network):
        typer.echo(path)


@cli.command("seed-demo")
def seed_demo(months: int = typer.Option(4), hosts_per_network: int = typer.Option(12)) -> None:
    """Load demo networks and a series of synthetic scans directly into the database."""
    import hashlib
    import tempfile

    from app.core.storage import scan_file_path
    from app.models import Scan
    from app.services import networks as network_service
    from app.services.demo import NETWORKS, generate_series
    from app.services.ingest import ingest_scan

    with SessionLocal() as db:
        for name, cidr, zone, crit in NETWORKS:
            if not db.scalar(select(Network).where(Network.cidr == cidr)):
                db.add(Network(name=name, cidr=cidr, zone=zone, criticality=crit, owner="IT Operations"))
        db.flush()
        network_service.reassign_assets(db)
        db.commit()

        admin = db.scalar(select(User).where(User.role == Role.ADMIN).order_by(User.id))
        with tempfile.TemporaryDirectory() as tmp:
            for path in generate_series(Path(tmp), months=months, per_network=hosts_per_network):
                data = path.read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                if db.scalar(select(Scan.id).where(Scan.sha256 == sha)):
                    continue
                dest = scan_file_path(sha)
                dest.write_bytes(data)
                scan = Scan(
                    name=path.name,
                    filename=path.name,
                    sha256=sha,
                    file_path=str(dest),
                    size_bytes=len(data),
                    uploaded_by_id=admin.id if admin else None,
                )
                db.add(scan)
                db.flush()
                stats = ingest_scan(db, scan)
                db.commit()
                typer.echo(f"Imported {path.name}: {stats.hosts} hosts, {stats.new} new, {stats.fixed} fixed")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
