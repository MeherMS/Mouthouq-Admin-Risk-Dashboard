"""City-level coordinates for the admin map.

Points are placed at the city center plus a small deterministic offset,
so entities in the same city do not stack on one spot. The offset is
derived from the entity's key with a hash, so it is the same on every run.
Nothing here identifies a home or street address.
"""
import hashlib

# Approximate city centers (latitude, longitude).
CITY_CENTERS = {
    "Riyadh":  (24.7136, 46.6753),
    "Jeddah":  (21.4858, 39.1925),
    "Makkah":  (21.4225, 39.8262),
    "Madinah": (24.5247, 39.5692),
    "Dammam":  (26.4207, 50.0888),
    "Khobar":  (26.2172, 50.1971),
}

# Maximum offset from the center, in degrees (about 1.5 km at this latitude).
MAX_OFFSET_DEG = 0.015


def _unit_pair(key: str) -> tuple[float, float]:
    """Map a string key to two stable floats in [-1, 1)."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    x = int.from_bytes(digest[:4], "big") / 2**32 * 2 - 1
    y = int.from_bytes(digest[4:8], "big") / 2**32 * 2 - 1
    return x, y


def city_point(city: str, key: str) -> tuple[float, float]:
    """Return (lat, lon) for an entity in `city`.

    `key` must be unique per entity, for example "customer:123" or "store:45".
    Raises KeyError if the city is not in CITY_CENTERS.
    """
    lat0, lon0 = CITY_CENTERS[city]
    dx, dy = _unit_pair(key)
    return lat0 + dy * MAX_OFFSET_DEG, lon0 + dx * MAX_OFFSET_DEG


if __name__ == "__main__":
    # Quick self-check: the same key must always give the same point,
    # and every point must stay within the offset limit.
    for city in CITY_CENTERS:
        p1 = city_point(city, "customer:1")
        p2 = city_point(city, "customer:1")
        assert p1 == p2, f"not deterministic for {city}"
        lat0, lon0 = CITY_CENTERS[city]
        assert abs(p1[0] - lat0) <= MAX_OFFSET_DEG
        assert abs(p1[1] - lon0) <= MAX_OFFSET_DEG
    print("geo.py self-check passed for", len(CITY_CENTERS), "cities")