# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory, add these directories to sys.path here. If the directory is relative
# to the documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))


# -- Project information -----------------------------------------------------

project = "easy_infra"
copyright = "2022, Seiso, LLC"
author = "Jon Zeolla"

# The full version, including alpha/beta/rc tags
release = "2022.11.05"


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = ["m2r2", "sphinx_rtd_theme"]

source_suffix = [".rst", ".md"]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and directories to ignore when looking for source files. This pattern also affects
# html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for a list of builtin themes.
html_theme = "sphinx_rtd_theme"

# A dictionary of options that influence the look and feel of the selected theme. These are theme-specific. For the options understood by the builtin
# themes, see this section.
html_theme_options = {"logo_only": True, "style_nav_header_background": "#FFFFFF"}

# Add any paths that contain custom static files (such as style sheets) here, relative to this directory. They are copied after the builtin static
# files, so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# If given, this must be the name of an image file (path relative to the configuration directory) that is the logo of the docs. It is placed at the
# top of the sidebar; its width should therefore not exceed 200 pixels. Default: None.
html_logo = "_static/easy_infra_on_white.png"
