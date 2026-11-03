"""Punto de entrada da aplicación de reservas."""
import argparse
from datetime import date

from src.consultas import medir_consultas, probar_sobreventa
from src.reservas import inicializar_contadores


def main():
    """Interpreta o subcomando e delega o traballo nos módulos de `src`."""
    parser = argparse.ArgumentParser(description="Aplicación de reservas Camiño Aberto")
    subparsers = parser.add_subparsers(dest="comando", required=True)
    subparsers.add_parser(
        "inicializar",
        help="construír os contadores de Redis a partir das reservas de PostgreSQL",
    )

    proba = subparsers.add_parser(
        "probar-sobreventa",
        help="lanzar reservas simultáneas para comprobar que non hai sobreventa",
    )
    proba.add_argument("--prazas", type=int, default=3)
    proba.add_argument("--intentos", type=int, default=30)

    medir = subparsers.add_parser(
        "medir",
        help="comparar o tempo de consulta en PostgreSQL e Redis",
    )
    medir.add_argument("--camino", default="Francés")
    medir.add_argument("--noite", type=date.fromisoformat, default=date.today())
    medir.add_argument("--repeticions", type=int, default=100)

    args = parser.parse_args()
    if args.comando == "inicializar":
        inicializar_contadores()
    elif args.comando == "probar-sobreventa":
        probar_sobreventa(args.prazas, args.intentos)
    elif args.comando == "medir":
        postgres_ms, redis_ms = medir_consultas(
            args.camino, args.noite, args.repeticions
        )
        print(
            f"Tempo medio en {args.repeticions} consultas: "
            f"PostgreSQL {postgres_ms:.3f} ms; Redis/caché {redis_ms:.3f} ms."
        )


if __name__ == "__main__":
    main()
