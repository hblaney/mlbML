"""Ballpark metadata and park factors.

The first values are conservative defaults plus known park geometry/location. Replace
or augment these with Statcast/Baseball Savant park factors as the dataset grows.
"""

from __future__ import annotations

from context import ParkSnapshot


PARKS_BY_TEAM_ID: dict[int, dict[str, float | bool | str]] = {
    108: {"name": "Angel Stadium", "lat": 33.8003, "lon": -117.8827, "runs": 0.99, "hr": 1.02, "alt": 160, "lf": 330, "cf": 396, "rf": 330, "dome": False},
    109: {"name": "Chase Field", "lat": 33.4455, "lon": -112.0667, "runs": 1.01, "hr": 1.03, "alt": 1086, "lf": 330, "cf": 407, "rf": 335, "dome": True},
    110: {"name": "Oriole Park at Camden Yards", "lat": 39.2839, "lon": -76.6217, "runs": 1.02, "hr": 0.98, "alt": 38, "lf": 333, "cf": 410, "rf": 318, "dome": False},
    111: {"name": "Fenway Park", "lat": 42.3467, "lon": -71.0972, "runs": 1.05, "hr": 0.96, "alt": 20, "lf": 310, "cf": 390, "rf": 302, "dome": False},
    112: {"name": "Wrigley Field", "lat": 41.9484, "lon": -87.6553, "runs": 1.03, "hr": 1.08, "alt": 600, "lf": 355, "cf": 400, "rf": 353, "dome": False},
    113: {"name": "Great American Ball Park", "lat": 39.0979, "lon": -84.5082, "runs": 1.04, "hr": 1.15, "alt": 489, "lf": 328, "cf": 404, "rf": 325, "dome": False},
    114: {"name": "Progressive Field", "lat": 41.4962, "lon": -81.6852, "runs": 0.99, "hr": 0.98, "alt": 653, "lf": 325, "cf": 400, "rf": 325, "dome": False},
    115: {"name": "Coors Field", "lat": 39.7561, "lon": -104.9942, "runs": 1.18, "hr": 1.12, "alt": 5200, "lf": 347, "cf": 415, "rf": 350, "dome": False},
    116: {"name": "Comerica Park", "lat": 42.3390, "lon": -83.0485, "runs": 1.00, "hr": 0.94, "alt": 600, "lf": 345, "cf": 420, "rf": 330, "dome": False},
    117: {"name": "Minute Maid Park", "lat": 29.7573, "lon": -95.3555, "runs": 1.01, "hr": 1.04, "alt": 50, "lf": 315, "cf": 409, "rf": 326, "dome": True},
    118: {"name": "Kauffman Stadium", "lat": 39.0517, "lon": -94.4803, "runs": 1.00, "hr": 0.91, "alt": 750, "lf": 330, "cf": 410, "rf": 330, "dome": False},
    119: {"name": "Dodger Stadium", "lat": 34.0739, "lon": -118.2400, "runs": 0.99, "hr": 1.02, "alt": 522, "lf": 330, "cf": 395, "rf": 330, "dome": False},
    120: {"name": "Nationals Park", "lat": 38.8730, "lon": -77.0074, "runs": 1.00, "hr": 1.00, "alt": 25, "lf": 336, "cf": 402, "rf": 335, "dome": False},
    121: {"name": "Citi Field", "lat": 40.7571, "lon": -73.8458, "runs": 0.99, "hr": 0.98, "alt": 13, "lf": 335, "cf": 408, "rf": 330, "dome": False},
    133: {"name": "Oakland Coliseum", "lat": 37.7516, "lon": -122.2005, "runs": 0.96, "hr": 0.92, "alt": 42, "lf": 330, "cf": 400, "rf": 330, "dome": False},
    134: {"name": "PNC Park", "lat": 40.4469, "lon": -80.0057, "runs": 0.98, "hr": 0.95, "alt": 730, "lf": 325, "cf": 399, "rf": 320, "dome": False},
    135: {"name": "Petco Park", "lat": 32.7076, "lon": -117.1570, "runs": 0.96, "hr": 0.94, "alt": 19, "lf": 336, "cf": 396, "rf": 322, "dome": False},
    136: {"name": "T-Mobile Park", "lat": 47.5914, "lon": -122.3325, "runs": 0.96, "hr": 0.95, "alt": 10, "lf": 331, "cf": 401, "rf": 326, "dome": True},
    137: {"name": "Oracle Park", "lat": 37.7786, "lon": -122.3893, "runs": 0.95, "hr": 0.84, "alt": 0, "lf": 339, "cf": 391, "rf": 309, "dome": False},
    138: {"name": "Busch Stadium", "lat": 38.6226, "lon": -90.1928, "runs": 0.99, "hr": 0.96, "alt": 466, "lf": 336, "cf": 400, "rf": 335, "dome": False},
    139: {"name": "Tropicana Field", "lat": 27.7682, "lon": -82.6534, "runs": 0.97, "hr": 0.96, "alt": 15, "lf": 315, "cf": 404, "rf": 322, "dome": True},
    140: {"name": "Globe Life Field", "lat": 32.7473, "lon": -97.0842, "runs": 1.00, "hr": 1.01, "alt": 560, "lf": 329, "cf": 407, "rf": 326, "dome": True},
    141: {"name": "Rogers Centre", "lat": 43.6414, "lon": -79.3894, "runs": 1.01, "hr": 1.05, "alt": 249, "lf": 328, "cf": 400, "rf": 328, "dome": True},
    142: {"name": "Target Field", "lat": 44.9817, "lon": -93.2776, "runs": 0.99, "hr": 0.96, "alt": 840, "lf": 339, "cf": 404, "rf": 328, "dome": False},
    143: {"name": "Citizens Bank Park", "lat": 39.9061, "lon": -75.1665, "runs": 1.03, "hr": 1.12, "alt": 39, "lf": 329, "cf": 401, "rf": 330, "dome": False},
    144: {"name": "Truist Park", "lat": 33.8908, "lon": -84.4678, "runs": 1.01, "hr": 1.02, "alt": 1001, "lf": 335, "cf": 400, "rf": 325, "dome": False},
    145: {"name": "Guaranteed Rate Field", "lat": 41.8300, "lon": -87.6339, "runs": 1.00, "hr": 1.10, "alt": 595, "lf": 330, "cf": 400, "rf": 335, "dome": False},
    146: {"name": "loanDepot park", "lat": 25.7781, "lon": -80.2197, "runs": 0.97, "hr": 0.92, "alt": 10, "lf": 344, "cf": 407, "rf": 335, "dome": True},
    147: {"name": "Yankee Stadium", "lat": 40.8296, "lon": -73.9262, "runs": 1.01, "hr": 1.12, "alt": 55, "lf": 318, "cf": 408, "rf": 314, "dome": False},
    158: {"name": "American Family Field", "lat": 43.0280, "lon": -87.9712, "runs": 1.00, "hr": 1.03, "alt": 620, "lf": 344, "cf": 400, "rf": 345, "dome": True},
}


def park_for_team(team_id: int) -> ParkSnapshot:
    park = PARKS_BY_TEAM_ID.get(team_id, {})
    return ParkSnapshot(
        park_factor_runs=float(park.get("runs", 1.0)),
        park_factor_hr=float(park.get("hr", 1.0)),
        altitude_ft=float(park.get("alt", 500.0)),
        left_field_ft=float(park.get("lf", 330.0)),
        center_field_ft=float(park.get("cf", 400.0)),
        right_field_ft=float(park.get("rf", 330.0)),
        foul_territory_index=1.0,
    )


def park_location(team_id: int) -> tuple[float, float, bool]:
    park = PARKS_BY_TEAM_ID.get(team_id, {})
    return float(park.get("lat", 40.0)), float(park.get("lon", -95.0)), bool(park.get("dome", False))
