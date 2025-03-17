import os
import requests
import subprocess

# // GitHub URL of the raw version of xbox360wrapper_main.py
url = "https://raw.githubusercontent.com/PorkMaster73/x360-visual-wrapper/main/xbox360wrapper_main.py"

# // Name of the local file to replace
file_name = "xbox360wrapper_main.py"

# // Check if the file exists before downloading
if os.path.exists(file_name):
    print(f"Found existing {file_name}, preparing to update.")

# // Download the latest xbox360wrapper_main.py
try:
    print(f"Downloading the latest {file_name} from GitHub...")
    response = requests.get(url)
    response.raise_for_status()  # Check if the request was successful
    with open(file_name, "wb") as file:
        file.write(response.content)
    print(f"Successfully downloaded and replaced {file_name}.")
except requests.exceptions.RequestException as e:
    print(f"Failed to download the file: {e}")
    exit(1)

# // Run the updated xbox360wrapper_main.py
try:
    print(f"Running {file_name}...")
    subprocess.run(["python", file_name], check=True)
    print(f"Successfully ran {file_name}.")
except subprocess.CalledProcessError as e:
    print(f"Failed to run {file_name}: {e}")
