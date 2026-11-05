"""
LIGHT AI V1.0 - Main Application Entrypoint
Deterministic, rule-based voice assistant for Windows.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.assistant import LightAssistant
from utils.logger import logger


BANNER = r"""
========================================================================
   _     ___ ____ _   _ _____      _    ___   __     _____ _        
  | |   |_ _/ ___| | | |_   _|    / \  |_ _|  \ \   / /_ / |        
  | |    | | |  _| |_| | | |     / _ \  | |    \ \ / / | || |        
  | |___ | | |_| |  _  | | |    / ___ \ | |     \ V /  | || |___ _ _ 
  |_____|___\____|_| |_| |_|   /_/   \_\___|     \_/   |_(_)_____(_|_)
                                                                      
         Deterministic Rule-Based Personal Voice Assistant           
                     Revision 6 Final Implementation                  
========================================================================
"""


def main():
    print(BANNER)
    logger.info("Starting LIGHT AI V1.0...")
    try:
        assistant = LightAssistant()
        assistant.run()
    except KeyboardInterrupt:
        logger.info("LIGHT AI process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal error during execution: {e}", exc_info=True)
        sys.exit(1)

    logger.info("LIGHT AI V1.0 process completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
