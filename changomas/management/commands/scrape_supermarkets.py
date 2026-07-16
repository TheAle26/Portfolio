"""Releva secuencialmente los catalogos configurados del tracker."""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from changomas.scraper import STORE_CONFIGS


class Command(BaseCommand):
    help = 'Scrapea ChangoMás, Carrefour y Disco, conservando historiales separados.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store',
            action='append',
            choices=tuple(STORE_CONFIGS),
            help='Limita la corrida a una tienda. Se puede repetir.',
        )
        parser.add_argument('--delay', type=float, default=0.3)
        parser.add_argument('--max-categories', type=int, default=None)
        parser.add_argument('--keep-days', type=int, default=30)

    def handle(self, *args, **options):
        stores = options['store'] or list(STORE_CONFIGS)
        failures = []

        for store_slug in stores:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'=== {STORE_CONFIGS[store_slug].name} ==='
            ))
            try:
                call_command(
                    'scrape_masonline',
                    store=store_slug,
                    delay=options['delay'],
                    max_categories=options['max_categories'],
                    keep_days=options['keep_days'],
                    stdout=self.stdout,
                    stderr=self.stderr,
                )
            except Exception as exc:  # una tienda no debe bloquear las restantes
                failures.append((store_slug, str(exc)))
                self.stderr.write(self.style.ERROR(
                    f'{STORE_CONFIGS[store_slug].name} falló: {exc}'
                ))

        if failures:
            failed_names = ', '.join(STORE_CONFIGS[slug].name for slug, _ in failures)
            raise CommandError(f'Finalizó con errores en: {failed_names}')

