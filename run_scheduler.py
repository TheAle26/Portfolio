import os
import django
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysiteFulbo.settings')
django.setup()

from tracking.management.commands.generate_daily_report import Command as ReportCommand

logger = logging.getLogger(__name__)

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
    scheduler = BlockingScheduler()

    # Programamos la tarea a las 2:00 AM todos los días
    scheduler.add_job(
        generar_reporte_diario,
        trigger=CronTrigger(hour=0, minute=25),
        id='reporte_diario',
        name='Generación de Reportes de Telemetría',
        replace_existing=True
    )

    logger.info("🚀 [SCHEDULER] Motor de tareas iniciado. Esperando la próxima ejecución (02:00 AM)...")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass