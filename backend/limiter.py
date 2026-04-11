from fastapi import Request
from slowapi import Limiter


def client_ip_key(request: Request) -> str:
    """Identify the real client IP for rate limiting.

    Could You Make sits behind Cloudflare -> Railway. The immediate
    request.client.host is the proxy's IP, which would group every
    real user into one bucket. Cloudflare exposes the original client
    IP via CF-Connecting-IP; we fall back to the first hop in
    X-Forwarded-For, then to the connection IP.

    This trusts these headers, which is only safe because the public
    internet cannot reach Railway directly -- all traffic flows
    through Cloudflare. If that ever changes, this becomes spoofable.

    NOTE: Rate-limit counters live in process memory. With a single
    Railway instance that's fine; if replicas are ever scaled above 1,
    each instance will have its own counters and the effective limit
    becomes (limit * replica count). Move to a Redis storage backend
    before scaling horizontally.
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip_key)
