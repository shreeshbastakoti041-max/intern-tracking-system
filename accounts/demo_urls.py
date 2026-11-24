from django.urls import path

from . import demo

urlpatterns = [
    path("", demo.demo_home, name="demo_home"),
    path("as/<str:role>/", demo.demo_login, name="demo_login"),
]
