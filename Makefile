init:
	pip install --upgrade pip 
	pip install -r requirements.txt

test:
	pytest test_acrawler.py

coverage:
	pytest --cov=acrawler test_acrawler.py

install: init
	python setup.py install