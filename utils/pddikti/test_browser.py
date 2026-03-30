import sys
sys.path.insert(0, '/home/ubuntu/_chifoo/chifoo_backend/utils/pddikti')
from firefox_helper import make_driver

driver = make_driver(headless=False)
print("Browser terbuka. Tekan Enter untuk tutup...")
input()
driver.quit()
print("Selesai.")
