from typing import Union

import requests

from .consts import METADATA_API_URI


def decode_string(bytes_or_string: Union[str, bytes]) -> str:
    """Defines data and if this bytes decode it into str"""
    if isinstance(bytes_or_string, bytes):
        bytes_or_string = bytes_or_string.decode("utf-8")
    return bytes_or_string


def get_categories_list(uri: str) -> list:
    """Get all meta categories as list"""
    categories = requests.get(uri).content
    if categories:
        return decode_string(categories).split('\n')
    return []


def get_meta_data(paths: list, category_name: str = None):
    """Get full meta data by paths to meta data categories"""
    meta_data = {}
    for path in paths:
        meta_data.update(get_category_instance(path, meta_data, category_name))
    if category_name:
        # remove last slash from category name
        meta_data = {category_name[:-1]: meta_data}
    return meta_data


def get_category_instance(
        path: str, meta_data: dict, category_name: str = None):
    """
    Get data for certain category and put it into existing meta_data
    """
    uri_with_path = "{0}{1}".format(METADATA_API_URI, path)

    if category_name:
        # cut category name from path
        category_name = path.split(category_name)[-1]
    else:
        category_name = path

    # if path ends with slash it means that this is path to nested category
    if path.endswith("/"):
        categories = get_categories_list(uri_with_path)
        # if no categories return empty string
        if not categories:
            meta_data.update({category_name: ""})
            return meta_data
        # add path to each category to get full category path
        category_paths = list(
            map(lambda category: path + category, categories)
        )
        # get meta data recursively
        meta_data.update(get_meta_data(category_paths, category_name))
    else:
        category_data = requests.get(uri_with_path).content
        meta_data.update({category_name: decode_string(category_data)})
    return meta_data
