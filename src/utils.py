import xml.etree.ElementTree as et
import subprocess, os, sys


def xml_string_to_json(xml_str, convert_numbers=False):
    """Converts an xml string to json format (dicts and lists). Take into
    account that xml supports more data types than json, so there is no direct
    conversion!

    Parameters
    ----------
    xml_str: str
        XML string that will be converted to json format
    convert_numbers: bool
        If True, it looks for numbers formatted as trings within the fields and
        tries to convert them to int or float
    """
    el_tree = et.fromstring(xml_str)
    return xml_element_to_json(el_tree, convert_numbers)


def xml_element_to_json(element, convert_numbers=False):
    """Converts xml.etree.ElementTree.Element to json format (dicts and lists).
    Take into account that xml supports more data types than json, so there is
    no direct conversion!

    Parameters
    ----------
    element: xml.etree.ElementTree.Element
        XML element that will be converted to json format
    convert_numbers: bool
        If True, it looks for numbers formatted as trings within the fields and
        tries to convert them to int or float
    """
    # Get childs
    el_childs = list(element)

    # Define the root element
    if __is_list(el_childs):
        parent_list = True
        el_json = []
    else:
        parent_list = False
        el_json = {}

    for child in el_childs:
        if parent_list:
            el_json.append(xml_element_to_json(
                child, convert_numbers=convert_numbers))
        else:
            if len(list(child)) > 0:
                el_json[child.tag] = xml_element_to_json(
                    child, convert_numbers=convert_numbers)
            else:
                if convert_numbers:
                    el_json[child.tag] = __str_to_number(child.text)
                else:
                    el_json[child.tag] = child.text or ''
    return el_json


def __is_list(element):
    tags = []
    for el in list(element):
        tags.append(el.tag)
    return not tags or (tags.count(tags[0]) == len(tags) and len(tags) > 1)


def __str_to_number(number_str):
    """Tries to convert the string to int or float. If it is not possible, it
    returns the same string
    """
    try:
        n = int(number_str)
    except ValueError as e:
        try:
            n = float(number_str)
        except ValueError as e:
            n = number_str
    return n


def execute_shell_commands(cmds):
    # Save temporal bat file
    bat_file_name = 'temp_bat_venv.bat'
    with open(bat_file_name, 'w') as f:
        for cmd in cmds:
            f.write(cmd + '\n')
    # Execute bat file
    with subprocess.Popen('%s' % bat_file_name, shell=True,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          universal_newlines=True) as p:
        while True:
            if p.poll() is not None:
                break
            for line in p.stdout:
                if line == '\n':
                    continue
                print(line)
            for line in p.stderr:
                if line == '\n':
                    continue
                print(line, file=sys.stderr)
    # Delete bat file
    os.remove(bat_file_name)
