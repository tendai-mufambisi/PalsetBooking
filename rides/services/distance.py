from typing import Tuple
import logging
import math
import requests
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class DistanceService:
    """DistanceService implementation using Google Distance Matrix API with server-side caching.

    Public method:
        get_distance_km(origin: Tuple[float,float], destination: Tuple[float,float], use_cache: bool = True) -> float

    Caching:
        Stores results in Django cache under key `distance:{lat1:.6f}:{lng1:.6f}:{lat2:.6f}:{lng2:.6f}`
        Timeout controlled with `settings.GOOGLE_DISTANCE_CACHE_TIMEOUT` (seconds).
    """

    @staticmethod
    def _cache_key(lat1: float, lng1: float, lat2: float, lng2: float) -> str:
        return f"distance:{lat1:.6f}:{lng1:.6f}:{lat2:.6f}:{lng2:.6f}"

    @staticmethod
    def get_distance_km(origin: Tuple[float, float], destination: Tuple[float, float], use_cache: bool = True) -> float:
        if not origin or not destination or len(origin) != 2 or len(destination) != 2:
            raise ValueError("origin and destination must be (lat, lng) tuples")

        # Prefer a server-specific key; fall back to the legacy single key if not provided
        api_key = getattr(settings, "GOOGLE_MAPS_SERVER_KEY", None) or getattr(settings, "GOOGLE_MAPS_API_KEY", None)
        # If no server key is configured, fall back to a local haversine distance
        if not api_key:
            logger.warning("No Google Maps server API key configured; using haversine fallback")
            lat1, lng1 = float(origin[0]), float(origin[1])
            lat2, lng2 = float(destination[0]), float(destination[1])
            distance_km = DistanceService._haversine_km(lat1, lng1, lat2, lng2)
            # cache the computed value where appropriate
            try:
                if use_cache:
                    cache.set(DistanceService._cache_key(lat1, lng1, lat2, lng2), distance_km,
                              getattr(settings, "GOOGLE_DISTANCE_CACHE_TIMEOUT", 6 * 3600))
            except Exception:
                logger.exception("Failed to set distance cache (non-fatal)")
            return distance_km

        lat1, lng1 = float(origin[0]), float(origin[1])
        lat2, lng2 = float(destination[0]), float(destination[1])

        key = DistanceService._cache_key(lat1, lng1, lat2, lng2)
        if use_cache:
            cached = cache.get(key)
            if cached is not None:
                logger.debug("distance cache hit for %s -> %s = %s km", origin, destination, cached)
                return float(cached)

        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "units": "metric",
            "origins": f"{lat1},{lng1}",
            "destinations": f"{lat2},{lng2}",
            "key": api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.exception("Google Distance Matrix request failed")
            # Fall back to haversine if the remote API call fails
            try:
                distance_km = DistanceService._haversine_km(lat1, lng1, lat2, lng2)
                logger.warning("Using haversine fallback after requests error")
                return distance_km
            except Exception:
                raise RuntimeError(f"Error calling Google Distance Matrix API: {exc}")

        if data.get("status") != "OK":
            logger.error("Google API returned non-OK status: %s", data)
            # fallback to haversine rather than failing the whole flow
            try:
                distance_km = DistanceService._haversine_km(lat1, lng1, lat2, lng2)
                logger.warning("Using haversine fallback after non-OK Google response")
                return distance_km
            except Exception:
                raise RuntimeError(f"Google Distance Matrix API error: {data.get('status')}")

        try:
            element = data["rows"][0]["elements"][0]
        except Exception as exc:
            logger.exception("Unexpected Distance Matrix response format")
            raise RuntimeError("Unexpected Distance Matrix response format") from exc

        if element.get("status") != "OK":
            logger.error("Element status not OK: %s", element)
            try:
                distance_km = DistanceService._haversine_km(lat1, lng1, lat2, lng2)
                logger.warning("Using haversine fallback after element status not OK")
                return distance_km
            except Exception:
                raise RuntimeError(f"Route not available: {element.get('status')}")

        meters = element["distance"]["value"]
        distance_km = float(meters) / 1000.0

        # Cache result
        timeout = getattr(settings, "GOOGLE_DISTANCE_CACHE_TIMEOUT", 6 * 3600)
        try:
            cache.set(key, distance_km, timeout=timeout)
        except Exception:
            logger.exception("Failed to set distance cache (non-fatal)")

        logger.debug("Computed distance %s km for %s -> %s", distance_km, origin, destination)
        return distance_km

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Compute great-circle distance between two points (in kilometers).

        This is a fallback when the Distance Matrix API is unavailable.
        """
        # Convert decimal degrees to radians
        rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = rlat2 - rlat1
        dlon = rlon2 - rlon1
        a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(min(1, math.sqrt(a)))
        # Earth's radius in kilometers (average)
        R = 6371.0088
        return float(R * c)

