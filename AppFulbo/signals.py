# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import  Notificacion,SolicitudUnionLiga,PuntuacionPendiente,PuntajePartido #,Mensaje,
from django.urls import reverse

# @receiver(post_save, sender=Mensaje)
# def crear_notificacion_nuevo_mensaje(sender, instance, created, **kwargs):
#     if created:
#         conversacion = instance.conversacion
#         # Determinar el destinatario
#         if instance.remitente == conversacion.usuario1:
#             destinatario = conversacion.usuario2
#         else:
#             destinatario = conversacion.usuario1

#         # Generar la URL usando el name del path y el ID de la conversación
#         url = reverse('conversacion_detail', kwargs={'conversacion_id': conversacion.id})
        
#         Notificacion.objects.create(
#             usuario=destinatario,
#             tipo='MSG',
#             mensaje=f"Nuevo mensaje de {instance.remitente.username}",
#             url=url  # se almacena la URL completa
#         )


@receiver(post_save, sender=SolicitudUnionLiga)
def crear_notificacion_nueva_solicitud(sender, instance, created, **kwargs):
    if created:
        liga = instance.liga
        # Generar la URL usando el name del path y el ID de la conversación
        url = reverse('gestionar_solicitudes', kwargs={'liga_id': liga.id})
        presidentes = liga.presidentes.all()
        for presidente in presidentes:
            Notificacion.objects.create(
                usuario=presidente,
                tipo='SOL',
                mensaje=f"Solicitud union: {instance.usuario} en {instance.liga}",
                url=url  # se almacena la URL completa
            )
            
@receiver(post_save, sender=PuntajePartido)
def crear_puntuacion_pendiente(sender, instance, created, **kwargs):
    if created:
        
        PuntuacionPendiente.objects.create(
                puntaje_partido=instance,
                jugador=instance.jugador,
                partido=instance.partido,
                liga=instance.partido.liga
            )
        try:
            url = reverse('ver_partido', kwargs={'partido_id': instance.partido.id})
            Notificacion.objects.create(
                usuario=instance.jugador.usuario,
                tipo='PP',
                mensaje=f"Puntuación de jugadores disponible",
                url=url
            )
        except:
            pass

