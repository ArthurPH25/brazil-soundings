from datetime import datetime, timezone
import io
import os
import re
import sys

try:
  import numpy as np
  import pandas as pd
  import requests
  import rpy2.robjects as robjects
  from rpy2.robjects import pandas2ri
  from rpy2.robjects.conversion import localconverter
except Exception as importError:
  sys.exit(
      f"Could not load a required dependency: {importError}\n\n"
      "To run this script you need:\n"
      "  1. R installed and available in your PATH;\n"
      "  2. the Python dependencies: pip install -r requirements.txt\n"
      '  3. the thundeR package in R: install.packages("thunder")'
  )

STATIONS_LIST = {
    "82022": "Boa Vista - RR",
    "82026": "Tiriós - PA",
    "82099": "Macapá A/P - AP",
    "82107": "São Gabriel da Cachoeira - AM",
    "82193": "Belém - PA",
    "82244": "Santarém Airport - PA",
    "82332": "Manaus - AM",
    "82400": "Fernando de Noronha - PE",
    "82411": "Tabatinga - AM",
    "82532": "Manicoré - AM",
    "82599": "Natal - RN",
    "82705": "Cruzeiro do Sul - AC",
    "82824": "Porto Velho Airport - RO",
    "82917": "Rio Branco - AC",
    "82965": "Alta Floresta Airport - MT",
    "83208": "Vilhena Airport - RO",
    "83362": "Cuiabá Airport - MT",
    "83378": "Brasília - DF",
    "83525": "Uberlândia - MG",
    "83554": "Corumbá - MS",
    "83566": "Confins - BH/MG",
    "83612": "Campo Grande - MS",
    "83649": "Vitória - ES",
    "83746": "Galeão - RJ",
    "83768": "Londrina - PR",
    "83779": "Campo de Marte - SP",
    "83827": "Foz do Iguaçu - PR",
    "83840": "Curitiba - PR",
    "83899": "Florianópolis - SC",
    "83928": "Uruguaiana - RS",
    "83937": "Santa Maria - RS",
    "83971": "Porto Alegre - RS",
}

SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))

WRF_INPUT_DIRECTORY = os.path.join(SCRIPT_DIRECTORY, "input", "wrf")

WYOMING_OUTPUT_DIRECTORY = os.path.join(SCRIPT_DIRECTORY, "output", "wyoming")
WRF_OUTPUT_DIRECTORY = os.path.join(SCRIPT_DIRECTORY, "output", "wrf")

COORDINATE_DECIMALS = 4

EARTH_RADIUS_KM = 6371.0
GRAVITY = 9.81
KAPPA = 287.04 / 1004.5
MS_TO_KNOTS = 1.94384
MIN_MIXING_RATIO = 1e-6
GRID_INSIDE_TOLERANCE = 0.6

WRF_REQUIRED_VARIABLES = (
    "Times", "XLAT", "XLONG", "P", "PB", "T", "QVAPOR", "PH", "PHB", "U", "V",
)
WRF_SURFACE_VARIABLES = ("PSFC", "T2", "Q2", "U10", "V10", "HGT")


def escapeForR(textValue):
  return textValue.replace("\\", "\\\\").replace('"', '\\"')


