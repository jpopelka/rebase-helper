# -*- coding: utf-8 -*-
#
# This tool helps you rebase your package to the latest version
# Copyright (C) 2013-2019 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Authors: Petr Hráček <phracek@redhat.com>
#          Tomáš Hozza <thozza@redhat.com>
#          Nikola Forró <nforro@redhat.com>
#          František Nečas <fifinecas@seznam.cz>

import collections.abc
import fnmatch
import re
from typing import Dict, Iterator, List, Optional, Tuple, cast

from rebasehelper.spec_content import SpecContent
from rebasehelper.helpers.macro_helper import MacroHelper


class Tag:
    def __init__(self, section_index: int, section_name: str, line: int, name: str, value_span: Tuple[int, int],
                 valid: bool) -> None:
        self.section_index: int = section_index
        self.section_name: str = section_name
        self.line: int = line
        self.name: str = name
        self.value_span: Tuple[int, int] = value_span
        self.valid: bool = valid

    def __eq__(self, other):
        return (self.section_index == other.section_index and
                self.section_name == other.section_name and
                self.line == other.line and
                self.name == other.name and
                self.value_span == other.value_span and
                self.valid == other.valid)


class Tags(collections.abc.Sequence):
    def __init__(self, raw_content: SpecContent, parsed_content: SpecContent) -> None:
        self.items: Tuple[Tag] = self._parse(raw_content, parsed_content)

    def __getitem__(self, index):
        return self.items[index]

    def __len__(self):
        return len(self.items)

    @classmethod
    def _map_sections_to_parsed(cls, raw_content: SpecContent, parsed_content: SpecContent) -> Dict[int, int]:
        """Creates a mapping of raw sections to parsed sections.

        Returns:
            A dict where the keys are indexes of sections in raw content and values are their
            counterparts in parsed content. Value is set to -1 if the section is not in
            parsed SpecContent.
        """
        result: Dict[int, int] = {}
        parsed = 0
        for index, (section, _) in enumerate(raw_content.sections):
            if parsed < len(parsed_content.sections) and parsed_content.sections[parsed][0].lower() == section.lower():
                result[index] = parsed
                parsed += 1
            else:
                result[index] = -1

        return result

    @classmethod
    def _parse(cls, raw_content: SpecContent, parsed_content: SpecContent) -> Tuple[Tag]:
        result = []
        parsed_mapping = cls._map_sections_to_parsed(raw_content, parsed_content)
        # counts number of occurrences of one particular section
        for section_index, (section, section_content) in enumerate(raw_content.sections):
            section = section.lower()
            parsed_section_index = parsed_mapping[section_index]
            parsed: List[str] = [] if parsed_section_index == -1 else parsed_content.sections[parsed_section_index][1]
            if section.startswith('%package'):
                result.extend(cls._parse_package_tags(section, section_content, parsed, section_index))
            elif section.startswith('%sourcelist') or section.startswith('%patchlist'):
                result.extend(cls._parse_list_tags(section, section_content, parsed,
                                                   cast(Tuple[Tag], tuple(result)), section_index))
        return cast(Tuple[Tag], tuple(result))

    @classmethod
    def _parse_package_tags(cls, section: str, section_content: List[str], parsed: List[str],
                            section_index: int) -> List[Tag]:
        """Parses all tags in a %package section and determines if they are valid.

        A tag is considered valid if it is still present after evaluating all conditions.

        Note that this is not perfect - if the same tag appears in both %if and %else blocks,
        and has the same value in both, it's impossible to tell them apart, so only the latter
        is considered valid, disregarding the actual condition.

        Returns:
              A tuple of all Tag objects.

              Indexed tag names are sanitized, for example 'Source' is replaced with 'Source0'
              and 'Patch007' with 'Patch7'.

              Tag names are capitalized, section names are lowercase.

        """
        def sanitize(name):
            if name.startswith('Source') or name.startswith('Patch'):
                # strip padding zeroes from indexes
                tokens = re.split(r'(\d+)', name, 1)
                if len(tokens) == 1:
                    return '{0}0'.format(tokens[0])
                return '{0}{1}'.format(tokens[0], int(tokens[1]))
            return name.capitalize()
        result = []
        tag_re = re.compile(r'^(?P<prefix>(?P<name>\w+)\s*:\s*)(?P<value>.+)$')
        for line_index, line in enumerate(section_content):
            expanded = MacroHelper.expand(line)
            if not line or not expanded:
                continue
            valid = bool(parsed and [p for p in parsed if p == expanded.rstrip()])
            m = tag_re.match(line)
            if m:
                result.append(Tag(section_index, section, line_index,
                                  sanitize(m.group('name')), m.span('value'), valid))
                continue
            m = tag_re.match(expanded)
            if m:
                start = line.find(m.group('prefix'))
                if start < 0:
                    # tag is probably defined by a macro, just ignore it
                    continue
                # conditionalized tag
                line = line[start:].rstrip('}')  # FIXME: removing trailing braces is not very robust
                m = tag_re.match(line)
                if m:
                    span = cast(Tuple[int, int], tuple(x + start for x in m.span('value')))
                    result.append(Tag(section_index, section, line_index, sanitize(m.group('name')), span, valid))

        return result

    @classmethod
    def _parse_list_tags(cls, section: str, section_content: List[str], parsed: List[str],
                         parsed_tags: Tuple[Tag], section_index: int) -> List[Tag]:
        """Parses all tags in a %sourcelist or %patchlist section.

        Only parses tags that are valid (that is - are in parsed), nothing more can
        consistently be detected.

        Follows how rpm works, the new Source/Patch tags are indexed starting from
        the last parsed Source/Patch tag.

        """
        tag = 'Source' if section == '%sourcelist' else 'Patch'
        indexes = []
        for parsed_tag in cls._filter(parsed_tags, name=tag + '*'):
            try:
                indexes.append(int(parsed_tag.name.lstrip(tag)))
            except ValueError:
                continue
        index = 0 if not indexes else max(indexes) + 1
        result = []
        for i, line in enumerate(section_content):
            expanded = MacroHelper.expand(line)
            is_comment = SpecContent.get_comment_span(line, section)[0] != len(line)
            if not expanded or not line or is_comment or not [p for p in parsed if p == expanded.rstrip()]:
                continue
            result.append(Tag(section_index, section, i, tag + str(index), (0, len(line)), True))
            index += 1

        return result

    @classmethod
    def _filter(cls, tags: Tuple[Tag], section_index: Optional[int] = None, section_name: Optional[str] = None,
                name: Optional[str] = None, valid: Optional[bool] = True) -> Iterator[Tag]:
        result = iter(tags)
        if section_index is not None:
            result = filter(lambda t: t.section_index == section_index, result)
        if section_name is not None:
            result = filter(lambda t: t.section_name == section_name.lower(), result)  # type: ignore
        if name is not None:
            result = filter(lambda t: fnmatch.fnmatchcase(t.name, name.capitalize()), result)  # type: ignore
        if valid is not None:
            result = filter(lambda t: t.valid == valid, result)
        return result

    def filter(self, section_index: Optional[int] = None, section_name: Optional[str] = None,
               name: Optional[str] = None, valid: Optional[bool] = True) -> Iterator[Tag]:
        """Filters tags based on section, name or validity. Defaults to all valid tags in all sections.

        Args:
            section_index: If specified, includes tags only from section of this index.
            section_name: If specified, includes tags only from sections of this name.
            name: If specified, includes tags matching this name. Wildcards are supported.
            valid: If specified, includes tags of this validity.

        Returns:
            Iterator of matching Tag objects.

        """
        return self._filter(self.items, section_index, section_name, name, valid)