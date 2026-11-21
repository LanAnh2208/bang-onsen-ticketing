from django import template

register = template.Library()


@register.filter(name='vnd')
def format_vnd(value):
    try:
        num = round(float(value))
        return f"{num:,}".replace(",", ".") + " VNĐ"
    except (ValueError, TypeError):
        return "0 VNĐ"