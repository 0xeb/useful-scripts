# mdparser.py
# Author: Elias Bachaalany
# License: Apache 2.0
# (c) 2024 Elias Bachaalany. All rights reserved.

class MarkdownHeading:
    def __init__(self, level, title):
        self.level: int = level
        self.title: str = title
        self.contents: list[str] = []
        self.subheadings: list[MarkdownHeading] = []

    def add_subheading(self, subheading):
        self.subheadings.append(subheading)

    def __str__(self):
        return f'{"#" * self.level} {self.title}'

class MarkdownDict:
    def __init__(self, data):
        self.data = data

    def __getitem__(self, key):
        return self.data.get(key)

    def get_val(self, path, default=None, check_title=False):
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

def parse_markdown(text):
    lines = text.split('\n')
    stack = []
    root = MarkdownHeading(0, 'root')
    stack.append(root)

    for line in lines:
        if line.startswith('#'):
            level = len(line.split(' ')[0])
            title = line[level + 1:]
            heading = MarkdownHeading(level, title)

            while stack and stack[-1].level >= level:
                stack.pop()
            
            stack[-1].add_subheading(heading)
            stack.append(heading)
        else:
            if stack:
class MarkdownHeading:
    def __init__(self, level, title):
        self.level: int = level
        self.title: str = title
        self.contents: list[str] = []
        self.subheadings: list[MarkdownHeading] = []

    def add_subheading(self, subheading):
        self.subheadings.append(subheading)

    def __str__(self):
        return f'{"#" * self.level} {self.title}'

class MarkdownDict:
    def __init__(self, data):
        self.data = data

    def __getitem__(self, key):
        return self.data.get(key)

    def get_val(self, path, default=None, check_title=False):
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

def parse_markdown(text):
    lines = text.split('\n')
    stack = []
    root = MarkdownHeading(0, 'root')
    stack.append(root)

    for line in lines:
        if line.startswith('#'):
            level = len(line.split(' ')[0])
            title = line[level + 1:]
            heading = MarkdownHeading(level, title)

            while stack and stack[-1].level >= level:
                stack.pop()
            
            stack[-1].add_subheading(heading)
            stack.append(heading)
        else:
            if stack:
                stack[-1].contents.append(line)

    def build_dict(heading):
        result = {'title': heading.title, 'contents': heading.contents}
        for subheading in heading.subheadings:
            result[subheading.title] = build_dict(subheading)
        return result

    return root.subheadings, MarkdownDict(build_dict(root))

def print_headings(heading, indent=0):
    print(' ' * indent + f'Heading: {heading}')
    print(' ' * indent + 'Contents:', heading.contents)
    for subheading in heading.subheadings:
        print_headings(subheading, indent + 2)

