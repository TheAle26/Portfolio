from django.core.management.base import BaseCommand

from changomas.notifications import dispatch_email_deliveries


class Command(BaseCommand):
    help = 'Despacha emails pendientes de alertas de precios.'

    def add_arguments(self, parser):
        parser.add_argument('--send', action='store_true', help='Autoriza el envío SMTP real.')
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        result = dispatch_email_deliveries(send=options['send'], limit=options['limit'])
        self.stdout.write(str(result))
