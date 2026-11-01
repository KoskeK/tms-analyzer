from tms_analyzer.engine import tms_scrape
from tms_analyzer.engine import minecraft_mp_scrape
import threading
import logging

if __name__ == "__main__":
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
    logging.info("Logging started...")

    tms = threading.Thread(
        target=tms_scrape.scrape
    )
    minecraft_mp = threading.Thread(
        target=minecraft_mp_scrape.scrape
    )
    tms.start()
    minecraft_mp.start()
    tms.join()
    minecraft_mp.join()
    logging.info("Scraping finished!")
