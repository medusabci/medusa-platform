"""This file contains the constants and default paths used through Medusa

Attributes
----------
MEDUSA_VERSION: str
    Version of Medusa following the semantic version scheme:
    MAJOR.MINOR.PATCH-tag

LSL_CONFIG_FILE: str
    Default path for the LSL config file to use on Medusa start
PLOTS_CONFIG_FILE
    Default path for the plots dashboard config file to use on Medusa start

PLOT_STATE_OFF: int
    Plot not working at the moment
PLOT_STATE_ON: int
    Plot busy plotting signals

APP_STATE_OFF: int
    Application not launched
APP_STATE_POWERING_ON: int
    Transitory state while the user presses the power button and the app is
    running
APP_STATE_POWERING_OFF: int
    Transitory state while the user press paradigm power button and the
    paradigm is off.
APP_STATE_ON: int
    Application launched state

RUN_STATE_READY: int
    APP is ON and waiting to start the running
RUN_STATE_RUNNING: int
    App running
RUN_STATE_PAUSED: int
    App paused
RUN_STATE_STOP: int
    Transitory state while user press the stop button and medusa is ready to
    start a new run again.
RUN_STATE_FINISHED: int
    The run is still active, but finished.

"""
# ============================== MEDUSA VERSION ============================== #
MEDUSA_VERSION = 'v2022.0'

# =============================== DEFAULT PATHS ============================== #
# Config files
LSL_CONFIG_FILE = 'lsl_config.json'
PLOTS_CONFIG_FILE = 'plots_config.json'
LOG_CONFIG_FILE = 'log_config.json'
APPS_CONFIG_FILE = 'apps_config.json'

# Images folder
IMG_FOLDER = 'gui/images'
STYLE_FILE = 'gui/style.css'

# ============================ CONTROL CONSTANTS ============================= #
# MEDUSA PLOT STATES
PLOT_STATE_OFF = 0
PLOT_STATE_ON = 1

# MEDUSA APP STATES
APP_STATE_OFF = 0
APP_STATE_POWERING_ON = 1
APP_STATE_POWERING_OFF = 2
APP_STATE_ON = 3

# MEDUSA RUN STATES
RUN_STATE_READY = 0
RUN_STATE_RUNNING = 1
RUN_STATE_PAUSED = 2
RUN_STATE_STOP = 3
RUN_STATE_FINISHED = 4

