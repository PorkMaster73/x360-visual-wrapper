import os
import requests
import subprocess

# // GitHub URL of the raw version of xbox360wrapper_main.py
url = "https://raw.githubusercontent.com/PorkMaster73/x360-visual-wrapper/main/"


def download_write_to_file(file_path: str, save_locally=True) -> str:
    # // Download the latest xbox360wrapper_main.py
    try:
        print(f"Downloading the latest {file_path} from GitHub...")
        response = requests.get(url + file_path)
        response.raise_for_status()  # // Check if the request was successful
        if (save_locally):
            with open(file_path, "wb") as file:
                file.write(response.content)
            print(f"Successfully downloaded and replaced {file_path}.")
        return str(response.content)
    except requests.exceptions.RequestException as e:
        print(f"Failed to download the file: {e}")
        exit(1)  # // Returns nothing.


includes_fname =  f"includes.txt"

includes = download_write_to_file(includes_fname, False)
includes = [x.strip() for x in includes.split("\n") if (x and "---" not in x)]
includes = [x[5:] for x in includes]  # // Gets rid of the "root/" prefix.

# // Loop through each file to be included.
for file_name in includes:
    # // Check if the file exists before downloading   
    if os.path.exists(file_name):
        print(f"Found existing {file_name}, preparing to update.")
    download_write_to_file(file_name, True)


# // Run the updated xbox360wrapper_main.py
run_file = "xbox360wrapper_main.py"
try:
    print(f"Running {run_file}...")
    subprocess.run(["python", run_file], check=True)
    print(f"Successfully ran {run_file}.")
except subprocess.CalledProcessError as e:
    print(f"Failed to run {run_file}: {e}")
