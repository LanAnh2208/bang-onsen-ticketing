from django.http import HttpResponse
from core.decorators import role_required


@role_required(['RECEPTIONIST', 'ADMIN'])
def pos_home(request):
    return HttpResponse("Màn hình bán vé & quét QR POS")