import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import requests

import config as config
import loco_validator.validator as loco_validator

cwd = "/tmp/ink_archive"
archive_name = "downloaded.zip"
value_folders = ['values', 'values-de', 'values-es', 'values-fr', 'values-it']

project_root = config.get_project("global", "project_root")
project_path = project_root + "/src/main/res"


def update_loco():
    loco_key = config.get_project("loco", "loco_key")
    zip_url = f"https://localise.biz/api/export/archive/xml.zip?format=android&filter=android&fallback=en&order=id&key={loco_key}"

    archive_path = download_zip(zip_url)
    if archive_path is None:
        return False

    print("String resources downloaded successfully")

    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
        zip_ref.extractall(cwd)

    os.chdir(cwd)
    files = [file for file in os.listdir('.') if file != archive_name]

    os.chdir(project_root)

    # Copy the strings.xml files from the archive to the project's values folder
    for value_folder in value_folders:
        target_file = f'{project_path}/{value_folder}/strings.xml'
        source_file = f'{cwd}/{files[0]}/res/{value_folder}/strings.xml'

        shutil.copy(source_file, target_file)

        fix_loco_header(target_file)

    print("String resources updated")

    shutil.rmtree(cwd)
    print("Deleting temporary downloaded strings resources")

    return True


def download_zip(zip_url):
    archive_path = cwd + "/" + archive_name

    response = requests.get(zip_url)

    if response.status_code != 200:
        print("Error: When trying to download translations received response.status_code =", response.status_code)
        return None

    os.makedirs(cwd, exist_ok=True)

    with open(archive_path, "wb+") as f:
        f.write(response.content)

    return archive_path


def fix_loco_header(target_file):
    walker = HeaderDiffWalker()
    walker.run(target_file)

    to_replace = "\n".join(walker.added_lines)
    replace_with = "\n".join(walker.removed_lines)
    with open(target_file, "r+") as fd:
        file_content = fd.read()
        fixed_file = file_content.replace(to_replace, replace_with)
        fd.seek(0)
        fd.write(fixed_file)


class DiffWalker:
    def walk(self, line, line_diff_type):
        pass

    def run(self, target_file):
        result = subprocess.run(f"git diff {target_file}", stdout=subprocess.PIPE, shell=True, universal_newlines=True)
        diff = result.stdout
        for line in diff.split("\n")[5:]:
            if line[0] == "-":
                returned_value = self.walk(line[1:], LineDiffType.removal)
            elif line[0] == "+":
                returned_value = self.walk(line[1:], LineDiffType.addition)
            else:
                returned_value = self.walk(None, LineDiffType.nothing)

            if returned_value == -1:
                break


class HeaderDiffWalker(DiffWalker):
    def __init__(self):
        self.removed_lines = []
        self.added_lines = []

    def walk(self, line, line_diff_type):
        if line_diff_type == LineDiffType.removal:
            self.removed_lines.append(line)
        elif line_diff_type == LineDiffType.nothing:
            return -1  # break
        else:
            has_header_ended = line.startswith("    <")
            if has_header_ended:
                return -1  # break

            self.added_lines.append(line)


class LineDiffType(Enum):
    addition = 0
    removal = 1
    nothing = 2


def validate_strings():
    error_count = 0

    for value_folder in value_folders:
        current_file = f'{project_path}/{value_folder}/strings.xml'
        tree = ET.parse(current_file)

        parts = value_folder.split("-")
        language = "en" if len(parts) < 2 else parts[-1]

        for element in tree.getroot():
            tag = element.tag
            name = element.get("name")
            value = element.text

            if tag == "string":
                error_count += loco_validator.validate_string(language, name, value)
            elif tag == "plurals":
                error_count += validate_plural(element, language, name)

    return error_count


def validate_plural(plural, language, name):
    error_count = 0

    for element in plural:
        plural_name = f"{name}-{element.get('quantity')}"
        plural_value = element.text

        error_count += loco_validator.validate_string(language, plural_name, plural_value)

    return error_count
