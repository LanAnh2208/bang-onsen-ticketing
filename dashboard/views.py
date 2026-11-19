from django.http import HttpResponse
from core.decorators import role_required


@role_required(['ADMIN'])
def dashboard_home(request):
    return HttpResponse("Trang quản trị Admin")