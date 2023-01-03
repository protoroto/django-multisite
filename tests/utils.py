from django.test import RequestFactory as DjangoRequestFactory


class RequestFactory(DjangoRequestFactory):
    def __init__(self, host):
        super().__init__()
        self.host = host

    def get(self, path, data=None, host=None, **extra):
        if host is None:
            host = self.host
        if not data:
            data = {}
        return super().get(path=path, data=data, HTTP_HOST=host, **extra)
