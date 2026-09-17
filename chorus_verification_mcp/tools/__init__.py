"""
tools/__init__.py
=================
Makes tools/ a package.  Re-exports the four tool run() callables so
the server module can import them with one line:

    from tools import reverse_search, upload_history, fact_check, web_search_fetch
"""