def renderSounding(
    soundingDataframe, baseName, chartTitle, outputDirectory, extraInfo=""
):
  with localconverter(robjects.default_converter + pandas2ri.converter):
    convertedRDataframe = robjects.conversion.py2rpy(soundingDataframe)

  robjects.globalenv["soundingData"] = convertedRDataframe
  os.makedirs(outputDirectory, exist_ok=True)

  pngPath = os.path.join(outputDirectory, f"{baseName}.png").replace("\\", "/")
  txtPath = os.path.join(outputDirectory, f"{baseName}.txt").replace("\\", "/")

  chartTitleStringR = escapeForR(chartTitle)
  extraInfoRLine = (
      f'cat("{escapeForR(extraInfo)}\\n")' if extraInfo else ""
  )

  print("Data processed. Generating chart and text file in R...")

  rScriptThunder = f"""
    suppressMessages(suppressWarnings({{
        if (!requireNamespace("thunder", quietly = TRUE)) {{
            stop("The thunder package is not installed in R.")
        }}
        library(thunder)
    }}))

    df <- soundingData

    suppressMessages(suppressWarnings({{
        sounding_save(
            filename = "{pngPath}",
            pressure = df$pressure,
            altitude = df$altitude,
            temp = df$temp,
            dpt = df$dpt,
            wd = df$wd,
            ws = df$ws,
            max_speed = 40,
            title = "{chartTitleStringR}"
        )
    }}))

    parms <- sounding_compute(
        pressure = df$pressure,
        altitude = df$altitude,
        temp = df$temp,
        dpt = df$dpt,
        wd = df$wd,
        ws = df$ws
    )

    sink("{txtPath}")
    cat("====================================================\\n")
    cat("EXTRACTED METEOROLOGICAL PARAMETERS (thundeR)\\n")
    cat("{chartTitleStringR}\\n")
    {extraInfoRLine}
    cat("====================================================\\n\\n")
    print(t(parms))
    sink()
    """

  try:
    robjects.r(rScriptThunder)
    print(f"\nSuccess! .png generated at:\n  {pngPath}")
    print(f".txt with more data generated at:\n  {txtPath}")
    return True
  except Exception as rBridgeError:
    print(f"\nError running the R script: {rBridgeError}")
    return False


def runApiMode():
  print("\n--- MODE 1: WYOMING API ---")

  print("\nAvailable stations (Brazil, radiosonde launch sites):")
  for currentCode in sorted(STATIONS_LIST):
    print(f"  {currentCode:6s} -> {STATIONS_LIST[currentCode]}")

  while True:
    stationInput = input("\nStation number: ").strip()
    if stationInput in STATIONS_LIST:
      break
    print("Enter a valid code from the list above.")

  stationNameString = STATIONS_LIST[stationInput]

  while True:
    dateInput = input("Sounding date (YYYY-MM-DD): ").strip()
    try:
      dateObject = datetime.strptime(dateInput, "%Y-%m-%d").date()
      if dateObject > datetime.now(timezone.utc).date():
        print("The date cannot be in the future.")
      else:
        urlDateString = dateObject.strftime("%Y-%m-%d")
        break
    except ValueError:
      print("Invalid format. Use the YYYY-MM-DD pattern.")

  while True:
    timeInput = input("Sounding time (e.g. 00 or 12): ").strip()
    if timeInput.isdigit() and 0 <= int(timeInput) <= 23:
      selectedHour = int(timeInput)
      break
    print("Enter a valid hour between 0 and 23.")

  datetimeParameter = f"{urlDateString} {selectedHour:02d}:00:00"

  apiUrl = "https://weather.uwyo.edu/wsgi/sounding"
  apiParams = {
      "datetime": datetimeParameter,
      "id": stationInput,
      "type": "TEXT:CSV",
  }

  print("\nRequesting data from the Wyoming API (this can take up to a minute)...")
  try:
    apiResponse = requests.get(apiUrl, params=apiParams, timeout=90)
    apiResponse.raise_for_status()
  except Exception as apiError:
    statusCode = getattr(getattr(apiError, "response", None), "status_code", None)
    if statusCode == 400:
      print(
          f"\nNo sounding found for {stationNameString} ({stationInput}) at"
          f" {datetimeParameter} UTC."
      )
      print(
          "It may not have been published yet, or the station did not launch"
          " at that time. Try the previous day, the other main time (00 or"
          " 12) or another station."
      )
    else:
      print(f"Error making the HTTP request: {apiError}")
    return

  if (
      not apiResponse.text.strip()
      or "error" in apiResponse.text.lower()
      or "Sorry" in apiResponse.text
  ):
    print(
        "Data unavailable or error returned by the API for the given"
        " date/time."
    )
    return

  try:
    soundingDataframe = pd.read_csv(
        io.StringIO(apiResponse.text), skipinitialspace=True
    )
    soundingDataframe.columns = soundingDataframe.columns.str.strip()

    columnsMapping = {
        "pressure_hPa": "pressure",
        "geopotential height_m": "altitude",
        "temperature_C": "temp",
        "dew point temperature_C": "dpt",
        "wind direction_degree": "wd",
        "wind speed_m/s": "ws",
    }

    for originalColumn in columnsMapping.keys():
      if originalColumn not in soundingDataframe.columns:
        print(
            f"Column '{originalColumn}' was not found in the returned CSV."
        )
        return

    soundingDataframe = soundingDataframe.rename(columns=columnsMapping)
    soundingDataframe = soundingDataframe[
        ["pressure", "altitude", "temp", "dpt", "wd", "ws"]
    ].copy()
    soundingDataframe["ws"] = soundingDataframe["ws"] * MS_TO_KNOTS

    soundingDataframe = soundingDataframe.dropna().reset_index(drop=True)

    if soundingDataframe.empty:
      print("The returned file has no valid data after processing.")
      return

  except Exception as csvError:
    print(f"Error processing the CSV data: {csvError}")
    return

  cleanSearchDateString = urlDateString.replace("-", "")
  baseName = (
      f"sounding_thunder_{stationInput}_{cleanSearchDateString}_{selectedHour:02d}Z"
  )
  chartTitle = (
      f"{stationNameString} ({stationInput}) - {urlDateString}"
      f" {selectedHour:02d}Z"
  )

  renderSounding(
      soundingDataframe, baseName, chartTitle, WYOMING_OUTPUT_DIRECTORY
  )


