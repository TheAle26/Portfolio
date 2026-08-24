from django.test import SimpleTestCase

from tracking.management.commands.simular_viaje import calcular_distancia
from tracking.simulated_routes import ROUTE_POINT_COUNTS, SIMULATED_ROUTES


class SimulatedRoutesTests(SimpleTestCase):
    def test_expected_routes_and_point_counts_are_embedded(self):
        self.assertEqual(
            ROUTE_POINT_COUNTS,
            {
                "123456789012345": 2575,
                "987654321098765": 514,
            },
        )

    def test_every_route_contains_valid_coordinate_pairs(self):
        for points in SIMULATED_ROUTES.values():
            self.assertTrue(points)
            for latitude, longitude in points:
                self.assertGreaterEqual(latitude, -90)
                self.assertLessEqual(latitude, 90)
                self.assertGreaterEqual(longitude, -180)
                self.assertLessEqual(longitude, 180)

    def test_distance_calculation_still_accepts_embedded_points(self):
        first, second = SIMULATED_ROUTES["123456789012345"][:2]
        self.assertGreater(calcular_distancia(*first, *second), 0)
