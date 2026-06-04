# Allows type hinting of types not-yet-declared
# in Python >= 3.7
# see https://peps.python.org/pep-0563/
from __future__ import annotations

import binascii
import collections
import io
import random
import re
from collections import defaultdict
from struct import pack, unpack
from typing import BinaryIO, Union
from xml.sax.saxutils import escape

from loguru import logger
from lxml import etree

from androguard.core.resources import public

from .types import *

# Constants for ARSC Files
# see http://aospxref.com/android-13.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#233
RES_NULL_TYPE = 0x0000
RES_STRING_POOL_TYPE = 0x0001
RES_TABLE_TYPE = 0x0002
RES_XML_TYPE = 0x0003

RES_XML_FIRST_CHUNK_TYPE = 0x0100
RES_XML_START_NAMESPACE_TYPE = 0x0100
RES_XML_END_NAMESPACE_TYPE = 0x0101
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_END_ELEMENT_TYPE = 0x0103
RES_XML_CDATA_TYPE = 0x0104
RES_XML_LAST_CHUNK_TYPE = 0x017F

RES_XML_RESOURCE_MAP_TYPE = 0x0180

RES_TABLE_PACKAGE_TYPE = 0x0200
RES_TABLE_TYPE_TYPE = 0x0201
RES_TABLE_TYPE_SPEC_TYPE = 0x0202
RES_TABLE_LIBRARY_TYPE = 0x0203
RES_TABLE_OVERLAYABLE_TYPE = 0x0204
RES_TABLE_OVERLAYABLE_POLICY_TYPE = 0x0205
RES_TABLE_STAGED_ALIAS_TYPE = 0x0206
# Flags in the STRING Section
SORTED_FLAG = 1 << 0
UTF8_FLAG = 1 << 8

# Position of the fields inside an attribute
ATTRIBUTE_IX_NAMESPACE_URI = 0
ATTRIBUTE_IX_NAME = 1
ATTRIBUTE_IX_VALUE_STRING = 2
ATTRIBUTE_IX_VALUE_TYPE = 3
ATTRIBUTE_IX_VALUE_DATA = 4
ATTRIBUTE_LENGTH = 5

# Internally used state variables for AXMLParser
START_DOCUMENT = 0
END_DOCUMENT = 1
START_TAG = 2
END_TAG = 3
TEXT = 4

# Table used to lookup functions to determine the value representation in ARSCParser
TYPE_TABLE = {
    TYPE_ATTRIBUTE: "attribute",
    TYPE_DIMENSION: "dimension",
    TYPE_FLOAT: "float",
    TYPE_FRACTION: "fraction",
    TYPE_INT_BOOLEAN: "int_boolean",
    TYPE_INT_COLOR_ARGB4: "int_color_argb4",
    TYPE_INT_COLOR_ARGB8: "int_color_argb8",
    TYPE_INT_COLOR_RGB4: "int_color_rgb4",
    TYPE_INT_COLOR_RGB8: "int_color_rgb8",
    TYPE_INT_DEC: "int_dec",
    TYPE_INT_HEX: "int_hex",
    TYPE_NULL: "null",
    TYPE_REFERENCE: "reference",
    TYPE_STRING: "string",
}

RADIX_MULTS = [0.00390625, 3.051758e-005, 1.192093e-007, 4.656613e-010]
DIMENSION_UNITS = ["px", "dip", "sp", "pt", "in", "mm"]
FRACTION_UNITS = ["%", "%p"]

COMPLEX_UNIT_MASK = 0x0F


class ResParserError(Exception):
    """Exception for the parsers"""

    pass


def complexToFloat(xcomplex) -> float:
    """
    Convert a complex unit into float
    """
    return float(xcomplex & 0xFFFFFF00) * RADIX_MULTS[(xcomplex >> 4) & 3]


