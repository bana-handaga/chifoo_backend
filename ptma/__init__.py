"""
ptma/__init__.py
PyMySQL fallback jika mysqlclient tidak tersedia di hosting.
"""
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
