# PTSA - Public Transport Stop Analysis for OSM

PTSA is an interactive map showing structure and properties of public transport stops in the [OpenStreetMap data base (OSM)](https://osm.org). It's main pupose is to find tagging mistakes and inconsitencies in OSM.

This repo contains the code for extracting data from OSM (backend) and for the interactive map (frontend).

Find the [ready-to-use PTSA map online](https://gauss.whz.de/ptsa) hosted at [Zwickau University of Applied Sciences](https://whz.de). Have a look at [PTSA Help page](https://gauss.whz.de/ptsa/help.html) to better understand what you see there.

## Installation and usage

If you want to have your own PTSA instance, clone the repo and follow instructions for backend and frontend below.

### Backend

The backend is a Python script which downloads data from OSM and generates vector tiles. Steps for generating tiles:

1. Install the [`geopandas` Python package](https://geopandas.org).
2. Rename `config.json.template` in the `backend` directory to `config.json`.
3. Adjust settings in `config.json` to your needs:
   * Set `overpass_url` to your private Overpass API instance. PTSA will download several gigabytes of data. Don't use a free public instance for such massive downloads. See [Overpass API Podman image](https://github.com/jeflem/overpass-podman) to set up a private instance.
   * Depending on your Overpass API instance you may have to provide an API key via `overpass_key`.
   * Paths in `ploles_path` and `tiles_path` should point to subdirectories of PTSA's frontend HTML on your webserver. `*_tmp_path` and `*_old_path` are used while generating tiles/ploles and should reside in the frontend HTML directory, too (for performance reasons). Both are temporary directories and will be removed after tiles/ploles have been generated.
   * With `regions_mode` and `regions_codes` you may choose a subset of all available regions. `regions_mode` may be `"include"` or `"exclude"` to only process provided codes or to skip provided codes, respectively. Codes are case-sensitive and can be found in `regions.csv` (see [div4aep](https://github.com/jeflem/div4aep) on how to generate such a regions file).
   * All other settings are either self-explanatory or should not be modified. Else PTSA's results might be garbage.
4. Ensure that paths provided in `ploles_path` and `tiles_path` exist and are writable by you (or the Python script in the next step).
5. Run `python process_all.py` and wait.

A full run on one CPU core (of a 2018 server) and files on an SSD takes about 17 hours. Logs are written to the `logs` directory. The `export` directory may be cleaned after PTSA has finished its job.

If you want to rerun PTSA for one region only without loosing data from other regions, don't touch the export directory. Export directory takes about 30 GB.

Tiles directory will take about 80 GB with almost 20 million files. Check your free inode count before you start! It's a good idea to use a file system specially crafted for lots of small files (search the web for 'inode ratio' or 'mke2fs -T news').

Ploles directory will take about 20 GB with almost 5 million files. Thus, total disk usage of PTSA frontend on the webserver is about 100 GB with 25 million files.

### Frontend

The frontend is HTML and JavaScript. Get it running as follows:
1. Copy all files from the `frontend` directory to your webserver's HTML directory (usually `/var/www/html`) or some subdirectory.
2. Check `map.js` and `details.js` for the correct tile URL (the line starting with `const ptsaTilesUrl = ` close to the file's top.
3. Edit `index.html` to get a custom logo.

## Contributing

Open a GitiHub issue for bug reports. File pull requests against the dev branch.

The dev branch contains the code for next release, whereas the main branch holds the current release. There are no release numbers, because the audience will be rather small and there's no reason to keep older releases.

If you think that you found some public transport stop that PTSA handles incorrectly please open an issue in PTSA's GitHub repo.

## Licence

[GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0.html.en)