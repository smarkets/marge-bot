FROM python:3.9

COPY requirements_frozen.txt /requirements.txt
RUN pip install -r requirements.txt

COPY marge/ /marge/
COPY marge.app /marge.app

CMD ["/marge.app"]
