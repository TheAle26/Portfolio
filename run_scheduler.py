import os
import django
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysiteFulbo.settings')
django.setup()

from django.core.management import call_command

from tracking.management.commands.generate_daily_report import Command as ReportCommand

logger = logging.getLogger(__name__)

def scrapear_supermercados():
    logger.info("⏰ [SCHEDULER] Iniciando scrape de ChangoMás, Carrefour y Disco")
    try:
        call_command('scrape_supermarkets')
        logger.info("✅ [SCHEDULER] Scrape de supermercados finalizado con éxito.")
    except Exception as e:
        logger.exception(f"❌ [SCHEDULER] Error en el scrape de supermercados: {str(e)}")
        raise

def generar_reporte_diario():
    
    logger.info("⏰ [SCHEDULER] Iniciando tarea programada: Generar Reporte Diario")
    try:
        # Instanciamos tu comando y lo corremos como si lo llamaras por consola
        cmd = ReportCommand()
        cmd.handle()
        logger.info("✅ [SCHEDULER] Tarea finalizada con éxito.")
    except Exception as e:
        logger.error(f"❌ [SCHEDULER] Error al generar el reporte: {str(e)}")

if __name__ == '__main__':
    # Usamos BlockingScheduler porque este contenedor no va a hacer otra cosa más que esto
    # TZ explícita: el contenedor corre en UTC, así que sin esto los horarios
    # de los jobs se interpretarían en UTC y correrían 3 h antes de lo esperado.
    scheduler = BlockingScheduler(timezone='America/Argentina/Buenos_Aires')

    # Programamos la tarea a las 2:00 AM todos los días
    scheduler.add_job(
        generar_reporte_diario,
        trigger=CronTrigger(hour=0, minute=25),
        id='reporte_diario',
        name='Generación de Reportes de Telemetría',
        replace_existing=True
    )

    # Scrape diario de precios de MasOnline a las 3:00 AM (después del reporte)
    scheduler.add_job(
        scrapear_supermercados,
        trigger=CronTrigger(hour=3, minute=0),
        id='scrape_supermarkets',
        name='Scrape de ChangoMás, Carrefour y Disco',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    logger.info("🚀 [SCHEDULER] Jobs: reporte diario (00:25) y supermercados (03:00).")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
