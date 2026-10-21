"""Política de egress pública para descargas, redirecciones y recursos del navegador.

No permite esquemas distintos de HTTP(S), credenciales embebidas ni direcciones
no globales. Devuelve los sockaddr ya resueltos para que el transporte conecte a
una IP validada, evitando una segunda resolución DNS en la conexión.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


def destinos_publicos(url: str) -> tuple[str, int, list[tuple[int, int, int, tuple]]]:
    """Valida URL HTTP(S) y devuelve host, puerto y destinos IP globales fijables."""
    try:
        partes = urlsplit(url)
        host = partes.hostname
        puerto = partes.port or (443 if partes.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise ValueError(f"URL malformada: {exc}") from exc
    esquema = partes.scheme.lower()
    if esquema not in ("http", "https"):
        raise ValueError("solo se permiten URLs HTTP o HTTPS")
    if not host or partes.username is not None or partes.password is not None:
        raise ValueError("URL sin host válido o con credenciales embebidas")
    host = host.rstrip(".").encode("idna").decode("ascii").lower()
    if not host or "%" in host or host == "localhost" or host.endswith((".localhost", ".local", ".example", ".invalid", ".test")):
        raise ValueError("host local o reservado bloqueado")
    if not 1 <= puerto <= 65535:
        raise ValueError("puerto fuera de rango")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, puerto, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError(f"no se pudo resolver el host: {exc}") from exc
        destinos = []
        vistos = set()
        for familia, tipo, protocolo, _, sockaddr in infos:
            ip_texto = sockaddr[0].split("%", 1)[0]
            try:
                ip_resuelta = ipaddress.ip_address(ip_texto)
            except ValueError as exc:
                raise ValueError("DNS devolvió una dirección IP inválida") from exc
            if not ip_resuelta.is_global or (ip_resuelta.ipv4_mapped and not ip_resuelta.ipv4_mapped.is_global):
                raise ValueError(f"DNS incluye destino no público: {ip_resuelta}")
            clave = (familia, tipo, protocolo, sockaddr)
            if clave not in vistos:
                destinos.append(clave)
                vistos.add(clave)
    else:
        if not ip.is_global or (ip.ipv4_mapped and not ip.ipv4_mapped.is_global):
            raise ValueError(f"destino no público bloqueado: {ip}")
        familia = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
        sockaddr = (str(ip), puerto, 0, 0) if familia == socket.AF_INET6 else (str(ip), puerto)
        destinos = [(familia, socket.SOCK_STREAM, 0, sockaddr)]

    if not destinos:
        raise ValueError("el host no resolvió a direcciones públicas")
    return host, puerto, destinos


def conectar_fijado(destinos: list[tuple[int, int, int, tuple]], timeout: float | None, source_address=None) -> socket.socket:
    """Conecta solo a uno de los sockaddr previamente validados, sin nueva consulta DNS."""
    ultimo_error: OSError | None = None
    for familia, tipo, protocolo, sockaddr in destinos:
        sock = socket.socket(familia, tipo, protocolo)
        try:
            if timeout is not None:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            ultimo_error = exc
            sock.close()
    if ultimo_error:
        raise ultimo_error
    raise OSError("no hay direcciones públicas para conectar")
