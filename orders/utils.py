import secrets
import segno
import socket
from catalog.models import Location
from orders.models import Order

# Unambiguous 31-character set (no 0, O, 1, I, L)
PICKUP_CODE_CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def get_local_lan_ip():
    """
    Attempt to find the machine's local LAN IP (e.g. 192.168.x.x)
    so smartphone QR scans over local Wi-Fi resolve to this machine instead of phone's loopback.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't have to be reachable; just probes routing table
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def generate_pickup_code(location, order_date):
    """
    Generate a random 4-character pickup code avoiding look-alikes.
    Retries up to 10 times on collision with existing orders at the same location today.
    """
    for _ in range(10):
        code = ''.join(secrets.choice(PICKUP_CODE_CHARS) for _ in range(4))
        if not Order.objects.filter(location=location, order_date=order_date, pickup_code=code).exists():
            return code
    raise RuntimeError("Unable to generate a unique pickup code after 10 attempts.")


def generate_qr_svg_data_uri(url):
    """
    Generate an SVG data URI for a QR code encoding the URL using segno.
    """
    qr = segno.make(url, error='m')
    return qr.svg_data_uri(scale=5, dark='#1f2421', light='#ffffff')


def generate_qr_svg_inline(url):
    """
    Generate inline SVG element string for direct embedding in HTML templates.
    """
    qr = segno.make(url, error='m')
    return qr.svg_inline(scale=5, dark='#1f2421', light='#ffffff')
