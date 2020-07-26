del dist\*.* /Q
python setup.py sdist bdist_wheel
twine upload --config .pypirc dist/*