# mdparser.py
# Author: Elias Bachaalany
# License: Apache 2.0
# (c) 2024 Elias Bachaalany. All rights reserved.


from typing import List, Dict, Any, Optional, Tuple

class MarkdownHeading:
    """
    Represents a Markdown heading, its contents, and subheadings.
    """
    def __init__(self, level: int, title: str) -> None:
        self.level: int = level
        self.title: str = title
        self.contents: List[str] = []
        self.subheadings: List['MarkdownHeading'] = []

    def add_subheading(self, subheading: 'MarkdownHeading') -> None:
        """
        Add a subheading to this heading.
        """
        self.subheadings.append(subheading)

    def __str__(self) -> str:
        """
        Return the Markdown string representation of the heading.
        """
        return f'{"#" * self.level} {self.title}'

class MarkdownDict:
    """
    Dictionary-like wrapper for parsed Markdown headings.
    """
    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key)

    def get_val(self, path: str, default: Optional[str] = None, check_title: bool = False) -> Optional[str]:
        """
        Retrieve the contents of a heading by a dotted path.
        """
        d = self.data
        for k in path.split('.'):
            d = d.get(k)
            if not d:
                return default
            if d.get('title', '') != k:
                return default
        v = d.get('contents')
        if v is None:
            return default
        return '\n'.join(v)


def parse_markdown(text: str) -> Tuple[List[MarkdownHeading], MarkdownDict]:
    """
    Parse Markdown text into a list of MarkdownHeading objects and a MarkdownDict.
    """
    lines = text.split('\n')
    stack: List[MarkdownHeading] = []
    root = MarkdownHeading(0, 'root')
    stack.append(root)

    for line in lines:
        if line.startswith('#'):
            # Determine heading level and title
            level = len(line.split(' ')[0])
            title = line[level + 1:]
            heading = MarkdownHeading(level, title)

            # Pop stack to find correct parent
            while stack and stack[-1].level >= level:
                stack.pop()
            
            stack[-1].add_subheading(heading)
            stack.append(heading)
        else:
            if stack:
                stack[-1].contents.append(line)

    def build_dict(heading: MarkdownHeading) -> Dict[str, Any]:
        result: Dict[str, Any] = {'title': heading.title, 'contents': heading.contents}
        for subheading in heading.subheadings:
            result[subheading.title] = build_dict(subheading)
        return result

    return root.subheadings, MarkdownDict(build_dict(root))


def print_headings(heading: MarkdownHeading, indent: int = 0) -> None:
    """
    Recursively print headings and their contents for debugging.
    """
    print(' ' * indent + f'Heading: {heading}')
    print(' ' * indent + 'Contents:', heading.contents)
    for subheading in heading.subheadings:
        print_headings(subheading, indent + 2)

