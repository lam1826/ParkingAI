from starlette.requests import Request


def get_client_ip(request: Request) -> str | None:
    """Return Fly's authenticated edge address, falling back to the peer."""
    fly_client_ip = request.headers.get("fly-client-ip", "").strip()
    if fly_client_ip:
        return fly_client_ip[:64]
    return request.client.host[:64] if request.client else None
