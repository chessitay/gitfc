install:
	pip3 install .

dev:
	pip3 install -e .

uninstall:
	pip3 uninstall future-commit -y

test:
	python3 -m pytest tests/ -v
