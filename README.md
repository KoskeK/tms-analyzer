# tms-analyzer

A system that scrapes data from various (for now only one) sources, and puts them into a standardized format into a SQL DB for further statistical purposes. The reason why this approach, instead of just doing an IP scan, is because there is the option to save tags, which offer an insight into the current trends of new servers.

## How to use?

First, the question is what is the purpose. If the user is simply curious about said statistics, there will be an API and a website where this data can be viewed. The data for the API is alredy being collected, which means that the API will have much fuller data than if the user was to ran it themselves. <br><br>
However, since the API is not available as of now, the only way to interact with the data as of now is for the user to run the scraping themselve.<br>

### Running the base scripts

0. Download appropriate software. This project needs [python3](https://python.org) and [uv](https://docs.astral.sh/uv/), and install required packages packages for [playwright](https://playwright.dev/python/). This may change depending on your setup.
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
uv run src/tms_analyzer/engine/scraper.py
```
4. Run the reporter, and wait for it to finish
```sh
uv run src/tms_analyzer/engine/reporter.py
```
5. Done. All the data will be in a SQLite DB in the src/tms_analyzer/files directory, unless configuration is changed. <br>

### Configuration
The only form of configuration offered is a .env file. The only configuration option in it is the DB URL. The default configuration is SQLite, which should be more than enough for most applications. <br>
While this script does not offer more configuration option on its own, it is reccomended to set up a cronjob to gather data periodically. The reccomended way is just to run the scraper and the reporter on their own.

### What to do now?
After setting up the project, you might want to explore the data you just collected. To do this, one can either download the .db file and use tools such as [sqlite browser](https://sqlitebrowser.org/) or [sqlviz](https://sqliteviz.com/) to take a look at it. However, a more convinient, but a bit more annoying option, is to set up [metabase](https://www.metabase.com/), and interact with the data directly from the server.