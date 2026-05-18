from django import template

register = template.Library()


@register.filter
def is_viewer(user):
    return user.groups.filter(name='Viewer').exists()


@register.filter
def user_role_label(user):
    if user.is_superuser:
        return 'Owner'
    if user.groups.filter(name='Viewer').exists():
        return 'Viewer'
    return 'Manager'
