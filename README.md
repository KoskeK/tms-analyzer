# tms-analyzer

A system that scrapes data from various sources, and puts them into a standardized format into a SQL DB for further statistical purposes. The reason why this approach, instead of just doing an IP scan, is because there is the option to save tags, which offer an insight into the current trends of new servers.

## How to use?

I am currently using this script to collect data, however the data I collected is not yet accessible for various reasons, including but not limited to concerns over ToS of the various websites used as sources and technical reasons. If one wishes to get data from this script, the only option on how to do so as of now is to run the script locally. <br>
The script is still under development, and I often change my mind about things, but I try to keep the updates as backwards compatible as possible, as I am lazy and do not want to have to migrate the DB or anything like that. 

### Running the base scripts

0. Download appropriate software. This project needs [python3](https://python.org) and [uv](https://docs.astral.sh/uv/), and install required packages for [playwright](https://github.com/feder-cr/invisible_playwright). This may change depending on your setup.
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
After setting up the project, you might want to explore the data you just collected. To do this, one can either download the .db file and use tools such as [sqlite browser](https://sqlitebrowser.org/) or [sqlviz](https://sqliteviz.com/) to take a look at it. However, a more convinient, but a bit more advanced option, is to set up [metabase](https://www.metabase.com/), and interact with the data directly from the server.

## Sources
As of now, the script is using the following websites as sources:
- https://topminecraftservers.org/sort/new
- https://minecraft-mp.com/