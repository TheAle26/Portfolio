# portal/views.py
from django.shortcuts import render

def index(request):
    
    context = {
        'titulo': 'Alejo Vincent Home',
    }
    return render(request, 'portal/index.html', context)