from django.urls import re_path
from volontaire.consumers import TaskConsumer

# websocket_urlpatterns = [
#     re_path(r'ws/tasks/(?P<volunteer_id>\w+)/$', TaskConsumer.as_asgi()),
# ]



websocket_urlpatterns = [
    re_path(r'ws/tasks/$', TaskConsumer.as_asgi()),
]