class StringBlock:
    """
    StringBlock is a CHUNK inside an AXML File: `ResStringPool_header`
    It contains all strings, which are used by referencing to ID's

    See http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#436
    """

    def __init__(self, buff: BinaryIO, header: ARSCHeader) -> None:
        """
        :param buff: buffer which holds the string block
        :param header: a instance of [ARSCHeader][androguard.core.axml.ARSCHeader]
        """
        self._cache = {}
        self.header = header
        # We already read the header (which was chunk_type and chunk_size
        # Now, we read the string_count:
        self.stringCount = unpack('<I', buff.read(4))[0]
        # style_count
        self.styleCount = unpack('<I', buff.read(4))[0]

        # flags
        self.flags = unpack('<I', buff.read(4))[0]
        self.m_isUTF8 = (self.flags & UTF8_FLAG) != 0

        # string_pool_offset
        # The string offset is counted from the beginning of the string section
        self.stringsOffset = unpack('<I', buff.read(4))[0]
        # check if the stringCount is correct
        if (
            self.stringsOffset - (self.styleCount * 4 + 28)
        ) / 4 != self.stringCount:
            self.stringCount = int(
                (self.stringsOffset - (self.styleCount * 4 + 28)) / 4
            )

        # style_pool_offset
        # The styles offset is counted as well from the beginning of the string section
        self.stylesOffset = unpack('<I', buff.read(4))[0]

        # Check if they supplied a stylesOffset even if the count is 0:
        if self.styleCount == 0 and self.stylesOffset > 0:
            logger.info(
                "Styles Offset given, but styleCount is zero. "
                "This is not a problem but could indicate packers."
            )

        self.m_stringOffsets = []
        self.m_styleOffsets = []
        self.m_charbuff = ""
        self.m_styles = []

        # Next, there is a list of string following.
        # This is only a list of offsets (4 byte each)
        for i in range(self.stringCount):
            self.m_stringOffsets.append(unpack('<I', buff.read(4))[0])

        # And a list of styles
        # again, a list of offsets
        for i in range(self.styleCount):
            self.m_styleOffsets.append(unpack('<I', buff.read(4))[0])

        # FIXME it is probably better to parse n strings and not calculate the size
        size = self.header.size - self.stringsOffset

        # if there are styles as well, we do not want to read them too.
        # Only read them, if no
        if self.stylesOffset != 0 and self.styleCount != 0:
            size = self.stylesOffset - self.stringsOffset

        if (size % 4) != 0:
            logger.warning("Size of strings is not aligned by four bytes.")

        self.m_charbuff = buff.read(size)

        if self.stylesOffset != 0 and self.styleCount != 0:
            size = self.header.size - self.stylesOffset

            if (size % 4) != 0:
                logger.warning("Size of styles is not aligned by four bytes.")

            for i in range(0, size // 4):
                self.m_styles.append(unpack('<I', buff.read(4))[0])

    def __repr__(self):
        return "<StringPool #strings={}, #styles={}, UTF8={}>".format(
            self.stringCount, self.styleCount, self.m_isUTF8
        )

    def __getitem__(self, idx):
        """
        Returns the string at the index in the string table

        :returns: the string
        """
        return self.getString(idx)

    def __len__(self):
        """
        Get the number of strings stored in this table

        :return: the number of strings
        """
        return self.stringCount

    def __iter__(self):
        """
        Iterable over all strings

        :returns: a generator over all strings
        """
        for i in range(self.stringCount):
            yield self.getString(i)

    def getString(self, idx: int) -> str:
        """
        Return the string at the index in the string table

        :param idx: index in the string table
        :return: the string
        """
        if idx in self._cache:
            return self._cache[idx]

        if idx < 0 or not self.m_stringOffsets or idx >= self.stringCount:
            return ""

        offset = self.m_stringOffsets[idx]

        if self.m_isUTF8:
            self._cache[idx] = self._decode8(offset)
        else:
            self._cache[idx] = self._decode16(offset)

        return self._cache[idx]

    def getStyle(self, idx: int) -> int:
        """
        Return the style associated with the index

        :param idx: index of the style
        :return: the style integer
        """
        return self.m_styles[idx]

    def _decode8(self, offset: int) -> str:
        """
        Decode an UTF-8 String at the given offset

        :param offset: offset of the string inside the data
        :raises ResParserError: if string is not null terminated
        :return: the decoded string
        """
        # UTF-8 Strings contain two lengths, as they might differ:
        # 1) the UTF-16 length
        str_len, skip = self._decode_length(offset, 1)
        offset += skip

        # 2) the utf-8 string length
        encoded_bytes, skip = self._decode_length(offset, 1)
        offset += skip

        # Two checks should happen here:
        # a) offset + encoded_bytes surpassing the string_pool length and
        # b) non-null terminated strings which should be rejected
        # platform/frameworks/base/libs/androidfw/ResourceTypes.cpp#789
        if len(self.m_charbuff) < (offset + encoded_bytes):
            logger.warning(
                f"String size: {offset + encoded_bytes} is exceeding string pool size. Returning empty string."
            )
            return ""
        data = self.m_charbuff[offset : offset + encoded_bytes]

        if self.m_charbuff[offset + encoded_bytes] != 0:
            logger.warning(
                "UTF-8 String is not null terminated! At offset={}".format(offset)
            )
            return ""

        return self._decode_bytes(data, 'utf-8', str_len)

    def _decode16(self, offset: int) -> str:
        """
        Decode an UTF-16 String at the given offset

        :param offset: offset of the string inside the data
        :raises ResParserError: if string is not null terminated

        :return: the decoded string
        """
        str_len, skip = self._decode_length(offset, 2)
        offset += skip

        # The len is the string len in utf-16 units
        encoded_bytes = str_len * 2

        # Two checks should happen here:
        # a) offset + encoded_bytes surpassing the string_pool length and
        # b) non-null terminated strings which should be rejected
        # platform/frameworks/base/libs/androidfw/ResourceTypes.cpp#789
        if len(self.m_charbuff) < (offset + encoded_bytes):
            logger.warning(
                f"String size: {offset + encoded_bytes} is exceeding string pool size. Returning empty string."
            )
            return ""

        data = self.m_charbuff[offset : offset + encoded_bytes]

        if (
            self.m_charbuff[
                offset + encoded_bytes : offset + encoded_bytes + 2
            ]
            != b"\x00\x00"
        ):
            raise ResParserError(
                "UTF-16 String is not null terminated! At offset={}".format(
                    offset
                )
            )

        return self._decode_bytes(data, 'utf-16', str_len)

    @staticmethod
    def _decode_bytes(data: bytes, encoding: str, str_len: int) -> str:
        """
        Generic decoding with length check.
        The string is decoded from bytes with the given encoding, then the length
        of the string is checked.
        The string is decoded using the "replace" method.

        :param data: bytes
        :param encoding: encoding name ("utf-8" or "utf-16")
        :param str_len: length of the decoded string
        :return: the decoded bytes
        """
        string = data.decode(encoding, 'replace')
        if len(string) != str_len:
            logger.warning("invalid decoded string length")
        return string

    def _decode_length(self, offset: int, sizeof_char: int) -> tuple[int, int]:
        """
        Generic Length Decoding at offset of string

        The method works for both 8 and 16 bit Strings.
        Length checks are enforced:
        * 8 bit strings: maximum of 0x7FFF bytes (See
        http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/ResourceTypes.cpp#692)
        * 16 bit strings: maximum of 0x7FFFFFF bytes (See
        http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/ResourceTypes.cpp#670)

        :param offset: offset into the string data section of the beginning of
        the string
        :param sizeof_char: number of bytes per char (1 = 8bit, 2 = 16bit)
        :returns: tuple of (length, read bytes)
        """
        sizeof_2chars = sizeof_char << 1
        fmt = "<2{}".format('B' if sizeof_char == 1 else 'H')
        highbit = 0x80 << (8 * (sizeof_char - 1))

        length1, length2 = unpack(
            fmt, self.m_charbuff[offset : (offset + sizeof_2chars)]
        )

        if (length1 & highbit) != 0:
            length = ((length1 & ~highbit) << (8 * sizeof_char)) | length2
            size = sizeof_2chars
        else:
            length = length1
            size = sizeof_char

        # These are true asserts, as the size should never be less than the values
        if sizeof_char == 1:
            assert (
                length <= 0x7FFF
            ), "length of UTF-8 string is too large! At offset={}".format(
                offset
            )
        else:
            assert (
                length <= 0x7FFFFFFF
            ), "length of UTF-16 string is too large!  At offset={}".format(
                offset
            )

        return length, size

    def show(self) -> None:
        """
        Print some information on stdout about the string table
        """
        print(
            "StringBlock(stringsCount=0x%x, "
            "stringsOffset=0x%x, "
            "stylesCount=0x%x, "
            "stylesOffset=0x%x, "
            "flags=0x%x"
            ")"
            % (
                self.stringCount,
                self.stringsOffset,
                self.styleCount,
                self.stylesOffset,
                self.flags,
            )
        )

        if self.stringCount > 0:
            print()
            print("String Table: ")
            for i, s in enumerate(self):
                print("{:08d} {}".format(i, repr(s)))

        if self.styleCount > 0:
            print()
            print("Styles Table: ")
            for i in range(self.styleCount):
                print("{:08d} {}".format(i, repr(self.getStyle(i))))


class AXMLParser:
    """
    `AXMLParser` reads through all chunks in the AXML file
    and implements a state machine to return information about
    the current chunk, which can then be read by [AXMLPrinter][androguard.core.axml.AXMLPrinter].

    An AXML file is a file which contains multiple chunks of data, defined
    by the `ResChunk_header`.
    There is no real file magic but as the size of the first header is fixed
    and the `type` of the `ResChunk_header` is set to `RES_XML_TYPE`, a file
    will usually start with `0x03000800`.
    But there are several examples where the `type` is set to something
    else, probably in order to fool parsers.

    Typically the `AXMLParser` is used in a loop which terminates if `m_event` is set to `END_DOCUMENT`.
    You can use the `next()` function to get the next chunk.
    Note that not all chunk types are yielded from the iterator! Some chunks are processed in
    the `AXMLParser` only.
    The parser will set [is_valid][androguard.core.axml.AXMLParser.is_valid] to `False` if it parses something not valid.
    Messages what is wrong are logged.

    See http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#563
    """

    def __init__(self, raw_buff: bytes) -> None:
        logger.debug("AXMLParser")

        self._reset()

        self._valid = True
        self.axml_tampered = False
        self.buff = io.BufferedReader(io.BytesIO(raw_buff))
        self.buff_size = self.buff.raw.getbuffer().nbytes
        self.packerwarning = False

        # Minimum is a single ARSCHeader, which would be a strange edge case...
        if self.buff_size < 8:
            logger.error(
                "Filesize is too small to be a valid AXML file! Filesize: {}".format(
                    self.buff_size
                )
            )
            self._valid = False
            return

        # This would be even stranger, if an AXML file is larger than 4GB...
        # But this is not possible as the maximum chunk size is a unsigned 4 byte int.
        if self.buff_size > 0xFFFFFFFF:
            logger.error(
                "Filesize is too large to be a valid AXML file! Filesize: {}".format(
                    self.buff_size
                )
            )
            self._valid = False
            return

        try:
            axml_header = ARSCHeader(self.buff)
            logger.debug("FIRST HEADER {}".format(axml_header))
        except ResParserError as e:
            logger.error("Error parsing first resource header: %s", e)
            self._valid = False
            return

        self.filesize = axml_header.size

        if axml_header.header_size == 28024:
            # Can be a common error: the file is not an AXML but a plain XML
            # The file will then usually start with '<?xm' / '3C 3F 78 6D'
            logger.warning(
                "Header size is 28024! Are you trying to parse a plain XML file?"
            )

        if axml_header.header_size != 8:
            logger.error(
                "This does not look like an AXML file. header size does not equal 8! header size = {}".format(
                    axml_header.header_size
                )
            )
            self._valid = False
            return

        if self.filesize > self.buff_size:
            logger.error(
                "This does not look like an AXML file. Declared filesize does not match real size: {} vs {}".format(
                    self.filesize, self.buff_size
                )
            )
            self._valid = False
            return

        if self.filesize < self.buff_size:
            # The file can still be parsed up to the point where the chunk should end.
            self.axml_tampered = True
            logger.warning(
                "Declared filesize ({}) is smaller than total file size ({}). "
                "Was something appended to the file? Trying to parse it anyways.".format(
                    self.filesize, self.buff_size
                )
            )

        # Not that severe of an error, we have plenty files where this is not
        # set correctly
        if axml_header.type != RES_XML_TYPE:
            self.axml_tampered = True
            logger.warning(
                "AXML file has an unusual resource type! "
                "Malware likes to to such stuff to anti androguard! "
                "But we try to parse it anyways. Resource Type: 0x{:04x}".format(
                    axml_header.type
                )
            )

        # Now we parse the STRING POOL
        try:
            header = ARSCHeader(self.buff, expected_type=RES_STRING_POOL_TYPE)
            logger.debug("STRING_POOL {}".format(header))
        except ResParserError as e:
            logger.error(
                "Error parsing resource header of string pool: {}".format(e)
            )
            self._valid = False
            return

        if header.header_size != 0x1C:
            logger.error(
                "This does not look like an AXML file. String chunk header size does not equal 28! header size = {}".format(
                    header.header_size
                )
            )
            self._valid = False
            return

        self.sb = StringBlock(self.buff, header)

        self.buff.seek(axml_header.header_size + header.size)

        # Stores resource ID mappings, if any
        self.m_resourceIDs = []

        # Store a list of prefix/uri mappings encountered
        self.namespaces = []

    def is_valid(self) -> bool:
        """
        Get the state of the [AXMLPrinter][androguard.core.axml.AXMLPrinter].
        if an error happend somewhere in the process of parsing the file,
        this flag is set to `False`.

        :returns: `True` if the `AXMLPrinter` finished parsing, or `False` if an error occurred
        """
        pass


    def __next__(self):
        self._do_next()
        return self.m_event


    @property
    def name(self) -> str:
        """
        Return the String associated with the tag name

        :returns: the string
        """
        pass

    @property
    def comment(self) -> Union[str, None]:
        """
        Return the comment at the current position or None if no comment is given

        This works only for Tags, as the comments of Namespaces are silently dropped.
        Currently, there is no way of retrieving comments of namespaces.

        :returns: the comment string, or None if no comment exists
        """
        pass

    @property
    def namespace(self) -> str:
        """
        Return the Namespace URI (if any) as a String for the current tag

        :returns: the namespace uri, or empty if namespace does not exist
        """
        pass

    @property
    def nsmap(self) -> dict[str, str]:
        """
        Returns the current namespace mapping as a dictionary

        there are several problems with the map and we try to guess a few
        things here:

        1) a URI can be mapped by many prefixes, so it is to decide which one to take
        2) a prefix might map to an empty string (some packers)
        3) uri+prefix mappings might be included several times
        4) prefix might be empty

        :returns: the namespace mapping dictionary
        """
        pass

    @property
    def text(self) -> str:
        """
        Return the String assosicated with the current text

        :returns: the string associated with the current text
        """
        pass

    def getName(self) -> str:
        """
        Legacy only!
        use `name` attribute instead
        """
        pass

    def getText(self) -> str:
        """
        Legacy only!
        use `text` attribute instead
        """
        pass

    def getPrefix(self) -> str:
        """
        Legacy only!
        use `namespace` attribute instead
        """
        pass

    def _get_attribute_offset(self, index: int):
        """
        Return the start inside the m_attributes array for a given attribute
        """
        pass

    def getAttributeCount(self) -> int:
        """
        Return the number of Attributes for a Tag
        or -1 if not in a tag

        :returns: the number of attributes
        """
        pass

    def getAttributeUri(self, index:int) -> int:
        """
        Returns the numeric ID for the namespace URI of an attribute

        :returns: the namespace URI numeric id
        """
        pass

    def getAttributeNamespace(self, index:int) -> str:
        """
        Return the Namespace URI (if any) for the attribute

        :returns: the attribute uri, or empty string if no namespace
        """
        pass

    def getAttributeName(self, index:int) -> str:
        """
        Returns the String which represents the attribute name

        :returns: the attribute name
        """
        pass

    def getAttributeValueType(self, index: int):
        """
        Return the type of the attribute at the given index

        :param index: index of the attribute
        """
        pass

    def getAttributeValueData(self, index: int):
        """
        Return the data of the attribute at the given index

        :param index: index of the attribute
        """
        pass

    def getAttributeValue(self, index: int) -> str:
        """
        This function is only used to look up strings
        All other work is done by
        [format_value][androguard.core.axml.format_value]
        # FIXME should unite those functions
        :param index: index of the attribute
        :returns: the string
        """
        pass


def format_value(
    _type: int, _data: int, lookup_string=lambda ix: "<string>"
) -> str:
    """
    Format a value based on type and data.
    By default, no strings are looked up and `"<string>"` is returned.
    You need to define `lookup_string` in order to actually lookup strings from
    the string table.

    :param _type: The numeric type of the value
    :param _data: The numeric data of the value
    :param lookup_string: A function how to resolve strings from integer IDs
    :returns: the formatted string
    """

    # Function to prepend android prefix for attributes/references from the
    # android library
    fmt_package = lambda x: "android:" if x >> 24 == 1 else ""

    # Function to represent integers
    fmt_int = lambda x: (0x7FFFFFFF & x) - 0x80000000 if x > 0x7FFFFFFF else x

    if _type == TYPE_STRING:
        return lookup_string(_data)

    elif _type == TYPE_ATTRIBUTE:
        return "?{}{:08X}".format(fmt_package(_data), _data)

    elif _type == TYPE_REFERENCE:
        return "@{}{:08X}".format(fmt_package(_data), _data)

    elif _type == TYPE_FLOAT:
        return "%f" % unpack("=f", pack("=L", _data))[0]

    elif _type == TYPE_INT_HEX:
        return "0x%08X" % _data

    elif _type == TYPE_INT_BOOLEAN:
        if _data == 0:
            return "false"
        return "true"

    elif _type == TYPE_DIMENSION:
        return "{:f}{}".format(
            complexToFloat(_data), DIMENSION_UNITS[_data & COMPLEX_UNIT_MASK]
        )

    elif _type == TYPE_FRACTION:
        return "{:f}{}".format(
            complexToFloat(_data) * 100,
            FRACTION_UNITS[_data & COMPLEX_UNIT_MASK],
        )

    elif TYPE_FIRST_COLOR_INT <= _type <= TYPE_LAST_COLOR_INT:
        return "#%08X" % _data

    elif TYPE_FIRST_INT <= _type <= TYPE_LAST_INT:
        return "%d" % fmt_int(_data)

    return "<0x{:X}, type 0x{:02X}>".format(_data, _type)


class AXMLPrinter:
    """
    Converter for AXML Files into a lxml ElementTree, which can easily be
    converted into XML.

    A Reference Implementation can be found at http://androidxref.com/9.0.0_r3/xref/frameworks/base/tools/aapt/XMLNode.cpp
    """

    __charrange = None
    __replacement = None

    def __init__(self, raw_buff: bytes) -> bytes:
        logger.debug("AXMLPrinter")

        self.axml = AXMLParser(raw_buff)

        self.root = None
        self.packerwarning = False
        cur = []

        while self.axml.is_valid():
            _type = next(self.axml)
            logger.debug("DEBUG ARSC TYPE {}".format(_type))

            if _type == START_TAG:
                if not self.axml.name:  # Check if the name is empty
                    logger.debug("Empty tag name, skipping to next element")
                    continue  # Skip this iteration
                uri = self._print_namespace(self.axml.namespace)
                uri, name = self._fix_name(uri, self.axml.name)
                tag = "{}{}".format(uri, name)

                comment = self.axml.comment
                if comment:
                    if self.root is None:
                        logger.warning(
                            "Can not attach comment with content '{}' without root!".format(
                                comment
                            )
                        )
                    else:
                        cur[-1].append(etree.Comment(comment))

                logger.debug(
                    "START_TAG: {} (line={})".format(
                        tag, self.axml.m_lineNumber
                    )
                )

                try:
                    elem = etree.Element(tag, nsmap=self.axml.nsmap)
                except ValueError as e:
                    logger.error(e)
                    # nsmap= {'<!--': 'http://schemas.android.com/apk/res/android'} | pull/1056
                    if 'Invalid namespace prefix' in str(e):
                        corrected_nsmap = self.clean_and_replace_nsmap(
                            self.axml.nsmap, str(e).split("'")[1]
                        )
                        elem = etree.Element(tag, nsmap=corrected_nsmap)
                    else:
                        raise

                for i in range(self.axml.getAttributeCount()):
                    uri = self._print_namespace(
                        self.axml.getAttributeNamespace(i)
                    )
                    uri, name = self._fix_name(
                        uri, self.axml.getAttributeName(i)
                    )
                    value = self._fix_value(self._get_attribute_value(i))

                    logger.debug(
                        "found an attribute: {}{}='{}'".format(
                            uri, name, value.encode("utf-8")
                        )
                    )
                    if "{}{}".format(uri, name) in elem.attrib:
                        logger.warning(
                            "Duplicate attribute '{}{}'! Will overwrite!".format(
                                uri, name
                            )
                        )
                    elem.set("{}{}".format(uri, name), value)

                if self.root is None:
                    self.root = elem
                else:
                    if not cur:
                        # looks like we lost the root?
                        logger.error(
                            "No more elements available to attach to! Is the XML malformed?"
                        )
                        break
                    cur[-1].append(elem)
                cur.append(elem)

            if _type == END_TAG:
                if not cur:
                    logger.warning(
                        "Too many END_TAG! No more elements available to attach to!"
                    )
                else:
                    if not self.axml.name:  # Check if the name is empty
                        logger.debug(
                            "Empty tag name at END_TAG, skipping to next element"
                        )
                        continue

                name = self.axml.name
                uri = self._print_namespace(self.axml.namespace)
                tag = "{}{}".format(uri, name)
                if cur[-1].tag != tag:
                    logger.warning(
                        "Closing tag '{}' does not match current stack! At line number: {}. Is the XML malformed?".format(
                            self.axml.name, self.axml.m_lineNumber
                        )
                    )
                cur.pop()
            if _type == TEXT:
                logger.debug("TEXT for {}".format(cur[-1]))
                cur[-1].text = self.axml.text
            if _type == END_DOCUMENT:
                # Check if all namespace mappings are closed
                if len(self.axml.namespaces) > 0:
                    logger.warning(
                        "Not all namespace mappings were closed! Malformed AXML?"
                    )
                break


    def get_buff(self) -> bytes:
        """
        Returns the raw XML file without prettification applied.

        :returns: bytes, encoded as UTF-8
        """
        pass

    def get_xml(self, pretty: bool = True) -> bytes:
        """
        Get the XML as an UTF-8 string

        :returns: bytes encoded as UTF-8
        """
        pass

    def get_xml_obj(self) -> etree.Element:
        """
        Get the XML as an ElementTree object

        :returns: `lxml.etree.Element` object
        """
        return self.root

    def is_valid(self) -> bool:
        """
        Return the state of the [AXMLParser][androguard.core.axml.AXMLParser].
        If this flag is set to `False`, the parsing has failed, thus
        the resulting XML will not work or will even be empty.

        :returns: `True` if the `AXMLParser` finished parsing, or `False` if an error occurred
        """
        pass

    def is_packed(self) -> bool:
        """
        Returns True if the AXML is likely to be packed

        Packers do some weird stuff and we try to detect it.
        Sometimes the files are not packed but simply broken or compiled with
        some broken version of a tool.
        Some file corruption might also be appear to be a packed file.

        :returns: True if packer detected, False otherwise
        """
        pass

    def _get_attribute_value(self, index: int):
        """
        Wrapper function for format_value to resolve the actual value of an attribute in a tag
        :param index: index of the current attribute
        :return: formatted value
        """
        pass

    def _fix_name(self, prefix, name) -> tuple[str, str]:
        """
        Apply some fixes to element named and attribute names.
        Try to get conform to:
        > Like element names, attribute names are case-sensitive and must start with a letter or underscore.
        > The rest of the name can contain letters, digits, hyphens, underscores, and periods.
        See: <https://msdn.microsoft.com/en-us/library/ms256152(v=vs.110).aspx>

        This function tries to fix some broken namespace mappings.
        In some cases, the namespace prefix is inside the name and not in the prefix field.
        Then, the tag name will usually look like 'android:foobar'.
        If and only if the namespace prefix is inside the namespace mapping and the actual prefix field is empty,
        we will strip the prefix from the attribute name and return the fixed prefix URI instead.
        Otherwise replacement rules will be applied.

        The replacement rules work in that way, that all unwanted characters are replaced by underscores.
        In other words, all characters except the ones listed above are replaced.

        :param name: Name of the attribute or tag
        :param prefix: The existing prefix uri as found in the AXML chunk
        :return: a fixed version of prefix and name
        """
        pass

    def _fix_value(self, value):
        """
        Return a cleaned version of a value
        according to the specification:
        > Char	   ::=   	#x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]

        See <https://www.w3.org/TR/xml/#charsets>

        :param value: a value to clean
        :return: the cleaned value
        """
        pass



# See http://aospxref.com/android-13.0.0_r3/xref/frameworks/native/include/android/configuration.h#56

ACONFIGURATION_ORIENTATION_ANY = 0x0000
ACONFIGURATION_ORIENTATION_PORT = 0x0001
ACONFIGURATION_ORIENTATION_LAND = 0x0002
ACONFIGURATION_ORIENTATION_SQUARE = 0x0003
ACONFIGURATION_TOUCHSCREEN_ANY = 0x0000
ACONFIGURATION_TOUCHSCREEN_NOTOUCH = 0x0001
ACONFIGURATION_TOUCHSCREEN_STYLUS = 0x0002
ACONFIGURATION_TOUCHSCREEN_FINGER = 0x0003
ACONFIGURATION_DENSITY_DEFAULT = 0
ACONFIGURATION_DENSITY_LOW = 120
ACONFIGURATION_DENSITY_MEDIUM = 160
ACONFIGURATION_DENSITY_TV = 213
ACONFIGURATION_DENSITY_HIGH = 240
ACONFIGURATION_DENSITY_XHIGH = 320
ACONFIGURATION_DENSITY_XXHIGH = 480
ACONFIGURATION_DENSITY_XXXHIGH = 640
ACONFIGURATION_DENSITY_ANY = 0xFFFE
ACONFIGURATION_DENSITY_NONE = 0xFFFF
ACONFIGURATION_KEYBOARD_ANY = 0x0000
ACONFIGURATION_KEYBOARD_NOKEYS = 0x0001
ACONFIGURATION_KEYBOARD_QWERTY = 0x0002
ACONFIGURATION_KEYBOARD_12KEY = 0x0003
ACONFIGURATION_NAVIGATION_ANY = 0x0000
ACONFIGURATION_NAVIGATION_NONAV = 0x0001
ACONFIGURATION_NAVIGATION_DPAD = 0x0002
ACONFIGURATION_NAVIGATION_TRACKBALL = 0x0003
ACONFIGURATION_NAVIGATION_WHEEL = 0x0004
ACONFIGURATION_KEYSHIDDEN_ANY = 0x0000
ACONFIGURATION_KEYSHIDDEN_NO = 0x0001
ACONFIGURATION_KEYSHIDDEN_YES = 0x0002
ACONFIGURATION_KEYSHIDDEN_SOFT = 0x0003
ACONFIGURATION_NAVHIDDEN_ANY = 0x0000
ACONFIGURATION_NAVHIDDEN_NO = 0x0001
ACONFIGURATION_NAVHIDDEN_YES = 0x0002
ACONFIGURATION_SCREENSIZE_ANY = 0x00
ACONFIGURATION_SCREENSIZE_SMALL = 0x01
ACONFIGURATION_SCREENSIZE_NORMAL = 0x02
ACONFIGURATION_SCREENSIZE_LARGE = 0x03
ACONFIGURATION_SCREENSIZE_XLARGE = 0x04
ACONFIGURATION_SCREENLONG_ANY = 0x00
ACONFIGURATION_SCREENLONG_NO = 0x1
ACONFIGURATION_SCREENLONG_YES = 0x2
ACONFIGURATION_SCREENROUND_ANY = 0x00
ACONFIGURATION_SCREENROUND_NO = 0x1
ACONFIGURATION_SCREENROUND_YES = 0x2
ACONFIGURATION_WIDE_COLOR_GAMUT_ANY = 0x00
ACONFIGURATION_WIDE_COLOR_GAMUT_NO = 0x1
ACONFIGURATION_WIDE_COLOR_GAMUT_YES = 0x2
ACONFIGURATION_HDR_ANY = 0x00
ACONFIGURATION_HDR_NO = 0x1
ACONFIGURATION_HDR_YES = 0x2
ACONFIGURATION_UI_MODE_TYPE_ANY = 0x00
ACONFIGURATION_UI_MODE_TYPE_NORMAL = 0x01
ACONFIGURATION_UI_MODE_TYPE_DESK = 0x02
ACONFIGURATION_UI_MODE_TYPE_CAR = 0x03
ACONFIGURATION_UI_MODE_TYPE_TELEVISION = 0x04
ACONFIGURATION_UI_MODE_TYPE_APPLIANCE = 0x05
ACONFIGURATION_UI_MODE_TYPE_WATCH = 0x06
ACONFIGURATION_UI_MODE_TYPE_VR_HEADSET = 0x07
ACONFIGURATION_UI_MODE_NIGHT_ANY = 0x00
ACONFIGURATION_UI_MODE_NIGHT_NO = 0x1
ACONFIGURATION_UI_MODE_NIGHT_YES = 0x2
ACONFIGURATION_SCREEN_WIDTH_DP_ANY = 0x0000
ACONFIGURATION_SCREEN_HEIGHT_DP_ANY = 0x0000
ACONFIGURATION_SMALLEST_SCREEN_WIDTH_DP_ANY = 0x0000
ACONFIGURATION_LAYOUTDIR_ANY = 0x00
ACONFIGURATION_LAYOUTDIR_LTR = 0x01
ACONFIGURATION_LAYOUTDIR_RTL = 0x02
ACONFIGURATION_MCC = 0x0001
ACONFIGURATION_MNC = 0x0002
ACONFIGURATION_LOCALE = 0x0004
ACONFIGURATION_TOUCHSCREEN = 0x0008
ACONFIGURATION_KEYBOARD = 0x0010
ACONFIGURATION_KEYBOARD_HIDDEN = 0x0020
ACONFIGURATION_NAVIGATION = 0x0040
ACONFIGURATION_ORIENTATION = 0x0080
ACONFIGURATION_DENSITY = 0x0100
ACONFIGURATION_SCREEN_SIZE = 0x0200
ACONFIGURATION_VERSION = 0x0400
ACONFIGURATION_SCREEN_LAYOUT = 0x0800
ACONFIGURATION_UI_MODE = 0x1000
ACONFIGURATION_SMALLEST_SCREEN_SIZE = 0x2000
ACONFIGURATION_LAYOUTDIR = 0x4000
ACONFIGURATION_SCREEN_ROUND = 0x8000
ACONFIGURATION_COLOR_MODE = 0x10000
ACONFIGURATION_MNC_ZERO = 0xFFFF

# See http://aospxref.com/android-13.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#946

ORIENTATION_ANY = ACONFIGURATION_ORIENTATION_ANY
ORIENTATION_PORT = ACONFIGURATION_ORIENTATION_PORT
ORIENTATION_LAND = ACONFIGURATION_ORIENTATION_LAND
ORIENTATION_SQUARE = ACONFIGURATION_ORIENTATION_SQUARE

TOUCHSCREEN_ANY = ACONFIGURATION_TOUCHSCREEN_ANY
TOUCHSCREEN_NOTOUCH = ACONFIGURATION_TOUCHSCREEN_NOTOUCH
TOUCHSCREEN_STYLUS = ACONFIGURATION_TOUCHSCREEN_STYLUS
TOUCHSCREEN_FINGER = ACONFIGURATION_TOUCHSCREEN_FINGER

DENSITY_DEFAULT = ACONFIGURATION_DENSITY_DEFAULT
DENSITY_LOW = ACONFIGURATION_DENSITY_LOW
DENSITY_MEDIUM = ACONFIGURATION_DENSITY_MEDIUM
DENSITY_TV = ACONFIGURATION_DENSITY_TV
DENSITY_HIGH = ACONFIGURATION_DENSITY_HIGH
DENSITY_XHIGH = ACONFIGURATION_DENSITY_XHIGH
DENSITY_XXHIGH = ACONFIGURATION_DENSITY_XXHIGH
DENSITY_XXXHIGH = ACONFIGURATION_DENSITY_XXXHIGH
DENSITY_ANY = ACONFIGURATION_DENSITY_ANY
DENSITY_NONE = ACONFIGURATION_DENSITY_NONE

KEYBOARD_ANY = ACONFIGURATION_KEYBOARD_ANY
KEYBOARD_NOKEYS = ACONFIGURATION_KEYBOARD_NOKEYS
KEYBOARD_QWERTY = ACONFIGURATION_KEYBOARD_QWERTY
KEYBOARD_12KEY = ACONFIGURATION_KEYBOARD_12KEY

NAVIGATION_ANY = ACONFIGURATION_NAVIGATION_ANY
NAVIGATION_NONAV = ACONFIGURATION_NAVIGATION_NONAV
NAVIGATION_DPAD = ACONFIGURATION_NAVIGATION_DPAD
NAVIGATION_TRACKBALL = ACONFIGURATION_NAVIGATION_TRACKBALL
NAVIGATION_WHEEL = ACONFIGURATION_NAVIGATION_WHEEL

MASK_KEYSHIDDEN = 0x0003
KEYSHIDDEN_ANY = ACONFIGURATION_KEYSHIDDEN_ANY
KEYSHIDDEN_NO = ACONFIGURATION_KEYSHIDDEN_NO
KEYSHIDDEN_YES = ACONFIGURATION_KEYSHIDDEN_YES
KEYSHIDDEN_SOFT = ACONFIGURATION_KEYSHIDDEN_SOFT

MASK_NAVHIDDEN = 0x000C
SHIFT_NAVHIDDEN = 2
NAVHIDDEN_ANY = ACONFIGURATION_NAVHIDDEN_ANY << SHIFT_NAVHIDDEN
NAVHIDDEN_NO = ACONFIGURATION_NAVHIDDEN_NO << SHIFT_NAVHIDDEN
NAVHIDDEN_YES = ACONFIGURATION_NAVHIDDEN_YES << SHIFT_NAVHIDDEN

SCREENWIDTH_ANY = 0
SCREENHEIGHT_ANY = 0
SDKVERSION_ANY = 0
MINORVERSION_ANY = 0

MASK_SCREENSIZE = 0x0F
SCREENSIZE_ANY = ACONFIGURATION_SCREENSIZE_ANY
SCREENSIZE_SMALL = ACONFIGURATION_SCREENSIZE_SMALL
SCREENSIZE_NORMAL = ACONFIGURATION_SCREENSIZE_NORMAL
SCREENSIZE_LARGE = ACONFIGURATION_SCREENSIZE_LARGE
SCREENSIZE_XLARGE = ACONFIGURATION_SCREENSIZE_XLARGE

MASK_SCREENLONG = 0x30
SHIFT_SCREENLONG = 4
SCREENLONG_ANY = ACONFIGURATION_SCREENLONG_ANY << SHIFT_SCREENLONG
SCREENLONG_NO = ACONFIGURATION_SCREENLONG_NO << SHIFT_SCREENLONG
SCREENLONG_YES = ACONFIGURATION_SCREENLONG_YES << SHIFT_SCREENLONG

MASK_LAYOUTDIR = 0xC0
SHIFT_LAYOUTDIR = 6
LAYOUTDIR_ANY = ACONFIGURATION_LAYOUTDIR_ANY << SHIFT_LAYOUTDIR
LAYOUTDIR_LTR = ACONFIGURATION_LAYOUTDIR_LTR << SHIFT_LAYOUTDIR
LAYOUTDIR_RTL = ACONFIGURATION_LAYOUTDIR_RTL << SHIFT_LAYOUTDIR

MASK_UI_MODE_TYPE = 0x0F
UI_MODE_TYPE_ANY = ACONFIGURATION_UI_MODE_TYPE_ANY
UI_MODE_TYPE_NORMAL = ACONFIGURATION_UI_MODE_TYPE_NORMAL
UI_MODE_TYPE_DESK = ACONFIGURATION_UI_MODE_TYPE_DESK
UI_MODE_TYPE_CAR = ACONFIGURATION_UI_MODE_TYPE_CAR
UI_MODE_TYPE_TELEVISION = ACONFIGURATION_UI_MODE_TYPE_TELEVISION
UI_MODE_TYPE_APPLIANCE = ACONFIGURATION_UI_MODE_TYPE_APPLIANCE
UI_MODE_TYPE_WATCH = ACONFIGURATION_UI_MODE_TYPE_WATCH
UI_MODE_TYPE_VR_HEADSET = ACONFIGURATION_UI_MODE_TYPE_VR_HEADSET

MASK_UI_MODE_NIGHT = 0x30
SHIFT_UI_MODE_NIGHT = 4
UI_MODE_NIGHT_ANY = ACONFIGURATION_UI_MODE_NIGHT_ANY << SHIFT_UI_MODE_NIGHT
UI_MODE_NIGHT_NO = ACONFIGURATION_UI_MODE_NIGHT_NO << SHIFT_UI_MODE_NIGHT
UI_MODE_NIGHT_YES = ACONFIGURATION_UI_MODE_NIGHT_YES << SHIFT_UI_MODE_NIGHT

MASK_SCREENROUND = 0x03
SCREENROUND_ANY = ACONFIGURATION_SCREENROUND_ANY
SCREENROUND_NO = ACONFIGURATION_SCREENROUND_NO
SCREENROUND_YES = ACONFIGURATION_SCREENROUND_YES

MASK_WIDE_COLOR_GAMUT = 0x03
WIDE_COLOR_GAMUT_ANY = ACONFIGURATION_WIDE_COLOR_GAMUT_ANY
WIDE_COLOR_GAMUT_NO = ACONFIGURATION_WIDE_COLOR_GAMUT_NO
WIDE_COLOR_GAMUT_YES = ACONFIGURATION_WIDE_COLOR_GAMUT_YES

MASK_HDR = 0x0C
SHIFT_HDR = 2
HDR_ANY = ACONFIGURATION_HDR_ANY << SHIFT_HDR
HDR_NO = ACONFIGURATION_HDR_NO << SHIFT_HDR
HDR_YES = ACONFIGURATION_HDR_YES << SHIFT_HDR


class ARSCParser:
    """
    Parser for resource.arsc files

    The ARSC File is, like the binary XML format, a chunk based format.
    Both formats are actually identical but use different chunks in order to store the data.

    The most outer chunk in the ARSC file is a chunk of type `RES_TABLE_TYPE`.
    Inside this chunk is a StringPool and at least one package.

    Each package is a chunk of type `RES_TABLE_PACKAGE_TYPE`.
    It contains again many more chunks.
    """

    def __init__(self, raw_buff: bytes) -> None:
        """
        :param bytes raw_buff: the raw bytes of the file
        """
        self.buff = io.BufferedReader(io.BytesIO(raw_buff))
        self.buff_size = self.buff.raw.getbuffer().nbytes

        if self.buff_size < 8 or self.buff_size > 0xFFFFFFFF:
            raise ResParserError(
                "Invalid file size {} for a resources.arsc file!".format(
                    self.buff_size
                )
            )

        self.analyzed = False
        self._resolved_strings = None
        self.packages = defaultdict(list)
        self.values = {}
        self.resource_values = defaultdict(defaultdict)
        self.resource_configs = defaultdict(lambda: defaultdict(set))
        self.resource_keys = defaultdict(lambda: defaultdict(defaultdict))
        self.stringpool_main = None

        # First, there is a ResTable_header.
        self.header = ARSCHeader(self.buff, expected_type=RES_TABLE_TYPE)

        # More sanity checks...
        if self.header.header_size != 12:
            logger.warning(
                "The ResTable_header has an unexpected header size! Expected 12 bytes, got {}.".format(
                    self.header.header_size
                )
            )

        if self.header.size > self.buff_size:
            raise ResParserError(
                "The file seems to be truncated. Refuse to parse the file! Filesize: {}, declared size: {}".format(
                    self.buff_size, self.header.size
                )
            )

        if self.header.size < self.buff_size:
            logger.warning(
                "The Resource file seems to have data appended to it. Filesize: {}, declared size: {}".format(
                    self.buff_size, self.header.size
                )
            )

        # The ResTable_header contains the packageCount, i.e. the number of ResTable_package
        self.packageCount = unpack('<I', self.buff.read(4))[0]

        # Even more sanity checks...
        if self.packageCount < 1:
            logger.warning(
                "The number of packages is smaller than one. There should be at least one package!"
            )

        logger.debug(
            "Parsed ResTable_header with {} package(s) inside.".format(
                self.packageCount
            )
        )

        # skip to the start of the first chunk's data, skipping trailing header bytes (there should be none)
        self.buff.seek(self.header.start + self.header.header_size)

        # Now parse the data:
        # We should find one ResStringPool_header and one or more ResTable_package chunks inside
        while self.buff.tell() <= self.header.end - ARSCHeader.SIZE:
            res_header = ARSCHeader(self.buff)

            if res_header.end > self.header.end:
                # this inner chunk crosses the boundary of the table chunk
                logger.warning(
                    "Invalid chunk found! It is larger than the outer chunk: %s",
                    res_header,
                )
                break

            if res_header.type == RES_STRING_POOL_TYPE:
                # There should be only one StringPool per resource table.
                if self.stringpool_main:
                    logger.warning(
                        "Already found a ResStringPool_header, but there should be only one! Will not parse the Pool again."
                    )
                else:
                    self.stringpool_main = StringBlock(self.buff, res_header)
                    logger.debug(
                        "Found the main string pool: %s", self.stringpool_main
                    )

            elif res_header.type == RES_TABLE_PACKAGE_TYPE:
                if len(self.packages) > self.packageCount:
                    raise ResParserError(
                        "Got more packages ({}) than expected ({})".format(
                            len(self.packages), self.packageCount
                        )
                    )

                current_package = ARSCResTablePackage(self.buff, res_header)
                package_name = current_package.get_name()

                # After the Header, we have the resource type symbol table
                self.buff.seek(
                    current_package.header.start + current_package.typeStrings
                )
                type_sp_header = ARSCHeader(
                    self.buff, expected_type=RES_STRING_POOL_TYPE
                )
                mTableStrings = StringBlock(self.buff, type_sp_header)

                # Next, we should have the resource key symbol table
                self.buff.seek(
                    current_package.header.start + current_package.keyStrings
                )
                key_sp_header = ARSCHeader(
                    self.buff, expected_type=RES_STRING_POOL_TYPE
                )
                mKeyStrings = StringBlock(self.buff, key_sp_header)

                # Add them to the dict of read packages
                self.packages[package_name].append(current_package)
                self.packages[package_name].append(mTableStrings)
                self.packages[package_name].append(mKeyStrings)

                pc = PackageContext(
                    current_package,
                    self.stringpool_main,
                    mTableStrings,
                    mKeyStrings,
                )
                logger.debug("Constructed a PackageContext: %s", pc)

                # skip to the first header in this table package chunk
                # FIXME is this correct? We have already read the first two sections!
                # self.buff.set_idx(res_header.start + res_header.header_size)
                # this looks more like we want: (???)
                # FIXME it looks like that the two string pools we have read might not be concatenated to each other,
                # thus jumping to the sum of the sizes might not be correct...
                next_idx = (
                    res_header.start
                    + res_header.header_size
                    + type_sp_header.size
                    + key_sp_header.size
                )

                if next_idx != self.buff.tell():
                    # If this happens, we have a testfile ;)
                    logger.error("This looks like an odd resources.arsc file!")
                    logger.error(
                        "Please report this error including the file you have parsed!"
                    )
                    logger.error(
                        "next_idx = {}, current buffer position = {}".format(
                            next_idx, self.buff.tell()
                        )
                    )
                    logger.error(
                        "Please open a issue at https://github.com/androguard/androguard/issues"
                    )
                    logger.error("Thank you!")

                self.buff.seek(next_idx)

                # Read all other headers
                while self.buff.tell() <= res_header.end - ARSCHeader.SIZE:
                    pkg_chunk_header = ARSCHeader(self.buff)
                    logger.debug("Found a header: {}".format(pkg_chunk_header))
                    if (
                        pkg_chunk_header.start + pkg_chunk_header.size
                        > res_header.end
                    ):
                        # we are way off the package chunk; bail out
                        break

                    self.packages[package_name].append(pkg_chunk_header)

                    if pkg_chunk_header.type == RES_TABLE_TYPE_SPEC_TYPE:
                        self.packages[package_name].append(
                            ARSCResTypeSpec(self.buff, pc)
                        )

                    elif pkg_chunk_header.type == RES_TABLE_TYPE_TYPE:
                        # Parse a RES_TABLE_TYPE
                        # http://androidxref.com/9.0.0_r3/xref/frameworks/base/tools/aapt2/format/binary/BinaryResourceParser.cpp#311
                        start_of_chunk = self.buff.tell() - 8
                        expected_end_of_chunk = (
                            start_of_chunk + pkg_chunk_header.size
                        )
                        a_res_type = ARSCResType(self.buff, pc)
                        self.packages[package_name].append(a_res_type)
                        self.resource_configs[package_name][a_res_type].add(
                            a_res_type.config
                        )

                        logger.debug("Config: {}".format(a_res_type.config))

                        entries = []
                        FLAG_SPARSE = 0x01
                        FLAG_OFFSET16 = 0x02
                        NO_ENTRY_16 = 0xFFFF
                        NO_ENTRY_32 = 0xFFFFFFFF
                        expected_entries_start = (
                            start_of_chunk + a_res_type.entriesStart
                        )

                        # Helper function to convert 16-bit offset to 32-bit

                        for i in range(0, a_res_type.entryCount):
                            # Check if FLAG_SPARSE is set
                            if a_res_type.flags & FLAG_SPARSE:
                                entry = self.buff.read(4)
                                idx, off = unpack('<HH', entry)
                                current_package.mResId = (
                                    current_package.mResId & 0xFFFF0000 | idx
                                )
                                offset = off * 4
                            else:
                                current_package.mResId = (
                                    current_package.mResId & 0xFFFF0000 | i
                                )
                                # Check if FLAG_OFFSET16 is set
                                if a_res_type.flags & FLAG_OFFSET16:
                                    # Read as 16-bit offset
                                    offset_16 = unpack('<H', self.buff.read(2))[0]
                                    offset = offset_from16(offset_16)
                                    if offset == NO_ENTRY_16:
                                        continue
                                else:
                                    # Read as 32-bit offset
                                    offset = unpack('<I', self.buff.read(4))[0]
                                    if offset == NO_ENTRY_32:
                                        continue
                            entries.append((offset, current_package.mResId))

                        self.packages[package_name].append(entries)

                        base_offset = self.buff.tell()
                        if base_offset + ((4 - (base_offset % 4)) % 4) != expected_entries_start:
                            # FIXME: seems like I am missing 2 bytes here in some cases, though it does not affect the result
                            logger.warning(
                                "Something is off here! We are not where the entries should start."
                            )
                        base_offset = expected_entries_start
                        for entry_offset, res_id in entries:
                            if entry_offset != -1:
                                ate = ARSCResTableEntry(
                                    self.buff,
                                    base_offset + entry_offset,
                                    expected_end_of_chunk,
                                    res_id,
                                    pc,
                                )
                                self.packages[package_name].append(ate)
                                if ate.is_weak():
                                    # FIXME we are not sure how to implement the FLAG_WEAK!
                                    # We saw the following: There is just a single Res_value after the ARSCResTableEntry
                                    # and then comes the next ARSCHeader.
                                    # Therefore we think this means all entries are somehow replicated?
                                    # So we do some kind of hack here. We set the idx to the entry again...
                                    # Now we will read all entries!
                                    # Not sure if this is a good solution though
                                    self.buff.seek(ate.start)
                    elif pkg_chunk_header.type == RES_TABLE_LIBRARY_TYPE:
                        logger.warning(
                            "RES_TABLE_LIBRARY_TYPE chunk is not supported"
                        )
                    else:
                        # Unknown / not-handled chunk type
                        logger.warning(
                            "Unknown chunk type encountered inside RES_TABLE_PACKAGE: %s",
                            pkg_chunk_header,
                        )

                    # skip to the next chunk
                    self.buff.seek(pkg_chunk_header.end)
            else:
                # Unknown / not-handled chunk type
                logger.warning(
                    "Unknown chunk type encountered: %s", res_header
                )

            # move to the next resource chunk
            self.buff.seek(res_header.end)

    def _analyse(self):
        if self.analyzed:
            return

        self.analyzed = True

        for package_name in self.packages:
            self.values[package_name] = {}

            nb = 3
            while nb < len(self.packages[package_name]):
                header = self.packages[package_name][nb]
                if isinstance(header, ARSCHeader):
                    if header.type == RES_TABLE_TYPE_TYPE:
                        a_res_type = self.packages[package_name][nb + 1]

                        locale = a_res_type.config.get_language_and_region()

                        c_value = self.values[package_name].setdefault(
                            locale, {"public": []}
                        )

                        entries = self.packages[package_name][nb + 2]
                        nb_i = 0
                        for entry, res_id in entries:
                            if entry != -1:
                                ate = self.packages[package_name][
                                    nb + 3 + nb_i
                                ]

                                self.resource_values[ate.mResId][
                                    a_res_type.config
                                ] = ate
                                self.resource_keys[package_name][
                                    a_res_type.get_type()
                                ][ate.get_value()] = ate.mResId

                                if ate.get_index() != -1:
                                    c_value["public"].append(
                                        (
                                            a_res_type.get_type(),
                                            ate.get_value(),
                                            ate.mResId,
                                        )
                                    )

                                if a_res_type.get_type() not in c_value:
                                    c_value[a_res_type.get_type()] = []

                                if a_res_type.get_type() == "string":
                                    c_value["string"].append(
                                        self.get_resource_string(ate)
                                    )

                                elif a_res_type.get_type() == "id":
                                    if (
                                        not ate.is_complex()
                                        and not ate.is_compact()
                                    ):
                                        c_value["id"].append(
                                            self.get_resource_id(ate)
                                        )

                                elif a_res_type.get_type() == "bool":
                                    if (
                                        not ate.is_complex()
                                        and not ate.is_compact()
                                    ):
                                        c_value["bool"].append(
                                            self.get_resource_bool(ate)
                                        )

                                elif a_res_type.get_type() == "integer":
                                    if ate.is_compact():
                                        c_value["integer"].append(ate.data)
                                    else:
                                        c_value["integer"].append(
                                            self.get_resource_integer(ate)
                                        )

                                elif a_res_type.get_type() == "color":
                                    if not ate.is_compact():
                                        c_value["color"].append(
                                            self.get_resource_color(ate)
                                        )

                                elif a_res_type.get_type() == "dimen":
                                    if not ate.is_compact():
                                        c_value["dimen"].append(
                                            self.get_resource_dimen(ate)
                                        )

                                nb_i += 1
                        nb += (
                            3 + nb_i - 1
                        )  # -1 to account for the nb+=1 on the next line
                nb += 1

    def get_resource_string(self, ate: ARSCResTableEntry) -> list:
        return [ate.get_value(), ate.get_key_data()]

    def get_resource_id(self, ate: ARSCResTableEntry) -> list[str]:
        x = [ate.get_value()]
        if ate.key.get_data() == 0:
            x.append("false")
        elif ate.key.get_data() == 1:
            x.append("true")
        return x

    def get_resource_bool(self, ate: ARSCResTableEntry) -> list[str]:
        x = [ate.get_value()]
        if ate.key.get_data() == 0:
            x.append("false")
        elif ate.key.get_data() == -1:
            x.append("true")
        return x

    def get_resource_integer(self, ate: ARSCResTableEntry) -> list:
        return [ate.get_value(), ate.key.get_data()]

    def get_resource_color(self, ate: ARSCResTableEntry) -> list:
        entry_data = ate.key.get_data()
        return [
            ate.get_value(),
            "#{:02x}{:02x}{:02x}{:02x}".format(
                ((entry_data >> 24) & 0xFF),
                ((entry_data >> 16) & 0xFF),
                ((entry_data >> 8) & 0xFF),
                (entry_data & 0xFF),
            ),
        ]

    def get_resource_dimen(self, ate: ARSCResTableEntry) -> list:
        try:
            return [
                ate.get_value(),
                "{}{}".format(
                    complexToFloat(ate.key.get_data()),
                    DIMENSION_UNITS[ate.key.get_data() & COMPLEX_UNIT_MASK],
                ),
            ]
        except IndexError:
            logger.debug(
                "Out of range dimension unit index for {}: {}".format(
                    complexToFloat(ate.key.get_data()),
                    ate.key.get_data() & COMPLEX_UNIT_MASK,
                )
            )
            return [ate.get_value(), ate.key.get_data()]

    # FIXME

    def get_packages_names(self) -> list[str]:
        """
        Retrieve a list of all package names, which are available
        in the given resources.arsc.
        """
        return list(self.packages.keys())

    def get_locales(self, package_name: str) -> list[str]:
        """
        Retrieve a list of all available locales in a given packagename.

        :param package_name: the package name to get locales of
        :returns: a list of locale strings
        """
        pass

    def get_types(
        self, package_name: str, locale: str = '\x00\x00'
    ) -> list[str]:
        """
        Retrieve a list of all types which are available in the given
        package and locale.

        :param package_name: the package name to get types of
        :param locale: the locale to get types of (default: '\x00\x00')
        :returns: a list of type strings
        """
        pass

    def get_public_resources(
        self, package_name: str, locale: str = '\x00\x00'
    ) -> bytes:
        """
        Get the XML (as string) of all resources of type 'public'.

        The public resources table contains the IDs for each item.

        :param package_name: the package name to get the resources for
        :param locale: the locale to get the resources for (default: '\x00\x00')
        :returns: the public xml bytes
        """
        pass

    def get_string_resources(
        self, package_name: str, locale: str = '\x00\x00'
    ) -> bytes:
        """
        Get the XML (as string) of all resources of type 'string'.

        Read more about string resources:
        <https://developer.android.com/guide/topics/resources/string-resource.html>

        :param package_name: the package name to get the resources for
        :param locale: the locale to get the resources for (default: '\x00\x00')
        :returns: the string xml bytes
        """
        pass

    def get_strings_resources(self) -> bytes:
        """
        Get the XML (as string) of all resources of type 'string'.
        This is a combined variant, which has all locales and all package names
        stored.

        :returns: the string, locales, and package name xml bytes
        """
        pass

    def get_id_resources(
        self, package_name: str, locale: str = '\x00\x00'
    ) -> bytes:
        """
        Get the XML (as string) of all resources of type 'id'.

        Read more about ID resources:
        <https://developer.android.com/guide/topics/resources/more-resources.html#Id>

        :param package_name: the package name to get the resources for
        :param locale: the locale to get the resources for (default: '\x00\x00')

        :returns: the id resources xml bytes
        """
        pass

    def get_bool_resources(
        self, package_name: str, locale: str = '\x00\x00'
    ) -> bytes:
        """
        Get the XML (as string) of all resources of type 'bool'.

        Read more about bool resources:
        <https://developer.android.com/guide/topics/resources/more-resources.html#Bool>

        :param package_name: the package name to get the resources for
        :param locale: the locale to get the resources for (default: '\x00\x00')

        :returns: the bool resources xml bytes
        """
        pass

    def get_integer_resources(
        self, package_name: str, locale: str = '\x00\x00'
    ) -> bytes:
        """
        Get the XML (as string) of all resources of type 'integer'.

        Read more about integer resources:
        <https://developer.android.com/guide/topics/resources/more-resources.html#Integer>

        :param package_name: the package name to get the resources for
        :param locale: the locale to get the resources for (default: '\x00\x00')

        :returns: the integer resources xml bytes
        """
        pass

    def get_color_resources(
        self, package_name: str, locale: str = '\x00\x00'
    ) -> bytes:
        """
        Get the XML (as string) of all resources of type 'color'.

        Read more about color resources:
        <https://developer.android.com/guide/topics/resources/more-resources.html#Color>

        :param package_name: the package name to get the resources for
        :param locale: the locale to get the resources for (default: '\x00\x00')

        :returns: the color resources xml bytes
        """
        pass

    def get_dimen_resources(
        self, package_name: str, locale: str = '\x00\x00'
    ) -> bytes:
        """
        Get the XML (as string) of all resources of type 'dimen'.

        Read more about Dimension resources:
        <https://developer.android.com/guide/topics/resources/more-resources.html#Dimension>

        :param package_name: the package name to get the resources for
        :param locale: the locale to get the resources for (default: '\x00\x00')

        :returns: the dimen resource xml bytes
        """
        pass

    def get_id(
        self, package_name: str, rid: int, locale: str = '\x00\x00'
    ) -> tuple:
        """
        Returns the tuple `(resource_type, resource_name, resource_id)`
        for the given resource_id.

        :param package_name: package name to query
        :param rid: the resource_id
        :param locale: specific locale
        :returns: tuple of (resource_type, resource_name, resource_id)
        """
        pass

    class ResourceResolver:
        """
        Resolves resources by ID and configuration.
        This resolver deals with complex resources as well as with references.
        """

        def __init__(
            self,
            android_resources: ARSCParser,
            config: Union[ARSCResTableConfig, None] = None,
        ) -> None:
            """
            :param ARSCParser android_resources: A resource parser
            :param ARSCResTableConfig config: The desired configuration or None to resolve all.
            """
            self.resources = android_resources
            self.wanted_config = config

        def resolve(self, res_id: int) -> list[tuple[ARSCResTableConfig, str]]:
            """
            the given ID into the Resource and returns a list of matching resources.

            :param int res_id: numerical ID of the resource
            :returns: a list of tuples of (ARSCResTableConfig, str)
            """
            result = []
            self._resolve_into_result(result, res_id, self.wanted_config)
            return result

        def _resolve_into_result(self, result, res_id, config):
            # First: Get all candidates
            configs = self.resources.get_res_configs(res_id, config)

            for config, ate in configs:
                # deconstruct them and check if more candidates are generated
                self.put_ate_value(result, ate, config)

        def put_ate_value(
            self,
            result: list,
            ate: ARSCResTableEntry,
            config: ARSCResTableConfig,
        ) -> None:
            """
            Put a [ARSCResTableEntry][androguard.core.axml.ARSCResTableEntry] into the list of results
            :param result: results array
            :param ate:
            :param config:
            """
            if ate.is_complex():
                complex_array = []
                result.append((config, complex_array))
                for _, item in ate.item.items:
                    self.put_item_value(
                        complex_array, item, config, ate, complex_=True
                    )
            elif ate.is_compact():
                self.put_item_value(
                    result,
                    ate.data,
                    config,
                    ate,
                    complex_=False,
                    compact_=True,
                )
            else:
                self.put_item_value(
                    result, ate.key, config, ate, complex_=False
                )

        def put_item_value(
            self,
            result: list,
            item: Union[ARSCResStringPoolRef, int],
            config: ARSCResTableConfig,
            parent: ARSCResTableEntry,
            complex_: bool,
            compact_: bool = False,
        ) -> None:
            """
            Put the tuple ([ARSCResTableConfig][androguard.core.axml.ARSCResTableConfig], resolved string) into the result set

            :param result: the result set
            :param item:
            :param config:
            :param parent: the originating entry
            :param complex_: True if the originating `ARSCResTableEntry` was complex
            :param bool compact_: True if the originating `ARSCResTableEntry` was compact
            """
            if isinstance(item, ARSCResStringPoolRef):
                if item.is_reference():
                    res_id = item.get_data()
                    if res_id:
                        # Infinite loop detection:
                        # TODO should this stay here or should be detect the loop much earlier?
                        if res_id == parent.mResId:
                            logger.warning(
                                "Infinite loop detected at resource item {}. It references itself!".format(
                                    parent
                                )
                            )
                            return

                        self._resolve_into_result(
                            result, item.get_data(), self.wanted_config
                        )
                else:
                    if complex_:
                        result.append(item.format_value())
                    else:
                        result.append((config, item.format_value()))
            else:
                if compact_:
                    result.append(
                        (config, parent.parent.stringpool_main.getString(item))
                    )

    def get_resolved_res_configs(
        self, rid: int, config: Union[ARSCResTableConfig, None] = None
    ) -> list[tuple[ARSCResTableConfig, str]]:
        """
        Return a list of resolved resource IDs with their corresponding configuration.
        It has a similar return type as [get_res_configs][androguard.core.axml.ARSCParser.get_res_configs] but also handles complex entries
        and references.
        Also instead of returning [ARSCResTableConfig][androguard.core.axml.ARSCResTableConfig] in the tuple, the actual values are resolved.

        This is the preferred way of resolving resource IDs to their resources.

        :param rid: the numerical ID of the resource
        :param config: the desired configuration or None to retrieve all
        :return: A list of tuples of (`ARSCResTableConfig`, str)
        """
        resolver = ARSCParser.ResourceResolver(self, config)
        return resolver.resolve(rid)


    def get_res_configs(
        self,
        rid: int,
        config: Union[ARSCResTableConfig, None] = None,
        fallback: bool = True,
    ) -> list[ARSCResTableConfig]:
        """
        Return the resources found with the ID `rid` and select
        the right one based on the configuration, or return all if no configuration was set.

        But we try to be generous here and at least try to resolve something:
        This method uses a fallback to return at least one resource (the first one in the list)
        if more than one items are found and the default config is used and no default entry could be found.

        This is usually a bad sign (i.e. the developer did not follow the android documentation:
        <https://developer.android.com/guide/topics/resources/localization.html#failing2)>
        In practise an app might just be designed to run on a single locale and thus only has those locales set.

        You can disable this fallback behaviour, to just return exactly the given result.

        :param rid: resource id as int
        :param config: a config to resolve from, or None to get all results
        :param fallback: Enable the fallback for resolving default configuration (default: True)
        :return: a list of `ARSCResTableConfig`
        """
        self._analyse()

        if not rid:
            raise ValueError("'rid' should be set")
        if not isinstance(rid, int):
            raise ValueError("'rid' must be an int")

        if rid not in self.resource_values:
            logger.warning(
                "The requested rid '0x{:08x}' could not be found in the list of resources.".format(
                    rid
                )
            )
            return []

        res_options = self.resource_values[rid]
        if len(res_options) > 1 and config:
            if config in res_options:
                return [(config, res_options[config])]
            elif fallback and config == ARSCResTableConfig.default_config():
                logger.warning(
                    "No default resource config could be found for the given rid '0x{:08x}', using fallback!".format(
                        rid
                    )
                )
                return [list(self.resource_values[rid].items())[0]]
            else:
                return []
        else:
            return list(res_options.items())

    def get_string(
        self, package_name: str, name: str, locale: str = '\x00\x00'
    ) -> Union[str, None]:
        self._analyse()

        try:
            for i in self.values[package_name][locale]["string"]:
                if i[0] == name:
                    return i
        except KeyError:
            return None




    @staticmethod
    def parse_id(name: str) -> tuple[str, str]:
        """
        Resolves an id from a binary XML file in the form `@[package:]DEADBEEF`
        and returns a tuple of package name and resource id.
        If no package name was given, i.e. the ID has the form `@DEADBEEF`,
        the package name is set to None.

        :raises ValueError: if the id is malformed.

        :param name: the string of the resource, as in the binary XML file
        :return: a tuple of (resource_id, package_name).
        """

        if not name.startswith('@'):
            raise ValueError(
                "Not a valid resource ID, must start with @: '{}'".format(name)
            )

        # remove @
        name = name[1:]

        package = None
        if ':' in name:
            package, res_id = name.split(':', 1)
        else:
            res_id = name

        if len(res_id) != 8:
            raise ValueError(
                "Numerical ID is not 8 characters long: '{}'".format(res_id)
            )

        try:
            return int(res_id, 16), package
        except ValueError:
            raise ValueError("ID is not a hex ID: '{}'".format(res_id))

    def get_resource_xml_name(
        self, r_id: int, package: Union[str, None] = None
    ) -> str:
        """
        Returns the XML name for a resource, including the package name if package is `None`.
        A full name might look like `@com.example:string/foobar`
        Otherwise the name is only looked up in the specified package and is returned without
        the package name.
        The same example from about without the package name will read as `@string/foobar`.

        If the ID could not be found, `None` is returned.

        A description of the XML name can be found here:
        <https://developer.android.com/guide/topics/resources/providing-resources#ResourcesFromXml>

        :param r_id: numerical ID if the resource
        :param package: package name
        :return: XML name identifier
        """
        pass


class PackageContext:
    def __init__(
        self,
        current_package: ARSCResTablePackage,
        stringpool_main: StringBlock,
        mTableStrings: StringBlock,
        mKeyStrings: StringBlock,
    ) -> None:
        """
        :param current_package:
        :param stringpool_main:
        :param mTableStrings:
        :param mKeyStrings:
        """
        self.stringpool_main = stringpool_main
        self.mTableStrings = mTableStrings
        self.mKeyStrings = mKeyStrings
        self.current_package = current_package




    def __repr__(self):
        return "<PackageContext {}, {}, {}, {}>".format(
            self.current_package,
            self.stringpool_main,
            self.mTableStrings,
            self.mKeyStrings,
        )


class ARSCHeader:
    """
    Object which contains a Resource Chunk.
    This is an implementation of the `ResChunk_header`.

    It will throw an [ResParserError][androguard.core.axml.ResParserError] if the header could not be read successfully.

    It is not checked if the data is outside the buffer size nor if the current
    chunk fits into the parent chunk (if any)!

    The parameter `expected_type` can be used to immediately check the header for the type or raise a [ResParserError][androguard.core.axml.ResParserError].
    This is useful if you know what type of chunk must follow.

    See http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#196
    """

    # This is the minimal size such a header must have. There might be other header data too!
    SIZE = 2 + 2 + 4

    def __init__(
        self,
        buff: BinaryIO,
        expected_type: Union[int, None] = None
    ) -> None:
        """
        :raises ResParserError: if header malformed
        :param buff: the buffer set to the position where the header starts.
        :param int expected_type: the type of the header which is expected.
        """
        self.start = buff.tell()
        # Make sure we do not read over the buffer:
        if buff.raw.getbuffer().nbytes < self.start + self.SIZE:
            raise ResParserError(
                "Can not read over the buffer size! Offset={}".format(
                    self.start
                )
            )

        # Checking for dummy data between elements
        while True:
            cur_pos = buff.tell()
            self._type, self._header_size, self._size = unpack(
                '<HHL', buff.read(self.SIZE)
            )

            # cases where packers set the EndNamespace with zero size: check we are the end and add the prefix + uri
            if self._size < self.SIZE and (
                buff.raw.getbuffer().nbytes
                == cur_pos + self._header_size + 4 + 4
            ):
                self._size = 24
            header_ok = self._header_size >= self.SIZE and self._size >= self._header_size
            if (self._type < RES_XML_FIRST_CHUNK_TYPE or self._type > RES_XML_LAST_CHUNK_TYPE) and header_ok:
                break
            if cur_pos == 0 or header_ok:
                break
            buff.seek(cur_pos)
            buff.read(1)
            logger.warning(
                "Appears that dummy data are found between elements!"
            )

        if expected_type and self._type != expected_type:
            raise ResParserError(
                "Header type is not equal the expected type: Got 0x{:04x}, wanted 0x{:04x}".format(
                    self._type, expected_type
                )
            )

        # Assert that the read data will fit into the chunk.
        # The total size must be equal or larger than the header size
        if self._header_size < self.SIZE:
            raise ResParserError(
                "declared header size is smaller than required size of {}! Offset={}".format(
                    self.SIZE, self.start
                )
            )
        if self._size < self.SIZE:
            raise ResParserError(
                "declared chunk size is smaller than required size of {}! Offset={}".format(
                    self.SIZE, self.start
                )
            )
        if self._size < self._header_size:
            raise ResParserError(
                "declared chunk size ({}) is smaller than header size ({})! Offset={}".format(
                    self._size, self._header_size, self.start
                )
            )

    @property
    def type(self) -> int:
        """
        Type identifier for this chunk
        """
        pass

    @property
    def header_size(self) -> int:
        """
        Size of the chunk header (in bytes).  Adding this value to
        the address of the chunk allows you to find its associated data
        (if any).
        """
        pass

    @property
    def size(self) -> int:
        """
        Total size of this chunk (in bytes).  This is the chunkSize plus
        the size of any data associated with the chunk.  Adding this value
        to the chunk allows you to completely skip its contents (including
        any child chunks).  If this value is the same as chunkSize, there is
        no data associated with the chunk.
        """
        pass

    @property
    def end(self) -> int:
        """
        Get the absolute offset inside the file, where the chunk ends.
        This is equal to `ARSCHeader.start + ARSCHeader.size`.
        """
        pass

    def __repr__(self):
        return "<ARSCHeader idx='0x{:08x}' type='{}' header_size='{}' size='{}'>".format(
            self.start, self.type, self.header_size, self.size
        )


class ARSCResTablePackage:
    """
    A `ResTable_package`

    See http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#861
    """

    def __init__(self, buff: BinaryIO, header: ARSCHeader) -> None:
        self.header = header
        self.start = buff.tell()
        self.id = unpack('<I', buff.read(4))[0]
        self.name = buff.read(256)
        self.typeStrings = unpack('<I', buff.read(4))[0]
        self.lastPublicType = unpack('<I', buff.read(4))[0]
        self.keyStrings = unpack('<I', buff.read(4))[0]
        self.lastPublicKey = unpack('<I', buff.read(4))[0]
        self.mResId = self.id << 24

    def get_name(self) -> None:
        name = self.name.decode("utf-16", 'replace')
        name = name[: name.find("\x00")]
        return name


class ARSCResTypeSpec:
    """
    See http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#1327
    """

    def __init__(
        self, buff: BinaryIO, parent: Union[PackageContext, None] = None
    ) -> None:
        self.start = buff.tell()
        self.parent = parent
        self.id = unpack('<B', buff.read(1))[0]
        self.res0 = unpack('<B', buff.read(1))[0]
        self.res1 = unpack('<H', buff.read(2))[0]
        # TODO: https://github.com/androguard/androguard/issues/1014 | Properly account for the cases where res0/1 are not zero
        try:
            if self.res0 != 0:
                logger.warning("res0 must be zero!")
            if self.res1 != 0:
                logger.warning("res1 must be zero!")
            self.entryCount = unpack('<I', buff.read(4))[0]

            self.typespec_entries = []
            for i in range(0, self.entryCount):
                self.typespec_entries.append(unpack('<I', buff.read(4))[0])
        except Exception as e:
            logger.error(e)


class ARSCResType:
    """
    This is a `ResTable_type` without it's `ResChunk_header`.
    It contains a `ResTable_config`

    See http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#1364
    """

    def __init__(
        self, buff: BinaryIO, parent: Union[PackageContext, None] = None
    ) -> None:
        self.start = buff.tell()
        self.parent = parent

        self.id = unpack('<B', buff.read(1))[0]
        # TODO there is now FLAG_SPARSE: http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#1401
        (self.flags,) = unpack('<B', buff.read(1))
        self.reserved = unpack('<H', buff.read(2))[0]
        if self.reserved != 0:
            # /libs/androidfw/LoadedArsc.cpp -> VerifyResTableType does not verify reserved value!
            logger.warning("Reserved must be zero! Meta is that you?")
        self.entryCount = unpack('<I', buff.read(4))[0]
        self.entriesStart = unpack('<I', buff.read(4))[0]

        self.mResId = (0xFF000000 & self.parent.get_mResId()) | self.id << 16
        self.parent.set_mResId(self.mResId)

        self.config = ARSCResTableConfig(buff)

        logger.debug("Parsed {}".format(self))

    def get_type(self) -> str:
        return self.parent.mTableStrings.getString(self.id - 1)


    def __repr__(self):
        return (
            "<ARSCResType(start=0x%x, id=0x%x, flags=0x%x, entryCount=%d, entriesStart=0x%x, mResId=0x%x, %s)>"
            % (
                self.start,
                self.id,
                self.flags,
                self.entryCount,
                self.entriesStart,
                self.mResId,
                "table:" + self.parent.mTableStrings.getString(self.id - 1),
            )
        )


class ARSCResTableConfig:
    """
    ARSCResTableConfig contains the configuration for specific resource selection.
    This is used on the device to determine which resources should be loaded
    based on different properties of the device like locale or displaysize.

    See the definition of `ResTable_config` in
    http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#911
    """

    @classmethod
    def default_config(cls):
        if not hasattr(cls, 'DEFAULT'):
            cls.DEFAULT = ARSCResTableConfig(None)
        return cls.DEFAULT

    def __init__(self, buff: Union[BinaryIO, None] = None, **kwargs) -> None:
        if buff is not None:
            self.start = buff.tell()

            # uint32_t
            self.size = unpack('<I', buff.read(4))[0]

            # union: uint16_t mcc, uint16_t mnc
            # 0 means any
            self.imsi = unpack('<I', buff.read(4))[0]

            # uint32_t as chars \0\0 means any
            # either two 7bit ASCII representing the ISO-639-1 language code
            # or a single 16bit LE value representing ISO-639-2 3 letter code
            self.locale = unpack('<I', buff.read(4))[0]

            # struct of:
            # uint8_t orientation
            # uint8_t touchscreen
            # uint16_t density
            self.screenType = unpack('<I', buff.read(4))[0]

            if self.size >= 20:
                # struct of
                # uint8_t keyboard
                # uint8_t navigation
                # uint8_t inputFlags
                # uint8_t inputPad0
                self.input = unpack('<I', buff.read(4))[0]
            else:
                logger.debug(
                    "This file does not have input flags! size={}".format(
                        self.size
                    )
                )
                self.input = 0

            if self.size >= 24:
                # struct of
                # uint16_t screenWidth
                # uint16_t screenHeight
                self.screenSize = unpack('<I', buff.read(4))[0]
            else:
                logger.debug(
                    "This file does not have screenSize! size={}".format(
                        self.size
                    )
                )
                self.screenSize = 0

            if self.size >= 28:
                # struct of
                # uint16_t sdkVersion
                # uint16_t minorVersion  which should be always 0, as the meaning is not defined
                self.version = unpack('<I', buff.read(4))[0]
            else:
                logger.debug(
                    "This file does not have version! size={}".format(
                        self.size
                    )
                )
                self.version = 0

            # The next three fields seems to be optional
            if self.size >= 32:
                # struct of
                # uint8_t screenLayout
                # uint8_t uiMode
                # uint16_t smallestScreenWidthDp
                (self.screenConfig,) = unpack('<I', buff.read(4))
            else:
                logger.debug(
                    "This file does not have a screenConfig! size={}".format(
                        self.size
                    )
                )
                self.screenConfig = 0

            if self.size >= 36:
                # struct of
                # uint16_t screenWidthDp
                # uint16_t screenHeightDp
                (self.screenSizeDp,) = unpack('<I', buff.read(4))
            else:
                logger.debug(
                    "This file does not have a screenSizeDp! size={}".format(
                        self.size
                    )
                )
                self.screenSizeDp = 0

            if self.size >= 40:
                self.localeScript = buff.read(4)

            if self.size >= 44:
                self.localeVariant = buff.read(8)

            if self.size >= 52:
                # struct of
                # uint8_t screenLayout2
                # uint8_t colorMode
                # uint16_t screenConfigPad2
                (self.screenConfig2,) = unpack("<I", buff.read(4))
            else:
                logger.debug(
                    "This file does not have a screenConfig2! size={}".format(
                        self.size
                    )
                )
                self.screenConfig2 = 0

            self.exceedingSize = self.size - (buff.tell() - self.start)
            if self.exceedingSize > 0:
                logger.debug("Skipping padding bytes!")
                self.padding = buff.read(self.exceedingSize)

        else:
            self.start = 0
            self.size = 0
            self.imsi = ((kwargs.pop('mcc', 0) & 0xFFFF) << 0) + (
                (kwargs.pop('mnc', 0) & 0xFFFF) << 16
            )

            temp_locale = kwargs.pop('locale', 0)
            if isinstance(temp_locale, str):
                self.set_language_and_region(temp_locale)
            else:
                self.locale = temp_locale

            for char_ix, char in kwargs.pop('locale', "")[0:4]:
                self.locale += ord(char) << (char_ix * 8)

            self.screenType = (
                ((kwargs.pop('orientation', 0) & 0xFF) << 0)
                + ((kwargs.pop('touchscreen', 0) & 0xFF) << 8)
                + ((kwargs.pop('density', 0) & 0xFFFF) << 16)
            )

            self.input = (
                ((kwargs.pop('keyboard', 0) & 0xFF) << 0)
                + ((kwargs.pop('navigation', 0) & 0xFF) << 8)
                + ((kwargs.pop('inputFlags', 0) & 0xFF) << 16)
                + ((kwargs.pop('inputPad0', 0) & 0xFF) << 24)
            )

            self.screenSize = (
                (kwargs.pop('screenWidth', 0) & 0xFFFF) << 0
            ) + ((kwargs.pop('screenHeight', 0) & 0xFFFF) << 16)

            self.version = ((kwargs.pop('sdkVersion', 0) & 0xFFFF) << 0) + (
                (kwargs.pop('minorVersion', 0) & 0xFFFF) << 16
            )

            self.screenConfig = (
                ((kwargs.pop('screenLayout', 0) & 0xFF) << 0)
                + ((kwargs.pop('uiMode', 0) & 0xFF) << 8)
                + ((kwargs.pop('smallestScreenWidthDp', 0) & 0xFFFF) << 16)
            )

            self.screenSizeDp = (
                (kwargs.pop('screenWidthDp', 0) & 0xFFFF) << 0
            ) + ((kwargs.pop('screenHeightDp', 0) & 0xFFFF) << 16)

            # TODO add this some day...
            self.screenConfig2 = 0

            self.exceedingSize = 0

    def _unpack_language_or_region(self, char_in, char_base):
        char_out = ""
        if char_in[0] & 0x80:
            first = char_in[1] & 0x1F
            second = ((char_in[1] & 0xE0) >> 5) + ((char_in[0] & 0x03) << 3)
            third = (char_in[0] & 0x7C) >> 2
            char_out += chr(first + char_base)
            char_out += chr(second + char_base)
            char_out += chr(third + char_base)
        else:
            if char_in[0]:
                char_out += chr(char_in[0])
            if char_in[1]:
                char_out += chr(char_in[1])
        return char_out



    def get_language_and_region(self) -> str:
        """
        Returns the combined language+region string or \x00\x00 for the default locale
        :returns: the combined language and region string
        """
        if self.locale != 0:
            _language = self._unpack_language_or_region(
                [
                    self.locale & 0xFF,
                    (self.locale & 0xFF00) >> 8,
                ],
                ord('a'),
            )
            _region = self._unpack_language_or_region(
                [
                    (self.locale & 0xFF0000) >> 16,
                    (self.locale & 0xFF000000) >> 24,
                ],
                ord('0'),
            )
            return (_language + "-r" + _region) if _region else _language
        return "\x00\x00"

    def get_config_name_friendly(self) -> str:
        """
        Here for legacy reasons.

        use [get_qualifier][androguard.core.axml.ARSCResTableConfig.get_qualifier] instead.
        :returns: the qualifier string
        """
        pass

    def get_qualifier(self) -> str:
        """
        Return resource name qualifier for the current configuration.
        for example

        * `ldpi-v4`
        * `hdpi-v4`

        All possible qualifiers are listed in table 2 of <https://developer.android.com/guide/topics/resources/providing-resources>

        You can find how android process this at [ResourceTypes 3243](http://aospxref.com/android-13.0.0_r3/xref/frameworks/base/libs/androidfw/ResourceTypes.cpp#3243)

        :return: the resource name qualifer string
        """
        pass




    def is_default(self) -> bool:
        """
        Test if this is a default resource, which matches all

        This is indicated that all fields are zero.
        :returns: True if default, False otherwise
        """
        pass


    def __hash__(self):
        return hash(self._get_tuple())

    def __eq__(self, other):
        return self._get_tuple() == other._get_tuple()

    def __repr__(self):
        return "<ARSCResTableConfig '{}'={}>".format(
            self.get_qualifier(), repr(self._get_tuple())
        )


class ARSCResTableEntry:
    """
    A `ResTable_entry`.

    See <https://cs.android.com/android/platform/superproject/main/+/main:frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h;l=1522;drc=442fcb158a5b2e23340b74ce2e29e5e1f5bf9d66;bpv=0;bpt=0>
    """

    # If set, this is a complex entry, holding a set of name/value
    # mappings.  It is followed by an array of ResTable_map structures.
    FLAG_COMPLEX = 1

    # If set, this resource has been declared public, so libraries
    # are allowed to reference it.
    FLAG_PUBLIC = 2

    # If set, this is a weak resource and may be overriden by strong
    # resources of the same name/type. This is only useful during
    # linking with other resource tables.
    FLAG_WEAK = 4

    # If set, this is a compact entry with data type and value directly
    # encoded in this entry
    FLAG_COMPACT = 8

    def __init__(
        self,
        buff: BinaryIO,
        entry_offset: int,
        expected_end_of_chunk: int,
        mResId: int,
        parent: Union[PackageContext, None] = None,
    ) -> None:
        self.start = buff.seek(entry_offset)
        self.mResId = mResId
        self.parent = parent

        self.size = unpack('<H', buff.read(2))[0]
        self.flags = unpack('<H', buff.read(2))[0]
        # This is a ResStringPool_ref
        self.index = unpack('<I', buff.read(4))[0]

        if self.is_complex():
            self.item = ARSCComplex(buff, expected_end_of_chunk, parent)
        elif self.is_compact():
            self.key = self.size
            self.data = self.index
            self.datatype = (self.flags >> 8) & 0xFF
        else:
            # If FLAG_COMPLEX is not set, a Res_value structure will follow
            self.key = ARSCResStringPoolRef(buff, self.parent)

        if self.is_weak():
            logger.debug("Parsed {}".format(self))

    def get_index(self) -> int:
        return self.index

    def get_value(self) -> str:
        if self.is_compact():
            return self.parent.mKeyStrings.getString(self.key)
        else:
            return self.parent.mKeyStrings.getString(self.index)

    def get_key_data(self) -> str:
        if self.is_compact():
            return self.parent.stringpool_main.getString(self.data)
        else:
            return self.key.get_data_value()


    def is_complex(self) -> bool:
        return (self.flags & self.FLAG_COMPLEX) != 0

    def is_compact(self) -> bool:
        return (self.flags & self.FLAG_COMPACT) != 0


    def __repr__(self):
        return "<ARSCResTableEntry idx='0x{:08x}' mResId='0x{:08x}' flags='0x{:02x}' holding={}>".format(
            self.start,
            self.mResId,
            self.flags,
            self.item if self.is_complex() else self.key,
        )


class ARSCComplex:
    """
    This is actually a `ResTable_map_entry`

    It contains a set of {name: value} mappings, which are of type `ResTable_map`.
    A `ResTable_map` contains two items: `ResTable_ref` and `Res_value`.

    See [ResourceTypes.h 1485](http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#1485) for `ResTable_map_entry`
    and [ResourceTypes.h 1498](http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#1498) for `ResTable_map`
    """

    def __init__(
        self,
        buff: BinaryIO,
        expected_end_of_chunk: int,
        parent: Union[PackageContext, None] = None,
    ) -> None:
        self.start = buff.tell()
        self.parent = parent

        self.id_parent = unpack('<I', buff.read(4))[0]
        self.count = unpack('<I', buff.read(4))[0]

        self.items = []
        # Parse self.count number of `ResTable_map`
        # these are structs of ResTable_ref and Res_value
        # ResTable_ref is a uint32_t.
        for i in range(0, self.count):
            if buff.tell() + 4 > expected_end_of_chunk:
                print(
                    f"We are out of bound with this complex entry. Count: {self.count}"
                )
                break
            self.items.append(
                (
                    unpack('<I', buff.read(4))[0],
                    ARSCResStringPoolRef(buff, self.parent),
                )
            )

    def __repr__(self):
        return "<ARSCComplex idx='0x{:08x}' parent='{}' count='{}'>".format(
            self.start, self.id_parent, self.count
        )


class ARSCResStringPoolRef:
    """
    This is actually a `Res_value`
    It holds information about the stored resource value

    See: [ResourceTypes.h 262](http://androidxref.com/9.0.0_r3/xref/frameworks/base/libs/androidfw/include/androidfw/ResourceTypes.h#262)
    """

    def __init__(
        self, buff: BinaryIO, parent: Union[PackageContext, None] = None
    ) -> None:
        self.start = buff.tell()
        self.parent = parent

        (self.size,) = unpack("<H", buff.read(2))
        (self.res0,) = unpack("<B", buff.read(1))
        try:
            if self.res0 != 0:
                logger.warning("res0 must be always zero!")
            self.data_type = unpack('<B', buff.read(1))[0]
            # data is interpreted according to data_type
            self.data = unpack('<I', buff.read(4))[0]
        except Exception as e:
            logger.error(e)

    def get_data_value(self) -> str:
        return self.parent.stringpool_main.getString(self.data)

    def get_data(self) -> int:
        return self.data



    def format_value(self) -> str:
        """
        Return the formatted (interpreted) data according to `data_type`.
        """
        return format_value(
            self.data_type, self.data, self.parent.stringpool_main.getString
        )

    def is_reference(self) -> bool:
        """
        Returns True if the Res_value is actually a reference to another resource
        """
        return self.data_type == TYPE_REFERENCE

    def __repr__(self):
        return "<ARSCResStringPoolRef idx='0x{:08x}' size='{}' type='{}' data='0x{:08x}'>".format(
            self.start,
            self.size,
            TYPE_TABLE.get(self.data_type, "0x%x" % self.data_type),
            self.data,
        )


def get_arsc_info(arscobj: ARSCParser) -> str:
    """
    Return a string containing all resources packages ordered by packagename, locale and type.

    :param arscobj: [ARSCParser][androguard.core.axml.ARSCParser]
    :return: a string
    """
    pass
