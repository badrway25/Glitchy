from django.shortcuts import render
from django.db.models import Sum
from store.models import Product
from orders.models import OrderProduct

def home(request):
    # Popular = top sellers (somma quantity)
    popular_rows = (
        OrderProduct.objects
        .filter(ordered=True, order__is_ordered=True)
        .values('product')
        .annotate(total_sold=Sum('quantity'))
        .order_by('-total_sold')[:8]
    )

    popular_ids = [r['product'] for r in popular_rows]
    sold_map = {r['product']: int(r['total_sold'] or 0) for r in popular_rows}

    if popular_ids:
        popular_qs = Product.objects.filter(is_available=True, id__in=popular_ids)
        order_map = {pid: i for i, pid in enumerate(popular_ids)}
        popular_products = sorted(popular_qs, key=lambda p: order_map.get(p.id, 9999))

        # attach total_sold attribute to each product (for template)
        for p in popular_products:
            p.total_sold = sold_map.get(p.id, 0)
    else:
        popular_products = Product.objects.filter(is_available=True).order_by('-modified_date')[:8]
        for p in popular_products:
            p.total_sold = 0

    latest_products = Product.objects.filter(is_available=True).order_by('-created_date')[:8]

    context = {
        'popular_products': popular_products,
        'latest_products': latest_products,
    }
    return render(request, 'home.html', context)
