from django.urls import path
from . import views

urlpatterns = [
    path('', views.store, name='store'),
    path('category/<slug:category_slug>/', views.store, name='products_by_category'),
    path('category/<slug:category_slug>/<slug:product_slug>/', views.product_detail, name='product_detail'),
    path('search/', views.search, name='search'),
    path('autocomplete/', views.autocomplete, name='autocomplete'),
    path('quick-view/<int:product_id>/', views.quick_view, name='quick_view'),
    path('compare/', views.compare, name='compare'),
    path('submit_review/<int:product_id>/', views.submit_review, name='submit_review'),
]