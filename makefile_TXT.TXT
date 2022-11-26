POETRY = poetry run
WORKDIR = yatube
TEMPLATES-DIR = $(WORKDIR)/templates
MANAGE = $(POETRY) python $(WORKDIR)/manage.py

style:
	$(POETRY) black -S -l 79 $(WORKDIR)
	$(POETRY) isort $(WORKDIR)
	$(POETRY) djhtml -i -t 2 $(WORKDIR)

lint:
	$(POETRY) flake8
	$(POETRY) mypy $(WORKDIR)

test:
	$(POETRY) pytest -vv

run:
	$(MANAGE) runserver

migrate:
	$(MANAGE)  makemigrations
	$(MANAGE)  migrate

unittest:
	$(MANAGE) test yatube
