from .models import Category

def menu_links(request):
    links = Category.public.all()   # customer-facing only (excludes technical categories)
    return dict(links=links)