def haversineKm(lat1, lon1, lat2, lon2):
  phi1 = np.radians(lat1)
  phi2 = np.radians(lat2)
  deltaPhi = phi2 - phi1
  deltaLambda = np.radians(lon2 - lon1)
  a = (
      np.sin(deltaPhi / 2.0) ** 2
      + np.cos(phi1) * np.cos(phi2) * np.sin(deltaLambda / 2.0) ** 2
  )
  return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def listWrfFiles():
  os.makedirs(WRF_INPUT_DIRECTORY, exist_ok=True)
  return sorted(
      fileName
      for fileName in os.listdir(WRF_INPUT_DIRECTORY)
      if fileName.lower().endswith(".nc")
      and os.path.isfile(os.path.join(WRF_INPUT_DIRECTORY, fileName))
  )


def readWrfTimes(wrfDataset):
  timesList = []
  for characterRow in wrfDataset.variables["Times"][:]:
    characters = [
        c.decode("utf-8") if isinstance(c, bytes) else str(c)
        for c in characterRow.tolist()
    ]
    timeString = "".join(characters).strip()
    timesList.append(datetime.strptime(timeString, "%Y-%m-%d_%H:%M:%S"))
  return timesList


def formatTimeLabel(timeObject):
  if timeObject.second:
    return timeObject.strftime("%H:%M:%SZ")
  if timeObject.minute:
    return timeObject.strftime("%H:%MZ")
  return timeObject.strftime("%HZ")


def formatTimeForFilename(timeObject):
  suffix = timeObject.strftime("%S") if timeObject.second else ""
  return timeObject.strftime("%H%M") + suffix + "Z"


def getGridName(wrfDataset, fileName):
  gridId = getattr(wrfDataset, "GRID_ID", None)
  if gridId is not None:
    try:
      return f"d{int(gridId):02d}"
    except (TypeError, ValueError):
      pass
  match = re.search(r"d(\d{2})", fileName, re.IGNORECASE)
  return f"d{match.group(1)}" if match else ""


