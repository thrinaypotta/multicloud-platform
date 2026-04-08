import sys
import os

# Make sure Python can find all project files
sys.path.insert(0, os.path.dirname(__file__))

from server import app

if __name__ == "__main__":
    app.run()