#!/usr/bin/env python3
"""
Generate a file for use by BASH_ENV
"""

import sys
import json
from pathlib import Path
from logging import getLogger, basicConfig
from argparse import ArgumentParser
from yaml import safe_load, YAMLError
from jinja2 import Environment, FileSystemLoader

formatting = json.dumps(
    {
        "timestamp": "%(asctime)s",
        "namespace": "%(name)s",
        "loglevel": "%(levelname)s",
        "message": "%(message)s",
    }
)
basicConfig(level="WARNING", format=formatting)
LOG = getLogger("easy_infra")


def render(*, template_file: Path, config: dict, output_file: Path) -> None:
    """Render the functions file"""
    folder = str(template_file.parent)
    file = str(template_file.name)
    template = Environment(loader=FileSystemLoader(folder)).get_template(file)
    out = template.render(config)
    output_file.write_text(out)
    output_file.chmod(0o755)


def create_arg_parser() -> ArgumentParser:
    """Parse the arguments"""
    parser = ArgumentParser()
    parser.add_argument(
        "--config-file",
        type=lambda p: Path(p).absolute(),
        default=Path("easy_infra.yml").absolute(),
        help="specify a config file",
    )
    parser.add_argument(
        "--output",
        type=lambda p: Path(p).absolute(),
        default=Path("functions").absolute(),
        help="specify an output file",
    )
    parser.add_argument(
        "--template-file",
        type=lambda p: Path(p).absolute(),
        default=Path("functions.j2").absolute(),
        help="specify a jinja2 template",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--debug",
        action="store_const",
        dest="loglevel",
        const="DEBUG",
        help="enable debug level logging",
    )
    group.add_argument(
        "--verbose",
        action="store_const",
        dest="loglevel",
        const="INFO",
        help="enable info level logging",
    )

    return parser


def get_args_config() -> dict:
    """Get the configs passed as arguments"""
    parser = create_arg_parser()
    parsed_args = vars(parser.parse_args())
    return parsed_args


def parse_file_config(*, config_file: Path) -> dict:
    """Parse the easy_infra config file"""
    # Filter
    suffix_whitelist = {".yml", ".yaml"}

    if config_file.suffix not in suffix_whitelist:
        LOG.error("Suffix for the config file %s is not allowed", config_file)
        raise RuntimeError

    try:
        with open(config_file) as yaml_data:
            config = safe_load(yaml_data)
    except (
        YAMLError,
        FileNotFoundError,
        PermissionError,
        IsADirectoryError,
        OSError,
    ) as err:
        LOG.error(
            "The config file %s was unable to be loaded due to the following exception: %s",
            config_file,
            str(err),
        )
        # Raise if info or debug level logging
        if LOG.getEffectiveLevel() <= 20:
            raise err
        sys.exit(1)

    return config


def main():
    """Generate the functions file"""
    try:
        args = get_args_config()
        if args["loglevel"]:
            getLogger().setLevel(args["loglevel"])
    except ValueError as err:
        LOG.error("Unable to create a valid configuration")
        raise err

    config = parse_file_config(config_file=args["config_file"])
    render(
        template_file=args["template_file"], config=config, output_file=args["output"]
    )


if __name__ == "__main__":
    main()