def getGridSpacingKm(wrfDataset, latGrid, lonGrid):
  dxValue = getattr(wrfDataset, "DX", None)
  try:
    if dxValue is not None and float(dxValue) > 0:
      return float(dxValue) / 1000.0
  except (TypeError, ValueError):
    pass
  midJ = latGrid.shape[0] // 2
  midI = max(min(latGrid.shape[1] // 2, latGrid.shape[1] - 2), 0)
  return float(
      haversineKm(
          latGrid[midJ, midI], lonGrid[midJ, midI],
          latGrid[midJ, midI + 1], lonGrid[midJ, midI + 1],
      )
  )


def formatResolution(gridSpacingKm):
  return f"{round(gridSpacingKm, 2):g} km"


def fractionalOffsets(latGrid, lonGrid, j, i, targetLat, targetLon):
  gridRows, gridColumns = latGrid.shape
  centerLat = latGrid[j, i]
  centerLon = lonGrid[j, i]
  cosLat = np.cos(np.radians(centerLat))

  def toKm(latValue, lonValue):
    deltaLon = (lonValue - centerLon + 180.0) % 360.0 - 180.0
    return np.array([
        np.radians(deltaLon) * EARTH_RADIUS_KM * cosLat,
        np.radians(latValue - centerLat) * EARTH_RADIUS_KM,
    ])

  i0, i1 = max(i - 1, 0), min(i + 1, gridColumns - 1)
  j0, j1 = max(j - 1, 0), min(j + 1, gridRows - 1)
  stepI = (
      toKm(latGrid[j, i1], lonGrid[j, i1]) - toKm(latGrid[j, i0], lonGrid[j, i0])
  ) / (i1 - i0)
  stepJ = (
      toKm(latGrid[j1, i], lonGrid[j1, i]) - toKm(latGrid[j0, i], lonGrid[j0, i])
  ) / (j1 - j0)

  offsets = np.linalg.solve(
      np.column_stack((stepI, stepJ)), toKm(targetLat, targetLon)
  )
  return float(offsets[0]), float(offsets[1])


def locateGridPoint(wrfDataset, timeIndex, targetLat, targetLon):
  latGrid = np.asarray(wrfDataset.variables["XLAT"][timeIndex, :, :], dtype="float64")
  lonGrid = np.asarray(wrfDataset.variables["XLONG"][timeIndex, :, :], dtype="float64")

  distances = haversineKm(latGrid, lonGrid, targetLat, targetLon)
  j, i = np.unravel_index(int(np.argmin(distances)), distances.shape)
  j, i = int(j), int(i)

  offsetI, offsetJ = fractionalOffsets(latGrid, lonGrid, j, i, targetLat, targetLon)
  isInside = (
      abs(offsetI) <= GRID_INSIDE_TOLERANCE
      and abs(offsetJ) <= GRID_INSIDE_TOLERANCE
  )
  return {
      "j": j,
      "i": i,
      "lat": float(latGrid[j, i]),
      "lon": float(lonGrid[j, i]),
      "distanceKm": float(distances[j, i]),
      "isInside": isInside,
  }


def dewPointCelsius(pressureHpa, mixingRatio):
  mixingRatio = np.maximum(mixingRatio, MIN_MIXING_RATIO)
  vaporPressure = pressureHpa * mixingRatio / (0.622 + mixingRatio)
  logRatio = np.log(vaporPressure / 6.112)
  return 243.5 * logRatio / (17.67 - logRatio)


def rotateWindToEarth(uGrid, vGrid, cosAlpha, sinAlpha):
  uEarth = uGrid * cosAlpha - vGrid * sinAlpha
  vEarth = vGrid * cosAlpha + uGrid * sinAlpha
  return uEarth, vEarth


def windToDirectionSpeed(uEarth, vEarth):
  speedKnots = np.hypot(uEarth, vEarth) * MS_TO_KNOTS
  directionDegrees = (270.0 - np.degrees(np.arctan2(vEarth, uEarth))) % 360.0
  return directionDegrees, speedKnots


def buildWrfSoundingDataframe(wrfDataset, timeIndex, j, i):
  wrfVariables = wrfDataset.variables

  def column(variableName):
    return np.asarray(wrfVariables[variableName][timeIndex, :, j, i], dtype="float64")

  def scalar(variableName):
    return float(wrfVariables[variableName][timeIndex, j, i])

  pressurePa = column("P") + column("PB")
  pressureHpa = pressurePa / 100.0
  potentialTemperature = column("T") + 300.0
  temperatureK = potentialTemperature * (pressurePa / 100000.0) ** KAPPA
  temperatureC = temperatureK - 273.15
  dewPointC = dewPointCelsius(pressureHpa, column("QVAPOR"))

  geopotentialHeight = (column("PH") + column("PHB")) / GRAVITY
  altitudeM = 0.5 * (geopotentialHeight[:-1] + geopotentialHeight[1:])

  uGrid = 0.5 * (
      np.asarray(wrfVariables["U"][timeIndex, :, j, i], dtype="float64")
      + np.asarray(wrfVariables["U"][timeIndex, :, j, i + 1], dtype="float64")
  )
  vGrid = 0.5 * (
      np.asarray(wrfVariables["V"][timeIndex, :, j, i], dtype="float64")
      + np.asarray(wrfVariables["V"][timeIndex, :, j + 1, i], dtype="float64")
  )
  cosAlpha = scalar("COSALPHA") if "COSALPHA" in wrfVariables else 1.0
  sinAlpha = scalar("SINALPHA") if "SINALPHA" in wrfVariables else 0.0
  uEarth, vEarth = rotateWindToEarth(uGrid, vGrid, cosAlpha, sinAlpha)
  windDirection, windSpeedKnots = windToDirectionSpeed(uEarth, vEarth)

  pressureList = [pressureHpa]
  altitudeList = [altitudeM]
  tempList = [temperatureC]
  dewPointList = [dewPointC]
  directionList = [windDirection]
  speedList = [windSpeedKnots]

  if all(name in wrfVariables for name in WRF_SURFACE_VARIABLES):
    surfacePressureHpa = scalar("PSFC") / 100.0
    surfaceTempC = scalar("T2") - 273.15
    surfaceDewPointC = float(dewPointCelsius(surfacePressureHpa, scalar("Q2")))
    surfaceU, surfaceV = rotateWindToEarth(
        scalar("U10"), scalar("V10"), cosAlpha, sinAlpha
    )
    surfaceDirection, surfaceSpeed = windToDirectionSpeed(surfaceU, surfaceV)
    if surfacePressureHpa > pressureHpa[0]:
      pressureList.insert(0, np.array([surfacePressureHpa]))
      altitudeList.insert(0, np.array([scalar("HGT")]))
      tempList.insert(0, np.array([surfaceTempC]))
      dewPointList.insert(0, np.array([surfaceDewPointC]))
      directionList.insert(0, np.array([float(surfaceDirection)]))
      speedList.insert(0, np.array([float(surfaceSpeed)]))

  tempArray = np.concatenate(tempList)
  dewPointArray = np.minimum(np.concatenate(dewPointList), tempArray)

  soundingDataframe = pd.DataFrame({
      "pressure": np.concatenate(pressureList),
      "altitude": np.concatenate(altitudeList),
      "temp": tempArray,
      "dpt": dewPointArray,
      "wd": np.concatenate(directionList),
      "ws": np.concatenate(speedList),
  }).astype("float64")

  soundingDataframe = soundingDataframe.replace([np.inf, -np.inf], np.nan)
  return soundingDataframe.dropna().reset_index(drop=True)


def askCoordinate(promptText, minValue, maxValue):
  while True:
    rawValue = input(promptText).strip().replace(",", ".")
    try:
      numericValue = float(rawValue)
    except ValueError:
      print("Invalid value. Enter a decimal number (e.g. -23.55).")
      continue
    if minValue <= numericValue <= maxValue:
      return numericValue
    print(f"The value must be between {minValue} and {maxValue}.")


def parseTimeSelection(selectionText, timesCount):
  selectionText = selectionText.strip().lower()
  if selectionText in ("t", "all"):
    return list(range(timesCount))
  try:
    if "-" in selectionText:
      startText, endText = selectionText.split("-", 1)
      startNumber, endNumber = int(startText), int(endText)
      if 1 <= startNumber <= endNumber <= timesCount:
        return list(range(startNumber - 1, endNumber))
    else:
      singleNumber = int(selectionText)
      if 1 <= singleNumber <= timesCount:
        return [singleNumber - 1]
  except ValueError:
    pass
  return None


def askTimeSelection(timesList):
  timesCount = len(timesList)
  if timesCount == 1:
    print(
        f"\nThe file has 1 time step: {timesList[0]:%Y-%m-%d}"
        f" {formatTimeLabel(timesList[0])}"
    )
    return [0]

  print(f"\nTime steps available in the file ({timesCount}):")
  if timesCount <= 40:
    for timeNumber, timeObject in enumerate(timesList, start=1):
      print(f"  {timeNumber:3d} -> {timeObject:%Y-%m-%d} {formatTimeLabel(timeObject)}")
  else:
    for timeNumber in (1, 2, 3):
      timeObject = timesList[timeNumber - 1]
      print(f"  {timeNumber:3d} -> {timeObject:%Y-%m-%d} {formatTimeLabel(timeObject)}")
    print("  ...")
    for timeNumber in (timesCount - 2, timesCount - 1, timesCount):
      timeObject = timesList[timeNumber - 1]
      print(f"  {timeNumber:3d} -> {timeObject:%Y-%m-%d} {formatTimeLabel(timeObject)}")

  while True:
    selectionInput = input(
        f"\nTime step number (1-{timesCount}), range (e.g. 5-12) or T for all: "
    )
    selectedIndexes = parseTimeSelection(selectionInput, timesCount)
    if selectedIndexes is not None:
      return selectedIndexes
    print("Invalid selection.")


def runWrfMode():
  print("\n--- MODE 2: WRF FILE (.nc) ---")

  try:
    import netCDF4
  except ImportError:
    print(
        "The netCDF4 package is not installed. Install it with:"
        " pip install netCDF4"
    )
    return

  wrfFiles = listWrfFiles()
  if not wrfFiles:
    print(f"\nNo .nc files found in:\n  {WRF_INPUT_DIRECTORY}")
    print("Place the WRF .nc file in input/wrf/ and run the script again.")
    return

  print(f"\n.nc files found in {WRF_INPUT_DIRECTORY}:")
  for fileNumber, fileName in enumerate(wrfFiles, start=1):
    fileSizeMb = os.path.getsize(os.path.join(WRF_INPUT_DIRECTORY, fileName)) / 1e6
    print(f"  {fileNumber:3d} -> {fileName} ({fileSizeMb:.1f} MB)")

  while True:
    fileInput = input("\nFile number: ").strip()
    if fileInput.isdigit() and 1 <= int(fileInput) <= len(wrfFiles):
      selectedFileName = wrfFiles[int(fileInput) - 1]
      break
    print(f"Enter a number between 1 and {len(wrfFiles)}.")

  selectedFilePath = os.path.join(WRF_INPUT_DIRECTORY, selectedFileName)

  try:
    wrfDataset = netCDF4.Dataset(selectedFilePath, "r")
  except Exception as openError:
    print(f"Error opening the file: {openError}")
    return

  try:
    wrfDataset.set_auto_mask(False)

    missingVariables = [
        name for name in WRF_REQUIRED_VARIABLES if name not in wrfDataset.variables
    ]
    if missingVariables:
      print(
          "The file does not look like a complete wrfout. Missing variables: "
          + ", ".join(missingVariables)
      )
      return

    try:
      timesList = readWrfTimes(wrfDataset)
    except Exception as timesError:
      print(f"Error reading the file's times (Times variable): {timesError}")
      return

    if not timesList:
      print("The file has no time steps.")
      return

    firstLatGrid = np.asarray(wrfDataset.variables["XLAT"][0, :, :], dtype="float64")
    firstLonGrid = np.asarray(wrfDataset.variables["XLONG"][0, :, :], dtype="float64")

    gridName = getGridName(wrfDataset, selectedFileName)
    gridSpacingKm = getGridSpacingKm(wrfDataset, firstLatGrid, firstLonGrid)
    resolutionString = formatResolution(gridSpacingKm)
    gridLabel = " ".join(part for part in ("WRF", gridName, resolutionString) if part)

    print(f"\nGrid: {gridLabel}  ({firstLatGrid.shape[1]} x {firstLatGrid.shape[0]} points)")
    print(
        f"Approximate bounds: lat {firstLatGrid.min():.2f} to {firstLatGrid.max():.2f}"
        f" | lon {firstLonGrid.min():.2f} to {firstLonGrid.max():.2f}"
    )

    print("\nEnter the sounding coordinates (decimal degrees, south/west negative).")
    while True:
      targetLat = askCoordinate("Latitude (e.g. -23.55): ", -90.0, 90.0)
      targetLon = askCoordinate("Longitude (e.g. -46.63): ", -180.0, 180.0)
      firstLocation = locateGridPoint(wrfDataset, 0, targetLat, targetLon)
      if firstLocation["isInside"]:
        break
      print(
          "\nThese coordinates are outside the simulated area. Use values"
          " within the bounds shown above."
      )

    selectedIndexes = askTimeSelection(timesList)

    coordinateString = (
        f"{targetLat:.{COORDINATE_DECIMALS}f}, {targetLon:.{COORDINATE_DECIMALS}f}"
    )
    coordinateFileString = (
        f"{targetLat:.{COORDINATE_DECIMALS}f}_{targetLon:.{COORDINATE_DECIMALS}f}"
    )

    for sequenceNumber, timeIndex in enumerate(selectedIndexes, start=1):
      timeObject = timesList[timeIndex]
      timeLabel = formatTimeLabel(timeObject)
      print(
          f"\n[{sequenceNumber}/{len(selectedIndexes)}] "
          f"{timeObject:%Y-%m-%d} {timeLabel}"
      )

      try:
        location = locateGridPoint(wrfDataset, timeIndex, targetLat, targetLon)
        if not location["isInside"]:
          print("Coordinates outside the grid at this time step. Skipping.")
          continue

        soundingDataframe = buildWrfSoundingDataframe(
            wrfDataset, timeIndex, location["j"], location["i"]
        )
      except Exception as extractionError:
        print(f"Error extracting the sounding from WRF: {extractionError}")
        continue

      if soundingDataframe.empty:
        print("No valid data after processing. Skipping.")
        continue

      print(
          f"Grid point used: lat {location['lat']:.{COORDINATE_DECIMALS}f},"
          f" lon {location['lon']:.{COORDINATE_DECIMALS}f}"
          f" ({location['distanceKm']:.1f} km from the given point)"
      )

      chartTitle = f"{coordinateString} - {gridLabel} - {timeObject:%Y-%m-%d} {timeLabel}"
      extraInfo = (
          f"File: {selectedFileName} | grid point (i={location['i']},"
          f" j={location['j']}): {location['lat']:.{COORDINATE_DECIMALS}f},"
          f" {location['lon']:.{COORDINATE_DECIMALS}f}"
          f" ({location['distanceKm']:.1f} km from the given point)"
      )
      baseName = (
          f"sounding_thunder_WRF_{gridName or 'grid'}_{coordinateFileString}_"
          f"{timeObject:%Y%m%d}_{formatTimeForFilename(timeObject)}"
      )

      renderSounding(
          soundingDataframe, baseName, chartTitle, WRF_OUTPUT_DIRECTORY, extraInfo
      )
  finally:
    wrfDataset.close()


def askMode():
  print("\nAvailable modes:")
  print("  1 -> Observed sounding: fetch from the Wyoming API (choosing the station)")
  print("  2 -> Simulated sounding: extract from a WRF file (.nc)")
  while True:
    modeInput = input("\nChoose the mode (1 or 2): ").strip()
    if modeInput in ("1", "2"):
      return modeInput
    print("Enter 1 or 2.")


def mainRoutine():
  print("=" * 60)
  print("SOUNDING GENERATOR -> PYTHON -> THUNDER")
  print("=" * 60)

  if askMode() == "1":
    runApiMode()
  else:
    runWrfMode()


if __name__ == "__main__":
  try:
    mainRoutine()
  except KeyboardInterrupt:
    print("\nOperation cancelled by the user.")