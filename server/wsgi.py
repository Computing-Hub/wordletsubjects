"""Entry point for the teacher site.

PythonAnywhere: point the WSGI file at this module (see server/README.md).
Locally:        flask --app wsgi run --debug   (from the server folder)
"""
from keyterms import create_app

app = create_app()
