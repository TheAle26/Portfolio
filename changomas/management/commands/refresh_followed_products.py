from django.core.management.base import BaseCommand

from changomas.jobs import refresh_followed_products


class Command(BaseCommand):
    help = 'Refresca ofertas VTEX de los productos seguidos por usuarios activos.'

    def add_arguments(self, parser):
        parser.add_argument('--delay', type=float, default=0.3)
        parser.add_argument('--max-products', type=int, default=None)

    def handle(self, *args, **options):
        result = refresh_followed_products(delay=options['delay'], max_products=options['max_products'])
        self.stdout.write(self.style.SUCCESS(str(result)))
