import sys
print("Python executable:", sys.executable)
print("sys.path:", sys.path)
try:
    import bs4
    print("bs4 imported successfully. Version:", bs4.__version__)
    from bs4 import BeautifulSoup
    print("BeautifulSoup imported successfully")
except ImportError as e:
    print("ImportError:", e)
