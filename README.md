# brazil-soundings

Interactive terminal script that generates Skew-T diagrams and thermodynamic parameters (via [thundeR](https://github.com/bczernecki/thundeR)) from:

1. **Observed soundings**, downloaded from the University of Wyoming API (choosing station, date and time);
2. **Simulated soundings**, extracted from WRF output files (`.nc`) at a coordinate of your choice.

## Scope: Brazil

This project is dedicated to Brazil. The station list in mode 1 contains only Brazilian stations that have launched, or still launch, weather balloons (radiosondes) with some regularity. Stations from other countries are not included, and neither are Brazilian locations that never had regular launches. Some listed stations may no longer launch, so recent dates can return no data.

Mode 2 (WRF) is not tied to any country: it works with any domain present in the `.nc` file.

To add a station, include its WMO code and name in the `STATIONS_LIST` dictionary in `main.py`. The station must have data available in the University of Wyoming archive.

## Structure

```
brazil-soundings/
├── main.py                # main script
├── requirements.txt       # Python dependencies
├── README.md
├── .gitignore
├── input/
│   └── wrf/               # put your WRF .nc files here
└── output/
    ├── wyoming/           # PNG + TXT from mode 1 (API)
    └── wrf/               # PNG + TXT from mode 2 (WRF)
```

The contents of `input/` and `output/` are ignored by Git (only the `.gitkeep` files are tracked).

## Requirements

- Python 3.9+
- R installed, with the thundeR package: `install.packages("thunder")`
- Python dependencies: `pip install -r requirements.txt`

## Usage

```
python main.py
```

The script first asks which mode to use.

**Mode 1 – Wyoming API:** choose a station from the list, then enter the date (`YYYY-MM-DD`) and the time (UTC).

**Mode 2 – WRF file:**

1. Put the `.nc` file in `input/wrf/` and choose it from the list.
2. Enter latitude and longitude in decimal degrees (south and west are negative).
3. If the file has several time steps, enter the number of one of them from the list, a range of numbers (`5-12`), or `all` (or `T`) for every time step.

## WRF mode details

- Uses the grid point closest to the given coordinate (no interpolation). Coordinates outside the simulated area are rejected.
- The file must contain the standard `wrfout` variables: `Times`, `XLAT`, `XLONG`, `P`, `PB`, `T`, `QVAPOR`, `PH`, `PHB`, `U`, `V`. If `PSFC`, `T2`, `Q2`, `U10`, `V10` and `HGT` are present, the surface is added as the first point of the sounding.

## Output

Each run saves a Skew-T chart (`.png`) and a text file (`.txt`) with the parameters computed by thundeR, in `output/wyoming/` (mode 1) or `output/wrf/` (mode 2). Titles and file names follow these patterns:

- **Mode 1**
  - Chart title: `Brasília - DF (83378) - 2023-11-03 12Z`
  - File name: `sounding_thunder_83378_20231103_12Z.png`
- **Mode 2**
  - Chart title: `-23.5702, -46.6333 - WRF d02 3 km - 2023-11-03 12:15Z`
  - File name: `sounding_thunder_WRF_d02_-23.5702_-46.6333_20231103_1215Z.png`

In mode 2, the title shows the coordinates you entered (4 decimal places), the grid name and resolution read from the file, and the time as `12Z` or `12:15Z`. The `.txt` file also records which grid point was actually used and how far it is from the coordinate you entered.