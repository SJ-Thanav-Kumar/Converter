"""Exceptions raised by the converter core.

Everything inherits from ConverterError so callers (GUI, tests, future web API)
can catch one type and still tell the failure kinds apart.
"""


class ConverterError(Exception):
    """Base class for every error the converter raises on purpose."""


class InvalidInputError(ConverterError):
    """Input file is missing, not a file, unreadable, or empty."""


class UnsupportedFormatError(ConverterError):
    """Input format is unrecognised, or no backend handles this conversion."""


class OutputExistsError(ConverterError):
    """Output path already exists (and overwrite was not requested)."""


class ConversionFailedError(ConverterError):
    """A backend started the conversion but could not finish it."""


class ConversionCancelledError(ConverterError):
    """The caller cancelled the conversion."""
