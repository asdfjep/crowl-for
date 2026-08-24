# HS News Service Configuration
# In the future, this will be stored in SQLite

# Data source settings
SOURCES = [
    "thsnews", "aerospace", "ai_news", "cls",
    "space_com", "nasa", "deepmind", "ofweek", "boe",
    # ... add all active sources here
]

# Scheduler settings
DEFAULT_INTERVAL_MINUTES = 60

# Output settings
DATA_DIR = "data/"
