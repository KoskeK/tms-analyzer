# tms-analyzer

A system that scrapes data from various (for now only one) sources, and puts them into a standardized format into a SQL DB for further statistical purposes. The reason why this approach, instead of just doing an IP scan, is because there is the option to save tags, which offer an insight into the current trends of new servers.

## How to use?

First, the question is what is the purpose. If the user is simply curious about said statistics, there will be an API and a website where this data can be viewed. If, however, the wish is to run an instance of this program on their own, it is also not a complicated ordeal.<br>

### Running the base scripts

0. Download appropriate software. This project needs [python3](https://python.org) and [uv](https://docs.astral.sh/uv/)
1. Clone this repo, and run
```sh
uv sync
```
2. Go into the root directory, in this case tms-analyzer
```sh
cd tms-analyzer
```
3. Make a .env fle. You can just copy the .env.example and it will work.
```sh
cp .env.example .env
```
3. Run the scraper, and wait for it to finish
```sh
uv run src/tms_analyzer/engine/minecraft_mp_scrape.py
```
4. Run the reporter, and wait for it to finish
```sh
uv run src/tms_analyzer/engine/reporter.py
```
5. Done. All the data will be in a SQLite DB in the src/tms_analyzer/files directory, unless configuration is changed. <br>

### Configuration
The only form of configuration offered is a .env file. The only configuration option in it is the DB URL. The default configuration is SQLite, which should be more than enough for most applications. 